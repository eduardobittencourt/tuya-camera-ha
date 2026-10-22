package lan

import (
	"context"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	kcp "github.com/xtaci/kcp-go/v5"
)

// Client negotiates command-32 signaling and camera-only AES/KCP media.
// Credentials are provisioned by Home Assistant, never fetched here.
type Client struct {
	DPIDs       []int
	dpMu        sync.Mutex
	dpValues    map[string]any
	reports     chan map[string]any
	StreamType  int
	Phase       string
	BeforeOffer func() error
	SignalInfo  func(map[string]any)
	DeviceID    string
	LocalKey    string
	Password    string
	UID         string
	// IP skips discovery when Home Assistant already resolved the monitor.
	IP string

	session *Session
	sock    *net.UDPConn
	router  *packetRouter
	// stream carries control messages, media the video and audio.
	stream *kcp.UDPSession
	media  []*kcp.UDPSession

	mu        sync.Mutex
	closed    bool
	cancel    context.CancelFunc
	stopClose func() bool
	onFrame   func(*VideoFrame)
	onAudio   func(*AudioFrame)

	statsMu sync.Mutex
	stats   Stats
}

// Stats counts what the media channel delivered, so a stream that is missing
// most of its pictures can be told apart from one that never received them.
type Stats struct {
	SignalError        string
	SignalErrorCmd     uint32
	SignalErrorLength  uint32
	SignalErrorPrefix  string
	SignalEOF          bool
	SignalFormatErrors int
	Outgoing           int64
	OutgoingACK        int64
	WriteErrors        int64
	AlternatePort      int64
	MaxDatagram        int64
	Truncated          int64
	ControlReplies     int
	AuthReplies        int
	AuthReplyZero      bool
	Datagrams          int64
	Accepted           int64
	WrongIP            int64
	BadMAC             int64
	PortChanges        int64
	SPS                int
	PPS                int
	Keyframes          int
	AudioBytes         int
	Reads              int
	OpenErrors         int
	Malformed          int
	Video              int
	Audio              int
	// Frames counts what reached the caller.
	Frames int
	// LongForm and ShortForm count the two sub-header layouts. Short-form
	// messages were read as gigabyte-long units and dropped until 2.3.8.
	LongForm  int
	ShortForm int

	// Other counts commands the dispatcher has no case for. Anything here is
	// media this bridge is discarding.
	Other map[uint32]int
}

func (c *Client) count(field *int) {
	c.statsMu.Lock()
	*field++
	c.statsMu.Unlock()
}

func (c *Client) countOther(cmd uint32) {
	c.statsMu.Lock()
	if c.stats.Other == nil {
		c.stats.Other = map[uint32]int{}
	}
	c.stats.Other[cmd]++
	c.statsMu.Unlock()
}

// Snapshot returns the counts so far.
func (c *Client) Snapshot() Stats {
	c.statsMu.Lock()
	defer c.statsMu.Unlock()
	out := c.stats
	if c.router != nil {
		out.Outgoing = c.router.outgoing.Load()
		out.OutgoingACK = c.router.outgoingACK.Load()
		out.WriteErrors = c.router.writeErrors.Load()
		out.AlternatePort = c.router.alternatePort.Load()
		out.MaxDatagram = c.router.maxDatagram.Load()
		out.Truncated = c.router.truncated.Load()
		out.Datagrams = c.router.datagrams.Load()
		out.Accepted = c.router.accepted.Load()
		out.WrongIP = c.router.wrongIP.Load()
		out.BadMAC = c.router.badMAC.Load()
		out.PortChanges = c.router.portChanges.Load()
	}
	out.Other = make(map[uint32]int, len(c.stats.Other))
	for cmd, n := range c.stats.Other {
		out.Other[cmd] = n
	}
	return out
}

