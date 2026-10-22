package rtsp

import (
	"bufio"
	"encoding/binary"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/internal/registry"
	"github.com/pion/rtp"
	"io"
	"net"
	"strings"
	"testing"
	"time"
)

func TestMediaWaitsForCompletePlayResponse(t *testing.T) {
	server := NewRTSPServer(0, nil)
	stream := NewCameraStream(&registry.CameraInfo{}, "hd", nil, nil, server)
	a, b := net.Pipe()
	defer a.Close()
	defer b.Close()
	b.SetReadDeadline(time.Now().Add(3 * time.Second))
	reader := bufio.NewReader(b)
	client := &RTSPClient{conn: a, stream: stream, session: "synthetic", videoRTPChannel: 0, audioRTPChannel: 2, backAudioRTPChannel: 4}
	readResponse := func() {
		t.Helper()
		first, err := reader.ReadString('\n')
		if err != nil || !strings.HasPrefix(first, "RTSP/1.0 200") {
			t.Fatalf("expected RTSP response, got %q / %v", first, err)
		}
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				t.Fatal(err)
			}
			if line == "\r\n" {
				return
			}
		}
	}
	for _, track := range []struct{ name, channels string }{{"video", "0-1"}, {"audio", "2-3"}} {
		done := make(chan struct{})
		go func() {
			server.handleSetup(client, &RTSPRequest{URL: "rtsp://127.0.0.1/camera/" + track.name, Headers: map[string]string{"Transport": "RTP/AVP/TCP;interleaved=" + track.channels}})
			close(done)
		}()
		readResponse()
		<-done
		// A live source already in flight must not corrupt the next SETUP reply.
		stream.webrtcBridge.rtpForwarder.ForwardVideoPacket(&rtp.Packet{Header: rtp.Header{Version: 2}, Payload: []byte{0x65, 0}})
	}
	done := make(chan struct{})
	go func() {
		server.handlePlay(client, &RTSPRequest{URL: "rtsp://127.0.0.1/camera", Headers: map[string]string{"Session": "synthetic"}})
		close(done)
	}()
	readResponse()
	<-done
	go stream.webrtcBridge.rtpForwarder.ForwardVideoPacket(&rtp.Packet{Header: rtp.Header{Version: 2, Marker: true}, Payload: []byte{0x65, 0}})
	var header [4]byte
	if _, err := io.ReadFull(reader, header[:]); err != nil || header[0] != '$' {
		t.Fatal("RTP did not follow PLAY")
	}
	payload := make([]byte, binary.BigEndian.Uint16(header[2:]))
	if _, err := io.ReadFull(reader, payload); err != nil {
		t.Fatal(err)
	}
}
