package rtsp

import (
	"bytes"
	"encoding/binary"
	"io"
	"net"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/storage"
	"github.com/pion/rtp"
)

type receivedRTP struct {
	channel byte
	packet  rtp.Packet
}

// Exercise the actual TCP framing, not only the forwarder's private fields.
func forwarderReceiver(t *testing.T, rf *RTPForwarder) <-chan receivedRTP {
	t.Helper()
	server, client := net.Pipe()
	t.Cleanup(func() { server.Close(); client.Close() })
	if err := rf.AddTCPClient("test", server, 0, 2, 4); err != nil {
		t.Fatal(err)
	}
	packets := make(chan receivedRTP, 512)
	go func() {
		defer close(packets)
		for {
			var header [4]byte
			if _, err := io.ReadFull(client, header[:]); err != nil {
				return
			}
			if header[0] != '$' {
				t.Error("invalid interleaved RTP framing")
				return
			}
			data := make([]byte, binary.BigEndian.Uint16(header[2:]))
			if _, err := io.ReadFull(client, data); err != nil {
				return
			}
			var packet rtp.Packet
			if err := packet.Unmarshal(data); err != nil {
				t.Error(err)
				return
			}
			packets <- receivedRTP{header[1], packet}
		}
	}()
	return packets
}

func nextRTP(t *testing.T, packets <-chan receivedRTP) receivedRTP {
	t.Helper()
	select {
	case packet := <-packets:
		return packet
	case <-time.After(time.Second):
		t.Fatal("no forwarded RTP packet")
		return receivedRTP{}
	}
}

func TestForwardVideoPreservesFrameClockSequenceAndSourcePacket(t *testing.T) {
	rf := NewRTPForwarder()
	packets := forwarderReceiver(t, rf)
	base := uint32(0xfffffff0)
	// Two HEVC fragments share a timestamp despite arriving separately;
	// the next frame crosses uint32 wraparound.
	for index, delta := range []uint32{0, 0, 6000} {
		packet := &rtp.Packet{Header: rtp.Header{Version: 2, Timestamp: base + delta,
			SequenceNumber: uint16(65534 + index), Marker: index != 0, SSRC: 9}, Payload: []byte{98, 1, 1}}
		rf.ForwardVideoPacket(packet)
		received := nextRTP(t, packets)
		if received.channel != 0 || received.packet.Timestamp != delta || received.packet.SequenceNumber != packet.SequenceNumber {
			t.Fatalf("video clock/sequence changed: %+v", received)
		}
		if packet.Timestamp != base+delta {
			t.Fatal("forwarding changed the caller's packet")
		}
		time.Sleep(2 * time.Millisecond)
	}
}

func TestForwardAudioBurstKeepsSampleClockAndResetsOnReconnect(t *testing.T) {
	rf := NewRTPForwarder()
	for _, base := range []uint32{0xfffffff0, 123456789} {
		packets := forwarderReceiver(t, rf)
		for index := range 12 {
			// 160 PCMU samples = 20 ms. Burst delivery must keep that interval.
			packet := &rtp.Packet{Header: rtp.Header{Version: 2, Timestamp: base + uint32(index*160),
				SequenceNumber: uint16(index), SSRC: 10}, Payload: make([]byte, 160)}
			rf.ForwardAudioPacket(packet)
			received := nextRTP(t, packets)
			if received.channel != 2 || received.packet.Timestamp != uint32(index*160) {
				t.Fatalf("audio sampling interval lost: %+v", received)
			}
			if packet.Timestamp != base+uint32(index*160) {
				t.Fatal("forwarding changed the caller's packet")
			}
		}
		rf.Stop()
	}
}