// NewClient prepares a client; nothing touches the network until Start.
// Either callback may be nil, in which case that stream is discarded.
func NewClient(deviceID, localKey, password, uid, ip string, onFrame func(*VideoFrame), onAudio func(*AudioFrame)) *Client {
	return &Client{reports: make(chan map[string]any, 64), dpValues: map[string]any{},
		DeviceID: deviceID,
		LocalKey: localKey,
		Password: password,
		UID:      uid,
		IP:       ip,
		onFrame:  onFrame,
		onAudio:  onAudio,
	}
}

var candidateRE = regexp.MustCompile(`candidate:(\S+) (\d+) (\S+) (\d+) (\S+) (\d+) typ (\S+)`)

// Start discovers the monitor, negotiates a session and begins streaming.
func (c *Client) Start(ctx context.Context) (result error) {
	ctx, c.cancel = context.WithCancel(ctx)
	defer func() {
		if result != nil {
			c.Close()
		}
	}()
	ip := c.IP
	if ip == "" {
		return errors.New("lan: no private camera address")
	}

	var err error
	c.Phase = "lan_connect"
	c.session, err = Dial(ip, c.DeviceID, c.LocalKey)
	if err != nil {
		return err
	}

	c.report(c.session.InitialDPS)
	c.session.InitialDPS = nil
	c.stopClose = context.AfterFunc(ctx, func() { c.session.Close() })
	go c.keepAlive(ctx)
	c.session.OnDPS = c.report
	if c.BeforeOffer != nil {
		if err := c.BeforeOffer(); err != nil {
			return err
		}
	}
	c.Phase = "offer"
	sock, err := net.ListenUDP("udp4", &net.UDPAddr{})
	if err != nil {
		return err
	}
	c.sock = sock

	local, err := newICECreds()
	if err != nil {
		return err
	}
	offer, err := NewOffer(c.UID, c.DeviceID, local.Ufrag, local.Pwd)
	if err != nil {
		return err
	}
	if err := offer.SendOffer(c.session); err != nil {
		return err
	}

	hostIP, err := localAddrFor(&net.UDPAddr{IP: net.ParseIP(ip), Port: Port})
	if err != nil {
		return err
	}
	port := sock.LocalAddr().(*net.UDPAddr).Port
	if err := offer.SendCandidate(c.session, hostCandidate(hostIP, port)); err != nil {
		return err
	}

	c.Phase = "answer"
	remote, aesKey, peer, err := c.collectAnswer(offer)
	if err != nil {
		return err
	}

	connCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	c.Phase = "ice"
	if err := iceConnect(connCtx, sock, peer, local, remote); err != nil {
		return err
	}

	// The monitor splits control and media across two KCP conversations, so a
	// router under both sessions sorts the datagrams by conversation id.
	router := newPacketRouter(sock, peer, aesKey, local)
	c.router = router

	control, err := newKCP(router, convControl, peer)
	if err != nil {
		return err
	}
	c.stream = control
	c.Phase = "media_login"
	if err := c.login(aesKey); err != nil {
		return err
	}
	c.Phase = "media"
	go c.readLoop(ctx, c.stream, aesKey)
	go c.attachMedia(ctx, peer, aesKey)
	go c.drainSignals(ctx)
	return nil
}

// attachMedia starts a reader for each conversation the monitor opens.
//
// Which id carries the video is not fixed: it has been seen as 1 and as 2 on
// the same camera, so the session follows whatever arrives.
func (c *Client) attachMedia(ctx context.Context, peer *net.UDPAddr, aesKey []byte) {
	for {
		select {
		case <-ctx.Done():
			return
		case conv := <-c.router.opened:
			if conv == convControl {
				continue
			}
			stream, err := newKCP(c.router, conv, peer)
			if err != nil {
				debugf("lan: conversation %d could not be opened: %v", conv, err)
				continue
			}
			c.mu.Lock()
			closed := c.closed
			if !closed {
				c.media = append(c.media, stream)
			}
			c.mu.Unlock()
			if closed {
				stream.Close()
				return
			}
			go c.readLoop(ctx, stream, aesKey)
		}
	}
}

