package onvifproxy

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/mickeyzzc/onvif-go/v2/server"
	"github.com/mickeyzzc/onvif-go/v2/server/provider"
)

const (
	defaultWidth     = 1280
	defaultHeight    = 720
	defaultFramerate = 15
	defaultBitrate   = 1200
)

// Camera describes one Tuya RTSP source and its stable public proxy path.
type Camera struct {
	ID         string
	Name       string
	SourcePath string
	ProxyPath  string
}

// Config controls the ONVIF facade and the on-demand H.264 relay.
type Config struct {
	Cameras       []Camera
	SourceHost    string
	SourcePort    int
	RTSPPort      int
	ONVIFBasePort int
	Username      string
	Password      string
	DataDir       string
	MediaMTXBin   string
	FFmpegBin     string
	Logger        *slog.Logger
}

// Gateway owns MediaMTX, one ONVIF server per camera, and their discovery responders.
type Gateway struct {
	cfg        Config
	cancel     context.CancelFunc
	mediaMTX   *exec.Cmd
	responders []*discoveryResponder
	wg         sync.WaitGroup
	errors     chan error
}

func New(cfg Config) (*Gateway, error) {
	if len(cfg.Cameras) == 0 {
		return nil, errors.New("at least one camera is required")
	}
	if cfg.SourcePort == 0 {
		cfg.SourcePort = 38554
	}
	if cfg.SourceHost == "" {
		cfg.SourceHost = "127.0.0.1"
	}
	if cfg.RTSPPort == 0 {
		cfg.RTSPPort = 8554
	}
	if cfg.ONVIFBasePort == 0 {
		cfg.ONVIFBasePort = 8081
	}
	if cfg.DataDir == "" {
		cfg.DataDir = "/data"
	}
	if cfg.MediaMTXBin == "" {
		cfg.MediaMTXBin = "mediamtx"
	}
	if cfg.FFmpegBin == "" {
		cfg.FFmpegBin = "ffmpeg"
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.New(slog.NewTextHandler(os.Stdout, nil))
	}
	for i, camera := range cfg.Cameras {
		if camera.ID == "" || camera.Name == "" || camera.SourcePath == "" || camera.ProxyPath == "" {
			return nil, fmt.Errorf("camera %d has an empty required field", i)
		}
	}
	return &Gateway{cfg: cfg, errors: make(chan error, len(cfg.Cameras)+1)}, nil
}

func (g *Gateway) Start(parent context.Context) error {
	ctx, cancel := context.WithCancel(parent)
	g.cancel = cancel
	advertiseHost := multicastAddress()
	if net.ParseIP(advertiseHost) == nil || advertiseHost == "0.0.0.0" {
		cancel()
		return errors.New("could not determine the LAN address used for ONVIF")
	}

	configPath, err := g.writeMediaMTXConfig()
	if err != nil {
		cancel()
		return err
	}
	g.mediaMTX = exec.CommandContext(ctx, g.cfg.MediaMTXBin, configPath)
	g.mediaMTX.Stdout = os.Stdout
	g.mediaMTX.Stderr = os.Stderr
	if err := g.mediaMTX.Start(); err != nil {
		cancel()
		return fmt.Errorf("start MediaMTX: %w", err)
	}
	g.wg.Add(1)
	go func() {
		defer g.wg.Done()
		if err := g.mediaMTX.Wait(); err != nil && ctx.Err() == nil {
			g.errors <- fmt.Errorf("MediaMTX exited: %w", err)
		}
	}()

	for i, camera := range g.cfg.Cameras {
		if err := g.startCamera(ctx, camera, g.cfg.ONVIFBasePort+i, advertiseHost); err != nil {
			g.Stop()
			return err
		}
	}
	return nil
}

func (g *Gateway) Errors() <-chan error { return g.errors }

func (g *Gateway) Stop() {
	if g.cancel != nil {
		g.cancel()
	}
	for _, responder := range g.responders {
		responder.Stop()
	}
	g.wg.Wait()
}

