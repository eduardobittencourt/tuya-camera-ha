package rtsp

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/lan"
	"github.com/pion/rtp"
	"github.com/pion/rtp/codecs"
)

// resolveCameraIP follows an exact MAC match in the local neighbor table after
// DHCP changes. The setup address is the fallback, never a cloud lookup.
func resolveCameraIP(host, mac string) string {
	canonical := func(s string) string { return strings.ToLower(strings.ReplaceAll(s, "-", ":")) }
	if mac != "" {
		if data, err := os.ReadFile("/proc/net/arp"); err == nil {
			for _, line := range strings.Split(string(data), "\n") {
				fields := strings.Fields(line)
				if len(fields) >= 4 && canonical(fields[3]) == canonical(mac) {
					if ip := net.ParseIP(fields[0]); ip != nil && ip.IsPrivate() {
						return fields[0]
					}
				}
			}
		}
	}
	return host
}

// startLocal is called with wb.mutex held. The cloud bridge, if needed for
// waking a sleeping battery camera, is separate and closed before the LAN offer.
// A LAN negotiation/authentication failure never falls back to cloud video.
func (wb *WebRTCBridge) startLocal() error {
	local := wb.camera.Local
	host := resolveCameraIP(local.Host, local.MAC)
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsPrivate() || len(local.Key) != 16 || local.Password == "" || wb.camera.UID == "" {
		return errors.New("invalid local media configuration")
	}
	var closeWake func()
	defer func() {
		if closeWake != nil {
			closeWake()
		}
	}()
	var wake *WebRTCBridge
	defer func() {
		if wake != nil {
			wake.Stop()
		}
	}()
	var audioSamples atomic.Uint32
	var videoSeq, audioSeq uint16
	var lastVideo atomic.Int64
	var videoMu, audioMu sync.Mutex
	payloader := &codecs.H264Payloader{}
	epoch := time.Now()
	var pictureTS uint32
	pictureEnded := true
	var sps, pps []byte
	wb.rtpForwarder.SetAudioPCM16(true)
	onFrame := func(frame *lan.VideoFrame) {
		if len(frame.NAL) < 2 {
			return
		}
		videoMu.Lock()
		defer videoMu.Unlock()
		lastVideo.Store(time.Now().UnixNano())
		// The 3.3 transport clock layout differs from the reference model.
		// Use one monotonic arrival clock per picture, shared by every FU-A.
		if pictureEnded {
			pictureTS = uint32(time.Since(epoch).Nanoseconds() * 90000 / int64(time.Second))
			pictureEnded = false
		}
		payloads := [][]byte{frame.NAL}
		if len(frame.NAL) > 1200 && frame.NAL[0]&31 < 24 {
			payloads = payloader.Payload(1200, frame.NAL)
		}
		switch frame.NAL[0] & 31 {
		case 7:
			sps = append([]byte{}, frame.NAL...)
		case 8:
			pps = append([]byte{}, frame.NAL...)
		}
		idr := frame.NAL[0]&31 == 5 || (frame.NAL[0]&31 == 28 && frame.NAL[1]&0x9f == 0x85)
		if idr && len(sps) > 0 && len(pps) > 0 {
			payloads = append([][]byte{sps, pps}, payloads...)
		}
		for _, payload := range payloads {
			if len(payload) < 2 {
				continue
			}
			videoSeq++
			packet := &rtp.Packet{Header: rtp.Header{Version: 2, PayloadType: 96, SequenceNumber: videoSeq, Timestamp: pictureTS, Marker: h264End(payload)}, Payload: payload}
			if packet.Marker {
				pictureEnded = true
			}
			wb.rtpForwarder.ForwardVideoPacket(packet)
			if wb.OnVideoPacket != nil {
				wb.OnVideoPacket(packet)
			}
		}
	}
	onAudio := func(frame *lan.AudioFrame) {
		// This verified LAN profile is H.264 plus PCM16 mono at 8 kHz.
		if len(frame.Samples) == 0 || len(frame.Samples)%2 != 0 {
			return
		}
		audioMu.Lock()
		defer audioMu.Unlock()
		audioSeq++
		samples := uint32(len(frame.Samples) / 2)
		packet := &rtp.Packet{Header: rtp.Header{Version: 2, PayloadType: 97, SequenceNumber: audioSeq, SSRC: 1, Timestamp: audioSamples.Add(samples) - samples}, Payload: frame.Samples}
		wb.rtpForwarder.ForwardAudioPacket(packet)
		if wb.OnAudioPacket != nil {
			wb.OnAudioPacket(packet)
		}
	}
	newClient := func() *lan.Client {
		client := lan.NewClient(wb.camera.DeviceID, local.Key, local.Password, wb.camera.UID, host, onFrame, onAudio)
		client.DPIDs = local.DPIDs
		client.StreamType = 2
		if wb.resolution == "sd" {
			client.StreamType = 4
		}
		client.BeforeOffer = func() error {
			if wb.OnState != nil {
				wb.OnState("connecting_lan")
			}
			return nil
		}
		return client
	}
	wb.localClient = newClient()
	err := wb.localClient.Start(wb.ctx)
	if err != nil && wb.localClient.Phase == "lan_connect" && wb.ctx.Err() == nil {
		wb.localClient.Close()
		if wb.OnState != nil {
			wb.OnState("waking_cloud")
		}
		// A dedicated low-power wake avoids creating a cloud AV session. That
		// session's disconnect can send this battery firmware back to standby.
		if wb.mobileClient != nil {
			broker, wakeErr := NewMQTTManager(wb.mobileClient).connect(wb.camera.DeviceID)
			if wakeErr == nil {
				var once sync.Once
				closeWake = func() { once.Do(broker.Stop) }
				if broker.WakeCloud(wb.camera.DeviceID, local.Key) == nil {
					if wb.OnState != nil {
						wb.OnState("wake_mqtt")
					}
					deadline := time.Now().Add(12 * time.Second)
					for time.Now().Before(deadline) && wb.ctx.Err() == nil {
						wb.localClient = newClient()
						wb.localClient.BeforeOffer = func() error {
							if wb.OnState != nil {
								wb.OnState("connecting_lan")
							}
							return nil
						}
						err = wb.localClient.Start(wb.ctx)
						if err == nil || wb.localClient.Phase != "lan_connect" {
							break
						}
						time.Sleep(300 * time.Millisecond)
					}
				}
			}
		}
		if err != nil && wb.localClient.Phase == "lan_connect" {
			if wb.OnState != nil {
				wb.OnState("wake_media")
			}
			camera := *wb.camera
			camera.Local = nil
			wake = NewWebRTCBridge(&camera, wb.resolution, wb.user, wb.registryStore)
			wake.SetMobileClient(wb.mobileClient)
			first := make(chan struct{})
			var once sync.Once
			wake.OnVideoPacket = func(p *rtp.Packet) {
				if p.Marker {
					once.Do(func() { close(first) })
				}
			}
			if err := wake.Start(); err != nil {
				return fmt.Errorf("cloud wake failed: %w", err)
			}
			select {
			case <-first:
			case <-wb.ctx.Done():
				return errors.New("wake cancelled")
			case <-time.After(20 * time.Second):
				return errors.New("cloud wake delivered no picture")
			}
			wb.localClient = newClient()
			wb.localClient.BeforeOffer = func() error {
				wake.Stop()
				wake = nil
				if wb.OnState != nil {
					wb.OnState("connecting_lan")
				}
				return nil
			}
			err = wb.localClient.Start(wb.ctx)
		}
	}
	if err != nil {
		wb.localClient.Close()
		if wb.OnState != nil {
			wb.OnState("lan_failed_" + wb.localClient.Phase)
		}
		return fmt.Errorf("local media failed at %s", wb.localClient.Phase)
	}
	if closeWake != nil {
		stop := closeWake
		closeWake = nil
		time.AfterFunc(10*time.Second, stop)
		context.AfterFunc(wb.ctx, stop)
	}
	wb.connected = true
	lastVideo.Store(time.Now().UnixNano())
	go func() {
		tick := time.NewTicker(5 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-wb.ctx.Done():
				return
			case <-tick.C:
				if time.Since(time.Unix(0, lastVideo.Load())) > 20*time.Second {
					wb.handleError(errors.New("local video stalled"))
					return
				}
			}
		}
	}()
	return nil
}

func h264End(payload []byte) bool {
	if len(payload) < 2 {
		return false
	}
	switch payload[0] & 31 {
	case 28, 29:
		return payload[1]&0x40 != 0
	case 1, 5:
		return true
	}
	return false
}

// LANSDP is deliberately independent from cloud WebRTC capabilities. Local
// firmware can supply H.264/PCM while its cloud path advertises HEVC/G.711.
func localSDP(baseURL string) string {
	return "m=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1\r\na=control:" + baseURL + "/video\r\na=recvonly\r\n" +
		"m=audio 0 RTP/AVP 97\r\na=rtpmap:97 L16/8000/1\r\na=control:" + baseURL + "/audio\r\na=recvonly\r\n"
}