// collectAnswer waits for the monitor's answer and its first host candidate.
func (c *Client) collectAnswer(offer *Offer) (remote iceCreds, aesKey []byte, peer *net.UDPAddr, err error) {
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		frame, err := ReadSignal(c.session, time.Until(deadline))
		if err != nil {
			return iceCreds{}, nil, nil, err
		}
		if frame.Header.SessionID != offer.SessionID || frame.Header.Path != "lan" || frame.Header.From != c.DeviceID || frame.Header.To != c.UID {
			continue
		}
		switch frame.Header.Type {
		case TypeAnswer:
			if c.SignalInfo != nil {
				c.SignalInfo(map[string]any{"answer_aes_hex_chars": len(sdpAttr(frame.Msg.SDP, "aes-key")), "answer_has_ice": sdpAttr(frame.Msg.SDP, "ice-ufrag") != "", "answer_newlines": strings.Count(frame.Msg.SDP, "\n"), "answer_escaped_newlines": strings.Contains(frame.Msg.SDP, `\r\n`)})
			}
			remote.Ufrag = sdpAttr(frame.Msg.SDP, "ice-ufrag")
			remote.Pwd = sdpAttr(frame.Msg.SDP, "ice-pwd")
			raw, decErr := hex.DecodeString(sdpAttr(frame.Msg.SDP, "aes-key"))
			if decErr != nil {
				return iceCreds{}, nil, nil, fmt.Errorf("lan: bad aes-key in answer: %w", decErr)
			}
			aesKey = raw
			if c.SignalInfo != nil {
				c.SignalInfo(map[string]any{"media_keys_match": string(aesKey) == offer.AESKey})
			}
		case TypeCandidate:
			if addr, parseErr := parseCandidate(frame.Msg.Candidate); parseErr == nil && addr.IP.Equal(net.ParseIP(c.IP)) {
				peer = addr
			}
		case TypeDisconnect:
			return iceCreds{}, nil, nil, errors.New("lan: monitor refused the session")
		}
		if remote.Ufrag != "" && remote.Pwd != "" && len(aesKey) == 16 && peer != nil {
			return remote, aesKey, peer, nil
		}
	}
	return iceCreds{}, nil, nil, errors.New("lan: monitor never completed the answer")
}

func (c *Client) login(aesKey []byte) error {
	msgs, err := startupSequence(LoginToken(c.Password, c.LocalKey), c.StreamType)
	if err != nil {
		return err
	}
	for _, msg := range msgs {
		sealed, err := seal(aesKey, msg)
		if err != nil {
			return err
		}
		if _, err := c.stream.Write(sealed); err != nil {
			return err
		}
		time.Sleep(120 * time.Millisecond)
	}
	return nil
}

