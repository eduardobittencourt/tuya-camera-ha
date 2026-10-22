package lan

import (
	"bytes"
	"encoding/binary"
	"encoding/hex"
	"hash/crc32"
	"net"
	"testing"
	"time"
)

func TestNative33SignalMatchesIndependentFixture(t *testing.T) {
	key := []byte("test-lan-key1234")
	plain := []byte(`{"header":{"type":"offer"},"msg":{"sdp":"synthetic"}}`)
	got, err := pack33(key, 9, 32, plain)
	if err != nil {
		t.Fatal(err)
	}
	want, _ := hex.DecodeString("000055aa0000000900000020000000480f080317143a0236b6a7b77448a1e7f6faad342f581c14955166d8cdcb256d6d2093a3cbf9f3122ed0cd6c9dec21a84350691a64a06e12723b09545c6525741dcf82c3c30000aa55")
	if !bytes.Equal(got, want) {
		t.Fatal("native IPC framing differs from independent TinyTuya AES/CRC fixture")
	}
}
func reply33(t *testing.T, body []byte) []byte {
	raw, e := pack33([]byte("test-lan-key1234"), 1, 32, body)
	if e != nil {
		t.Fatal(e)
	}
	payload := append([]byte{0, 0, 0, 0}, raw[16:len(raw)-8]...)
	out := append(append([]byte{}, raw[:16]...), payload...)
	binary.BigEndian.PutUint32(out[12:], uint32(len(payload)+8))
	out = binary.BigEndian.AppendUint32(out, crc32.ChecksumIEEE(out))
	return binary.BigEndian.AppendUint32(out, 0xaa55)
}
func TestRecv33AcceptsLargeAnswerAndRejectsTampering(t *testing.T) {
	for _, tampered := range []bool{false, true} {
		left, right := net.Pipe()
		s := &Session{Key: []byte("test-lan-key1234"), conn: left}
		plain := append([]byte(`{"sdp":"`), bytes.Repeat([]byte("x"), 4000)...)
		plain = append(plain, []byte(`"}`)...)
		raw := reply33(t, plain)
		if tampered {
			raw[len(raw)-8] ^= 1
		}
		go func() { defer right.Close(); right.Write(raw) }()
		_, got, e := s.Recv(time.Second)
		left.Close()
		if tampered {
			if e == nil {
				t.Fatal("bad CRC was accepted")
			}
		} else if e != nil || !bytes.Equal(got, plain) {
			t.Fatal("large decrypted reply mismatch")
		}
	}
}

func TestRecvEmptyAcknowledgementWithoutReturnCode(t *testing.T) {
	left, right := net.Pipe()
	defer left.Close()
	raw := make([]byte, 16)
	binary.BigEndian.PutUint32(raw, Prefix55AA)
	binary.BigEndian.PutUint32(raw[8:], 9)
	binary.BigEndian.PutUint32(raw[12:], 8)
	raw = binary.BigEndian.AppendUint32(raw, crc32.ChecksumIEEE(raw))
	raw = binary.BigEndian.AppendUint32(raw, 0xaa55)
	go func() { defer right.Close(); right.Write(raw) }()
	s := &Session{Key: []byte("test-lan-key1234"), conn: left}
	header, body, err := s.Recv(time.Second)
	if err != nil || header.Cmd != 9 || len(body) != 0 {
		t.Fatal("empty heartbeat ACK rejected")
	}
}
