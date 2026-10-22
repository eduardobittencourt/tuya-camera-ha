package lan

import (
	"encoding/binary"
	"net"
	"testing"
	"time"
)

func TestAuthenticatedDatagramSplitsConversationsWithoutTruncation(t *testing.T) {
	peer, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	defer peer.Close()
	sock, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	key := []byte("test-lan-key1234")
	router := newPacketRouter(sock, peer.LocalAddr().(*net.UDPAddr), key, iceCreds{})
	defer router.Close()
	one, two := router.conn(1), router.conn(2)
	segment := func(conv uint32) []byte {
		raw := make([]byte, 1024)
		binary.LittleEndian.PutUint32(raw, conv)
		raw[4] = 0x51
		binary.LittleEndian.PutUint32(raw[20:], 1000)
		return raw
	}
	body := append(segment(1), segment(2)...)
	packet := append(append([]byte{}, body...), mac(key, body)...)
	if _, err := peer.WriteToUDP(packet, sock.LocalAddr().(*net.UDPAddr)); err != nil {
		t.Fatal(err)
	}
	for index, c := range []*convConn{one, two} {
		c.SetReadDeadline(time.Now().Add(time.Second))
		buf := make([]byte, 1500)
		n, _, err := c.ReadFrom(buf)
		if err != nil || n != 1024 || binary.LittleEndian.Uint32(buf) != uint32(index+1) {
			t.Fatal("batched KCP segment lost or truncated")
		}
	}
	if router.truncated.Load() != 0 {
		t.Fatal("truncated authenticated batch")
	}
}