func (c *Client) readLoop(ctx context.Context, stream *kcp.UDPSession, aesKey []byte) {
	buf := make([]byte, 4*1024*1024)
	for {
		if ctx.Err() != nil {
			return
		}
		if err := stream.SetReadDeadline(time.Now().Add(10 * time.Second)); err != nil {
			return
		}
		n, err := stream.Read(buf)
		if err != nil {
			var n net.Error
			if errors.As(err, &n) && n.Timeout() {
				continue
			}
			return
		}
		c.count(&c.stats.Reads)
		msg, err := open(aesKey, buf[:n])
		if err != nil {
			c.count(&c.stats.OpenErrors)
			continue
		}
		if len(msg) >= 8 && binary.LittleEndian.Uint32(msg[:4]) == mediaMagic {
			c.statsMu.Lock()
			c.stats.ControlReplies++
			if binary.LittleEndian.Uint32(msg[4:8]) == 1 {
				c.stats.AuthReplies++
				c.stats.AuthReplyZero = len(msg) >= 12 && binary.LittleEndian.Uint32(msg[8:12]) == 0
			}
			c.statsMu.Unlock()
			continue
		}
		cmd, ts, long, payload, ok := mediaPayload(msg)
		if !ok {
			c.count(&c.stats.Malformed)
			continue
		}
		if long {
			c.count(&c.stats.LongForm)
		} else {
			c.count(&c.stats.ShortForm)
		}
		switch cmd {
		case CmdMediaVideo:
			if len(payload) > 1 {
				switch payload[0] & 31 {
				case 7:
					c.count(&c.stats.SPS)
				case 8:
					c.count(&c.stats.PPS)
				case 5:
					c.count(&c.stats.Keyframes)
				case 28:
					if payload[1]&0x9f == 0x85 {
						c.count(&c.stats.Keyframes)
					}
				}
			}
			c.count(&c.stats.Video)
			if c.onFrame != nil {
				c.count(&c.stats.Frames)
				c.onFrame(parseVideo(msg, ts, payload))
			}
		case CmdMediaAudio:
			c.statsMu.Lock()
			c.stats.AudioBytes += len(payload)
			c.statsMu.Unlock()
			c.count(&c.stats.Audio)
			if c.onAudio != nil {
				c.onAudio(parseAudio(msg, ts, payload))
			}
		default:
			c.countOther(cmd)
		}
	}
}

// keepAlive holds the signalling session open; the monitor drops an idle one.
func (c *Client) keepAlive(ctx context.Context) {
	ticker := time.NewTicker(HeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := c.session.Heartbeat(); err != nil {
				return
			}
		}
	}
}

// Close tears the session down.
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	if c.stopClose != nil {
		c.stopClose()
	}
	if c.cancel != nil {
		c.cancel()
	}
	if c.stream != nil {
		c.stream.Close()
	}
	for _, m := range c.media {
		m.Close()
	}
	if c.sock != nil {
		c.sock.Close()
	}
	if c.session != nil {
		return c.session.Close()
	}
	return nil
}

func sdpAttr(sdp, name string) string {
	for _, line := range strings.Split(strings.ReplaceAll(sdp, "\r\n", "\n"), "\n") {
		if strings.HasPrefix(line, "a="+name+":") {
			return strings.TrimPrefix(line, "a="+name+":")
		}
	}
	return ""
}

func parseCandidate(line string) (*net.UDPAddr, error) {
	line = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "a="))
	m := candidateRE.FindStringSubmatch(line)
	if m == nil {
		return nil, errors.New("lan: unusable candidate")
	}
	ip := net.ParseIP(m[5])
	if ip == nil {
		return nil, errors.New("lan: candidate carries no address")
	}
	port, err := strconv.Atoi(m[6])
	if err != nil {
		return nil, err
	}
	return &net.UDPAddr{IP: ip, Port: port}, nil
}

// Drain heartbeat acknowledgements and pushed DP status while media runs.
func (c *Client) drainSignals(ctx context.Context) {
	for ctx.Err() == nil {
		h, body, err := c.session.Recv(10 * time.Second)
		if err != nil {
			var n net.Error
			if errors.As(err, &n) && n.Timeout() {
				continue
			}
			c.statsMu.Lock()
			if errors.Is(err, io.EOF) {
				c.stats.SignalEOF = true
			} else {
				c.stats.SignalFormatErrors++
				c.stats.SignalError = "io"
				for _, kind := range []string{"prefix", "framing", "checksum", "padding", "block length", "short"} {
					if strings.Contains(err.Error(), kind) {
						c.stats.SignalError = kind
						break
					}
				}
				c.stats.SignalErrorCmd = c.session.LastCmd
				c.stats.SignalErrorLength = c.session.LastLength
				c.stats.SignalErrorPrefix = c.session.LastPrefix
			}
			c.statsMu.Unlock()
			return
		}
		if h.Cmd != CmdIPCLan302 {
			c.report(decodeDPS(body))
		}
	}
}