func (g *Gateway) startCamera(ctx context.Context, camera Camera, port int, advertiseHost string) error {
	token := "profile_" + camera.ProxyPath
	scopes := []string{
		"onvif://www.onvif.org/type/video_encoder",
		"onvif://www.onvif.org/Profile/Streaming",
		"onvif://www.onvif.org/name/" + url.PathEscape(camera.Name),
		"onvif://www.onvif.org/hardware/tuya-camera-bridge",
		"onvif://www.onvif.org/mac/" + stableHardwareID(camera.ID),
	}
	cfg := &server.Config{
		Host: "0.0.0.0", Port: port, BasePath: "/onvif", Timeout: 30 * time.Second,
		AdvertiseHost: advertiseHost,
		DeviceInfo: server.DeviceInfo{
			Manufacturer: "Tuya Camera Bridge", Model: "Virtual ONVIF Camera",
			FirmwareVersion: "0.2.0", SerialNumber: camera.ID, HardwareID: camera.ID,
		},
		Username: g.cfg.Username, Password: g.cfg.Password, Scopes: scopes,
		SupportPTZ: false, SupportImaging: false,
		Profiles: []server.ProfileConfig{{
			Token: token, Name: camera.Name,
			VideoSource: server.VideoSourceConfig{
				Token: "source_" + camera.ProxyPath, Name: camera.Name,
				Resolution: server.Resolution{Width: defaultWidth, Height: defaultHeight},
				Framerate:  defaultFramerate,
			},
			VideoEncoder: server.VideoEncoderConfig{
				Encoding: "H264", Resolution: server.Resolution{Width: defaultWidth, Height: defaultHeight},
				Quality: 75, Framerate: defaultFramerate, Bitrate: defaultBitrate, GovLength: 30,
			},
			Snapshot: server.SnapshotConfig{
				Enabled: true, Resolution: server.Resolution{Width: defaultWidth, Height: defaultHeight}, Quality: 80,
			},
		}},
		Logger: g.cfg.Logger,
	}
	backend := &cameraProvider{
		camera: camera, rtspPort: g.cfg.RTSPPort, ffmpegBin: g.cfg.FFmpegBin,
		cachePath: filepath.Join(g.cfg.DataDir, "snapshots", camera.ProxyPath+".jpg"),
		ctx:       ctx, logger: g.cfg.Logger,
	}
	srv, err := server.New(cfg, server.WithStreamURIProvider(backend), server.WithSnapshotProvider(backend))
	if err != nil {
		return fmt.Errorf("create ONVIF server for %s: %w", camera.Name, err)
	}
	listener, err := net.Listen("tcp4", fmt.Sprintf("0.0.0.0:%d", port))
	if err != nil {
		return fmt.Errorf("listen on ONVIF port %d for %s: %w", port, camera.Name, err)
	}
	responder := newDiscoveryResponder("urn:uuid:"+stableUUID(camera.ID), scopes, port, multicastInterface())
	if err := responder.Start(ctx); err != nil {
		_ = listener.Close()
		return fmt.Errorf("start ONVIF discovery for %s: %w", camera.Name, err)
	}
	g.responders = append(g.responders, responder)
	g.wg.Add(1)
	go func() {
		defer g.wg.Done()
		if err := serveONVIF(ctx, srv.Handler(), listener, stableHardwareID(camera.ID), advertiseHost); err != nil && ctx.Err() == nil {
			g.errors <- fmt.Errorf("ONVIF server for %s exited: %w", camera.Name, err)
		}
	}()
	backend.refreshAsync()
	g.cfg.Logger.Info("ONVIF camera started", "camera", camera.Name, "port", port, "rtsp_path", camera.ProxyPath)
	return nil
}

