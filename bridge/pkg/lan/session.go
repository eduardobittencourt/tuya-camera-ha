package lan

import (
	"bufio"
	"bytes"
	"crypto/aes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"hash/crc32"
	"net"
	"sync"
	"sync/atomic"
	"time"
)

const (
	Port              = 6668
	HeartbeatInterval = 7 * time.Second
)

type Session struct {
	OnDPS      func(map[string]any)
	reader     *bufio.Reader
	LastCmd    uint32
	LastLength uint32
	LastPrefix string
	InitialDPS map[string]any
	DeviceID   string
	Key        []byte
	conn       net.Conn
	seq        atomic.Uint32
	writeMu    sync.Mutex
}

func Dial(ip, deviceID, localKey string) (*Session, error) {
	address := net.ParseIP(ip)
	if address == nil || !address.IsPrivate() {
		return nil, errors.New("non-private LAN address")
	}
	if len(localKey) != 16 {
		return nil, errors.New("invalid local key length")
	}
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(ip, "6668"), time.Second)
	if err != nil {
		return nil, err
	}
	s := &Session{DeviceID: deviceID, Key: []byte(localKey), conn: conn}
	query, _ := json.Marshal(map[string]string{"gwId": deviceID, "devId": deviceID})
	if err = s.Send(10, nil, query); err != nil {
		conn.Close()
		return nil, err
	}
	end := time.Now().Add(8 * time.Second)
	for time.Now().Before(end) {
		h, body, e := s.Recv(time.Second)
		if e != nil {
			if n, ok := e.(net.Error); ok && n.Timeout() {
				continue
			}
			conn.Close()
			return nil, e
		}
		if h.Cmd == 8 && bytes.Contains(body, []byte(`"dps"`)) {
			s.InitialDPS = decodeDPS(body)
			break
		}
	}
	return s, nil
}
func pack33(key []byte, seq, cmd uint32, payload []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	pad := 16 - len(payload)%16
	plain := append(append([]byte{}, payload...), bytes.Repeat([]byte{byte(pad)}, pad)...)
	encrypted := make([]byte, len(plain))
	for i := 0; i < len(plain); i += 16 {
		block.Encrypt(encrypted[i:i+16], plain[i:i+16])
	}
	if cmd == 9 && len(payload) == 0 {
		encrypted = nil
	}
	// CONTROL includes a clear version prefix; IPC signal/query/heartbeat do not.
	if cmd == 7 {
		encrypted = append(append([]byte("3.3"), make([]byte, 12)...), encrypted...)
	}
	// Cmd 32 follows the native 3.3 IPC format: no clear version header.
	out := make([]byte, 16)
	binary.BigEndian.PutUint32(out, Prefix55AA)
	binary.BigEndian.PutUint32(out[4:], seq)
	binary.BigEndian.PutUint32(out[8:], cmd)
	binary.BigEndian.PutUint32(out[12:], uint32(len(encrypted)+8))
	out = append(out, encrypted...)
	out = binary.BigEndian.AppendUint32(out, crc32.ChecksumIEEE(out))
	out = binary.BigEndian.AppendUint32(out, 0xaa55)
	return out, nil
}
func (s *Session) Send(cmd uint32, iv, payload []byte) error {

	frame, err := pack33(s.Key, s.seq.Add(1), cmd, payload)
	if err != nil {
		return err
	}
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	if err = s.conn.SetWriteDeadline(time.Now().Add(2 * time.Second)); err != nil {
		return err
	}
	_, err = s.conn.Write(frame)
	return err
}
func (s *Session) Recv(timeout time.Duration) (Header, []byte, error) {
	if err := s.conn.SetReadDeadline(time.Now().Add(timeout)); err != nil {
		return Header{}, nil, err
	}
	if s.reader == nil {
		s.reader = bufio.NewReaderSize(s.conn, maxFrameLen+16)
	}
	head, err := s.reader.Peek(16)
	if err != nil {
		return Header{}, nil, err
	}
	s.LastPrefix = "other"
	switch binary.BigEndian.Uint32(head) {
	case Prefix55AA:
		s.LastPrefix = "55aa"
	case Prefix6699:
		s.LastPrefix = "6699"
	}
	h, err := ParseHeader(head)
	s.LastCmd = h.Cmd
	s.LastLength = h.Length
	if err != nil {
		return h, nil, err
	}
	if h.Prefix != Prefix55AA || h.Length < 8 {
		return h, nil, errors.New("invalid 3.3 framing")
	}
	frame, err := s.reader.Peek(16 + int(h.Length))
	if err != nil {
		return h, nil, err
	}
	raw := append([]byte{}, frame...)
	s.reader.Discard(len(raw))
	rest := raw[16:]
	if binary.BigEndian.Uint32(raw[len(raw)-4:]) != 0xaa55 || crc32.ChecksumIEEE(raw[:len(raw)-8]) != binary.BigEndian.Uint32(raw[len(raw)-8:]) {
		return h, nil, errors.New("invalid 3.3 checksum")
	}
	body := rest[:len(rest)-8]
	// Empty ACKs have no return code; other firmware includes a 4-byte code.
	if len(body) == 4 || len(body)%16 == 4 || len(body)%16 == 3 {
		body = body[4:]
	}
	if bytes.HasPrefix(body, []byte("3.3")) {
		if len(body) < 15 {
			return h, nil, errors.New("short 3.3 payload")
		}
		body = body[15:]
	}
	if len(body) == 0 {
		return h, nil, nil
	}
	if len(body)%16 != 0 {
		return h, nil, errors.New("invalid encrypted block length")
	}
	block, err := aes.NewCipher(s.Key)
	if err != nil {
		return h, nil, err
	}
	plain := make([]byte, len(body))
	for i := 0; i < len(body); i += 16 {
		block.Decrypt(plain[i:i+16], body[i:i+16])
	}
	pad := int(plain[len(plain)-1])
	if pad < 1 || pad > 16 || !bytes.Equal(plain[len(plain)-pad:], bytes.Repeat([]byte{byte(pad)}, pad)) {
		return h, nil, errors.New("invalid encrypted padding")
	}
	return h, plain[:len(plain)-pad], nil
}
func (s *Session) Heartbeat() error { return s.Send(9, nil, nil) }
func (s *Session) Close() error     { return s.conn.Close() }
