package rtsp

import (
	"bytes"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/internal/registry"
	"github.com/pion/rtp"
)

func TestUDPBackchannelRemainsLoopbackAfterReconnect(t *testing.T) {
	server := NewRTSPServer(0, nil)
	t.Cleanup(server.cancel)
	server.Talkback = true
	stream := NewCameraStream(&registry.CameraInfo{DeviceID: "synthetic"}, "hd", nil, nil, server)
	t.Cleanup(func() { stream.webrtcBridge.Stop() })
	for generation := range 2 {
		if generation > 0 {
			stream.mutex.Lock()
			stream.replaceBridge()
			stream.mutex.Unlock()
		}
		t.Run(fmt.Sprint(generation), func(t *testing.T) {
			rf := stream.webrtcBridge.rtpForwarder
			received := make(chan *rtp.Packet, 1)
			rf.OnBackchannelAudio = func(packet *rtp.Packet) { received <- packet }
			if err := rf.AddUDPClient("synthetic", 0, 0); err != nil {
				t.Fatal(err)
			}
			defer rf.RemoveClient("synthetic")
			port, err := rf.SetupUDPBackchannel("synthetic", 50000)
			if err != nil {
				t.Fatal(err)
			}
			client := rf.clients["synthetic"]
			for _, listener := range []*net.UDPConn{client.backchannelListener, client.backchannelRTCPListener} {
				ip := listener.LocalAddr().(*net.UDPAddr).IP
				if !ip.Equal(net.IPv4(127, 0, 0, 1)) {
					t.Fatalf("managed talkback exposed on %s", ip)
				}
			}
			if port%2 != 0 || client.backchannelRTCPPort != port+1 {
				t.Fatal("RTP/RTCP ports must remain an even consecutive pair")
			}
			// A local relay can still send real RTP to the camera's audio callback.
			sender, err := net.DialUDP("udp4", nil, &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: port})
			if err != nil {
				t.Fatal(err)
			}
			defer sender.Close()
			packet := &rtp.Packet{Header: rtp.Header{Version: 2, PayloadType: 0, SequenceNumber: 7}, Payload: []byte{1, 2, 3}}
			data, err := packet.Marshal()
			if err != nil {
				t.Fatal(err)
			}
			if _, err := sender.Write(data); err != nil {
				t.Fatal(err)
			}
			select {
			case got := <-received:
				if got.SequenceNumber != packet.SequenceNumber || !bytes.Equal(got.Payload, packet.Payload) {
					t.Fatal("talkback RTP changed in transit")
				}
			case <-time.After(time.Second):
				t.Fatal("local talkback RTP did not reach the audio callback")
			}
			t.Run("LAN", func(t *testing.T) {
				addresses, err := net.InterfaceAddrs()
				if err != nil {
					t.Fatal(err)
				}
				var lanIP net.IP
				for _, address := range addresses {
					if network, ok := address.(*net.IPNet); ok && network.IP.To4() != nil && !network.IP.IsLoopback() {
						lanIP = network.IP
						break
					}
				}
				if lanIP == nil {
					t.Skip("no LAN IPv4 interface available")
				}
				lanSender, err := net.DialUDP("udp4", nil, &net.UDPAddr{IP: lanIP, Port: port})
				if err != nil {
					t.Fatal(err)
				}
				defer lanSender.Close()
				if _, err := lanSender.Write(data); err != nil {
					t.Fatal(err)
				}
				select {
				case <-received:
					t.Fatal("LAN audio reached managed talkback")
				case <-time.After(200 * time.Millisecond):
				}
			})
		})
	}
}
