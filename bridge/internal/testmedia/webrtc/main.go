// Test-only WebRTC receiver for the synthetic camera fixture.
package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/pion/webrtc/v4"
)

func run(endpoint string) error {
	settings := webrtc.SettingEngine{}
	settings.SetIncludeLoopbackCandidate(true)
	pc, err := webrtc.NewAPI(webrtc.WithSettingEngine(settings)).NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		return err
	}
	defer pc.Close()
	tracks := make(chan string, 2)
	pc.OnTrack(func(track *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		for i := 0; i < 10; i++ {
			if _, _, err := track.ReadRTP(); err != nil {
				return
			}
		}
		tracks <- track.Codec().MimeType
	})
	for _, kind := range []webrtc.RTPCodecType{webrtc.RTPCodecTypeVideo, webrtc.RTPCodecTypeAudio} {
		if _, err := pc.AddTransceiverFromKind(kind, webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
			return err
		}
	}
	offer, err := pc.CreateOffer(nil)
	if err != nil {
		return err
	}
	gathered := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		return err
	}
	<-gathered
	client := &http.Client{Timeout: 35 * time.Second}
	response, err := client.Post(endpoint, "application/sdp", strings.NewReader(pc.LocalDescription().SDP))
	if err != nil {
		return err
	}
	defer response.Body.Close()
	answer, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024))
	if err != nil {
		return err
	}
	if response.StatusCode != http.StatusCreated && response.StatusCode != http.StatusOK {
		return fmt.Errorf("WebRTC endpoint returned %d", response.StatusCode)
	}
	if err := pc.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeAnswer, SDP: string(answer)}); err != nil {
		return err
	}
	seen := map[string]bool{}
	timer := time.NewTimer(20 * time.Second)
	defer timer.Stop()
	for !seen[webrtc.MimeTypeH264] || !seen[webrtc.MimeTypeOpus] {
		select {
		case codec := <-tracks:
			seen[codec] = true
		case <-timer.C:
			return fmt.Errorf("missing H.264/Opus WebRTC media: %v (peer %v, ICE %v)", seen, pc.ConnectionState(), pc.ICEConnectionState())
		}
	}
	fmt.Println("Received H.264 video and Opus audio via WebRTC")
	return nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: webrtc-probe <synthetic go2rtc endpoint>")
		os.Exit(2)
	}
	if err := run(os.Args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