func serveONVIF(ctx context.Context, next http.Handler, listener net.Listener, hardwareID, address string) error {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "invalid SOAP request", http.StatusBadRequest)
			return
		}
		r.Body = io.NopCloser(bytes.NewReader(body))
		if bytes.Contains(body, []byte("GetNetworkInterfaces")) {
			w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
			_, _ = fmt.Fprintf(w, `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body><tds:GetNetworkInterfacesResponse><tds:NetworkInterfaces token="lan"><tt:Enabled>true</tt:Enabled><tt:Info><tt:Name>lan</tt:Name><tt:HwAddress>%s</tt:HwAddress><tt:MTU>1500</tt:MTU></tt:Info><tt:IPv4><tt:Enabled>true</tt:Enabled><tt:Config><tt:Manual><tt:Address>%s</tt:Address><tt:PrefixLength>24</tt:PrefixLength></tt:Manual><tt:DHCP>true</tt:DHCP></tt:Config></tt:IPv4></tds:NetworkInterfaces></tds:GetNetworkInterfacesResponse></s:Body></s:Envelope>`, hardwareID, address)
			return
		}
		next.ServeHTTP(w, r)
	})
	httpServer := &http.Server{Handler: handler, ReadHeaderTimeout: 10 * time.Second}
	errorChannel := make(chan error, 1)
	go func() { errorChannel <- httpServer.Serve(listener) }()
	select {
	case <-ctx.Done():
		shutdownContext, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return httpServer.Shutdown(shutdownContext)
	case err := <-errorChannel:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}

func multicastInterface() string {
	localIP := net.ParseIP(multicastAddress())
	if localIP == nil {
		return ""
	}
	interfaces, err := net.Interfaces()
	if err != nil {
		return ""
	}
	for _, iface := range interfaces {
		addresses, _ := iface.Addrs()
		for _, address := range addresses {
			ip, _, parseErr := net.ParseCIDR(address.String())
			if parseErr == nil && ip.Equal(localIP) {
				return iface.Name
			}
		}
	}
	return ""
}

func multicastAddress() string {
	connection, err := net.DialUDP("udp", nil, &net.UDPAddr{IP: net.ParseIP("239.255.255.250"), Port: 3702})
	if err != nil {
		return ""
	}
	defer connection.Close()
	return connection.LocalAddr().(*net.UDPAddr).IP.String()
}

func (g *Gateway) writeMediaMTXConfig() (string, error) {
	if err := os.MkdirAll(g.cfg.DataDir, 0o700); err != nil {
		return "", fmt.Errorf("create data directory: %w", err)
	}
	var b strings.Builder
	fmt.Fprintf(&b, "logLevel: info\nrtspAddress: :%d\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\nmoq: false\npathDefaults:\n  source: publisher\npaths:\n", g.cfg.RTSPPort)
	for _, camera := range g.cfg.Cameras {
		sourceURL := (&url.URL{Scheme: "rtsp", Host: fmt.Sprintf("%s:%d", g.cfg.SourceHost, g.cfg.SourcePort), Path: camera.SourcePath}).String()
		publishURL := (&url.URL{Scheme: "rtsp", Host: fmt.Sprintf("127.0.0.1:%d", g.cfg.RTSPPort), Path: "/" + camera.ProxyPath}).String()
		command := strings.Join([]string{
			g.cfg.FFmpegBin, "-hide_banner", "-loglevel", "warning", "-rtsp_transport", "tcp", "-i", sourceURL,
			"-map", "0:v:0", "-an", "-vf", "scale=-2:720,fps=15", "-c:v", "libx264", "-preset", "ultrafast",
			"-tune", "zerolatency", "-pix_fmt", "yuv420p", "-g", "30", "-b:v", "1200k",
			"-rtsp_transport", "tcp", "-f", "rtsp", publishURL,
		}, " ")
		fmt.Fprintf(&b, "  %s:\n    runOnDemand: %s\n    runOnDemandRestart: true\n    runOnDemandStartTimeout: 30s\n    runOnDemandCloseAfter: 15s\n", camera.ProxyPath, strconv.Quote(command))
	}
	path := filepath.Join(g.cfg.DataDir, "mediamtx.yml")
	if err := os.WriteFile(path, []byte(b.String()), 0o600); err != nil {
		return "", fmt.Errorf("write MediaMTX config: %w", err)
	}
	return path, nil
}

type cameraProvider struct {
	camera     Camera
	rtspPort   int
	ffmpegBin  string
	cachePath  string
	ctx        context.Context
	logger     *slog.Logger
	captureMu  sync.Mutex
	stateMu    sync.Mutex
	refreshing bool
}

func (p *cameraProvider) Stream(string) (provider.StreamInfo, error) {
	return provider.StreamInfo{RTSPPath: "/" + p.camera.ProxyPath, RTSPPort: p.rtspPort}, nil
}