func TestForwardPCM16UsesL16WithoutChangingSamplesOrDuration(t *testing.T) {
	rf := NewRTPForwarder()
	rf.SetAudioPCM16(true)
	packets := forwarderReceiver(t, rf)
	// Known signed 16-bit little-endian samples: 0, 256, -256, 32767.
	payload := []byte{0, 0, 0, 1, 0, 255, 255, 127}
	want := []byte{0, 0, 1, 0, 255, 0, 127, 255}
	for index := range 2 {
		packet := &rtp.Packet{Header: rtp.Header{Version: 2, Timestamp: uint32(1234 + index*4)}, Payload: payload}
		rf.ForwardAudioPacket(packet)
		received := nextRTP(t, packets).packet
		if received.PayloadType != 97 || received.Timestamp != uint32(index*4) || !bytes.Equal(received.Payload, want) {
			t.Fatalf("incorrect RTP L16 conversion: %+v", received)
		}
		if !bytes.Equal(packet.Payload, payload) || packet.PayloadType != 0 {
			t.Fatal("PCM conversion modified the source packet")
		}
	}
	// A truncated sample must not produce malformed L16.
	rf.ForwardAudioPacket(&rtp.Packet{Header: rtp.Header{Version: 2}, Payload: []byte{1}})
	select {
	case <-packets:
		t.Fatal("forwarded a truncated PCM sample")
	default:
	}
}

func TestSDPDistinguishesPCMFromG711(t *testing.T) {
	server := NewRTSPServer(0, nil)
	for _, test := range []struct{ skill, want string }{
		{`{"audios":[{"codecType":101,"sampleRate":8000,"channels":1}]}`, "a=rtpmap:97 L16/8000/1\r\n"},
		{`{"audios":[{"codecType":101,"sampleRate":16000,"channels":2}]}`, "a=rtpmap:97 L16/16000/2\r\n"},
		{`{"audios":[{"codecType":105}]}`, "a=rtpmap:0 PCMU/8000\r\n"},
		{`{"audios":[{"codecType":106}]}`, "a=rtpmap:8 PCMA/8000\r\n"},
	} {
		sdp := server.generateSDP(&storage.CameraInfo{Skill: test.skill}, "rtsp://127.0.0.1/test")
		if !strings.Contains(sdp, test.want) {
			t.Fatalf("wrong audio SDP: %s", sdp)
		}
	}
}

func TestForwardParameterSetsDoesNotReplayOldRTPPackets(t *testing.T) {
	rf := NewRTPForwarder()
	packets := forwarderReceiver(t, rf)
	for index, nal := range []byte{7, 8, 5} {
		rf.ForwardVideoPacket(&rtp.Packet{Header: rtp.Header{Version: 2, Timestamp: uint32(index * 6000),
			SequenceNumber: uint16(index)}, Payload: []byte{nal, 1}})
	}
	for index := range 3 {
		if packet := nextRTP(t, packets); packet.packet.SequenceNumber != uint16(index) {
			t.Fatalf("stale parameter-set packet replayed: %+v", packet)
		}
	}
	select {
	case <-packets:
		t.Fatal("unexpected duplicate parameter-set packet")
	default:
	}
}

func TestForwardAudioVideoAndLifecycleConcurrently(t *testing.T) {
	rf := NewRTPForwarder()
	packets := forwarderReceiver(t, rf)
	var group sync.WaitGroup
	for _, audio := range []bool{false, true} {
		group.Go(func() {
			for index := range 100 {
				packet := &rtp.Packet{Header: rtp.Header{Version: 2, Timestamp: uint32(index * 6000),
					SequenceNumber: uint16(index)}, Payload: []byte{1, 2}}
				if audio {
					rf.ForwardAudioPacket(packet)
				} else {
					rf.ForwardVideoPacket(packet)
				}
			}
		})
	}
	group.Go(func() {
		for index := range 100 {
			rf.SetSourceSSRCs(uint32(index), uint32(index+1))
			rf.SourceSSRCs()
			rf.GetClientCount()
			rf.CleanupInactiveClients(time.Hour)
		}
	})
	group.Wait()
	for range 200 {
		nextRTP(t, packets)
	}
	group.Go(rf.Stop)
	group.Go(func() { rf.ForwardVideoPacket(&rtp.Packet{Header: rtp.Header{Version: 2}, Payload: []byte{1}}) })
	group.Go(func() { rf.SetSourceSSRCs(0, 1) })
	group.Wait()
	if rf.GetClientCount() != 0 {
		t.Fatal("Stop retained clients")
	}
}