func (p *cameraProvider) Snapshot(string) (provider.SnapshotResult, error) {
	if data, err := p.cachedSnapshot(); err == nil {
		p.refreshAsync()
		return provider.SnapshotResult{Data: data, ContentType: "image/jpeg"}, nil
	}
	return p.captureSnapshot(false)
}

func (p *cameraProvider) refreshAsync() {
	p.stateMu.Lock()
	if p.refreshing {
		p.stateMu.Unlock()
		return
	}
	p.refreshing = true
	p.stateMu.Unlock()
	go func() {
		defer func() {
			p.stateMu.Lock()
			p.refreshing = false
			p.stateMu.Unlock()
		}()
		var err error
		for attempt := 1; attempt <= 3; attempt++ {
			if _, err = p.captureSnapshot(true); err == nil || p.ctx.Err() != nil {
				return
			}
			select {
			case <-p.ctx.Done():
				return
			case <-time.After(time.Duration(attempt*2) * time.Second):
			}
		}
		if err != nil {
			p.logger.Warn("could not refresh ONVIF snapshot cache", "camera", p.camera.Name, "error", err)
		}
	}()
}

func (p *cameraProvider) captureSnapshot(force bool) (provider.SnapshotResult, error) {
	p.captureMu.Lock()
	defer p.captureMu.Unlock()
	if !force {
		if data, err := p.cachedSnapshot(); err == nil {
			return provider.SnapshotResult{Data: data, ContentType: "image/jpeg"}, nil
		}
	}
	ctx, cancel := context.WithTimeout(p.ctx, 25*time.Second)
	defer cancel()
	streamURL := fmt.Sprintf("rtsp://127.0.0.1:%d/%s", p.rtspPort, p.camera.ProxyPath)
	cmd := exec.CommandContext(ctx, p.ffmpegBin, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", streamURL, "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1")
	var output bytes.Buffer
	cmd.Stdout = &output
	if err := cmd.Run(); err != nil {
		return provider.SnapshotResult{}, fmt.Errorf("capture snapshot: %w", err)
	}
	data := output.Bytes()
	if len(data) < 4 || data[0] != 0xff || data[1] != 0xd8 {
		return provider.SnapshotResult{}, errors.New("snapshot command returned invalid JPEG data")
	}
	if err := p.storeSnapshot(data); err != nil {
		return provider.SnapshotResult{}, err
	}
	return provider.SnapshotResult{Data: data, ContentType: "image/jpeg"}, nil
}

func (p *cameraProvider) cachedSnapshot() ([]byte, error) {
	data, err := os.ReadFile(p.cachePath)
	if err != nil {
		return nil, err
	}
	if len(data) < 4 || data[0] != 0xff || data[1] != 0xd8 {
		return nil, errors.New("cached snapshot is not a JPEG")
	}
	return data, nil
}

func (p *cameraProvider) storeSnapshot(data []byte) error {
	directory := filepath.Dir(p.cachePath)
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return fmt.Errorf("create snapshot cache: %w", err)
	}
	temporary, err := os.CreateTemp(directory, ".snapshot-*")
	if err != nil {
		return fmt.Errorf("create temporary snapshot: %w", err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o600); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("protect temporary snapshot: %w", err)
	}
	if _, err := temporary.Write(data); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("write temporary snapshot: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("sync temporary snapshot: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close temporary snapshot: %w", err)
	}
	if err := os.Rename(temporaryPath, p.cachePath); err != nil {
		return fmt.Errorf("replace cached snapshot: %w", err)
	}
	return nil
}

func stableUUID(value string) string {
	sum := sha256.Sum256([]byte(value))
	// Set RFC 4122 version/variant bits so clients that validate the endpoint
	// reference accept it, while retaining a deterministic ID per camera.
	sum[6] = (sum[6] & 0x0f) | 0x40
	sum[8] = (sum[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", sum[0:4], sum[4:6], sum[6:8], sum[8:10], sum[10:16])
}

func stableHardwareID(value string) string {
	sum := sha256.Sum256([]byte(value))
	return fmt.Sprintf("%02X%02X%02X%02X%02X%02X", sum[0], sum[1], sum[2], sum[3], sum[4], sum[5])
}
