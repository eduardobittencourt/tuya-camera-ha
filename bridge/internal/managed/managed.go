package managed

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/internal/registry"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/core"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/rtsp"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/tuya"
)

// BridgeConfig is the JSON shape written by the companion HA integration.
type BridgeConfig struct {
	UID         string   `json:"uid"`
	SigningKey  string   `json:"signing_key"`
	SID         string   `json:"sid"`
	Ecode       string   `json:"ecode"`
	Partner     string   `json:"partner"`
	AppKey      string   `json:"app_key"`
	ChKey       string   `json:"ch_key"`
	DeviceID    string   `json:"device_id"`
	PackageName string   `json:"package_name"`
	APIHost     string   `json:"api_host"`
	AppVersion  string   `json:"app_version"`
	SDKVersion  string   `json:"sdk_version"`
	DeviceCore  string   `json:"device_core_version"`
	TTID        string   `json:"ttid"`
	Channel     string   `json:"channel"`
	OSSystem    string   `json:"os_system"`
	Platform    string   `json:"platform"`
	AppRN       string   `json:"app_rn_version"`
	ET          string   `json:"et"`
	Timezone    string   `json:"timezone"`
	Talkback    bool     `json:"talkback"`
	BridgePort  int      `json:"bridge_port"`
	Cameras     []Camera `json:"cameras"`
}

// Camera is one entry under "cameras" in the JSON.
type Camera struct {
	Local     *registry.LocalMedia `json:"local_media"`
	ID        string               `json:"camera_id"`
	Name      string               `json:"camera_name"`
	ProductID string               `json:"product_id"`
}

func loadConfig(reader io.Reader) (BridgeConfig, error) {
	var cfg BridgeConfig
	data, err := io.ReadAll(io.LimitReader(reader, 1024*1024+1))
	if err != nil {
		return cfg, fmt.Errorf("read bridge configuration")
	}
	if len(data) > 1024*1024 {
		return cfg, fmt.Errorf("bridge config exceeds maximum size")
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("invalid bridge configuration")
	}
	return cfg, nil
}

// CameraWithPath pairs a Camera with the RTSP path it will be served on.
type CameraWithPath struct {
	Camera
	Path string
}

// assignPaths sanitizes each camera's name into an RTSP path and filters out
// invalid entries. Behavior:
//   - skip entries with empty camera_id (warn);
//   - skip later entries that repeat a previously-seen camera_id (warn) — a single
//     physical device must not be registered twice;
//   - when two distinct cameras sanitize to the same path, the second one gets
//     a suffix derived from up to 6 characters of its camera_id (warn).
func assignPaths(cams []Camera) []CameraWithPath {
	out := make([]CameraWithPath, 0, len(cams))
	seenIDs := make(map[string]bool, len(cams))
	seenPaths := make(map[string]bool, len(cams))
	for _, cam := range cams {
		if cam.ID == "" {
			core.Logger.Warn().Msgf("Camera config invalid: missing camera_id, skipping name=%q", cam.Name)
			continue
		}
		if seenIDs[cam.ID] {
			core.Logger.Warn().Msgf("Duplicate camera_id %q, skipping repeated entry name=%q", cam.ID, cam.Name)
			continue
		}
		seenIDs[cam.ID] = true

		basePath := registry.SanitizeRTSPPath(cam.Name, cam.ID)
		path := basePath
		if seenPaths[path] {
			suffix := cam.ID
			if len(suffix) > 6 {
				suffix = suffix[:6]
			}
			path = basePath + "_" + suffix
			i := 2
			for seenPaths[path] {
				path = fmt.Sprintf("%s_%s_%d", basePath, suffix, i)
				i++
			}
			core.Logger.Warn().Msgf("Path collision on %s, falling back to %s", basePath, path)
		}
		seenPaths[path] = true
		out = append(out, CameraWithPath{Camera: cam, Path: path})
	}
	return out
}

func validateConfig(cfg BridgeConfig) error {
	if cfg.SigningKey == "" {
		return fmt.Errorf("signing_key is required")
	}
	if cfg.SID == "" {
		return fmt.Errorf("sid is required")
	}
	if cfg.AppKey == "" {
		return fmt.Errorf("app_key is required")
	}
	if cfg.DeviceID == "" {
		return fmt.Errorf("device_id is required")
	}
	if cfg.Ecode == "" {
		return fmt.Errorf("ecode is required")
	}
	if cfg.Partner == "" {
		return fmt.Errorf("partner is required")
	}
	if len(cfg.Cameras) == 0 {
		return fmt.Errorf("cameras list is empty: nothing to serve")
	}
	return nil
}

func Run() (result error) {
	defer func() {
		if result != nil {
			event := "error"
			if tuya.IsAuthenticationError(result) {
				event = "auth_required"
			}
			emitManaged(map[string]interface{}{"event": event})
		}
	}()
	cfg, err := loadConfig(os.Stdin)
	if err != nil {
		return err
	}
	if err := validateConfig(cfg); err != nil {
		return err
	}
	camsWithPath := assignPaths(cfg.Cameras)
	if len(camsWithPath) == 0 {
		return fmt.Errorf("no valid cameras")
	}
	infos := make([]registry.CameraInfo, 0, len(camsWithPath))
	apiHost := tuya.NormalizeAPIHost(cfg.APIHost)
	chKey := cfg.ChKey
	if chKey == "" {
		chKey = "071d81fa"
	}
	client := tuya.NewMobileSDKClient(cfg.SigningKey, cfg.SID, cfg.AppKey, cfg.DeviceID, chKey)
	client.BaseURL = tuya.APIBaseURL(apiHost)
	client.Ecode = cfg.Ecode
	client.PartnerIdentity = cfg.Partner
	client.PackageName = cfg.PackageName
	client.ApplyAppProfile(tuya.AppProfile{
		AppVersion: cfg.AppVersion, SDKVersion: cfg.SDKVersion, DeviceCoreVersion: cfg.DeviceCore,
		TTID: cfg.TTID, Channel: cfg.Channel, OSSystem: cfg.OSSystem, Platform: cfg.Platform,
		AppRNVersion: cfg.AppRN, ET: cfg.ET,
	})
	if cfg.Timezone != "" {
		client.Timezone = cfg.Timezone
	}

	allLocal := true
	for _, camera := range camsWithPath {
		if camera.Local == nil {
			allLocal = false
		}
	}
	client.UID = cfg.UID
	if !allLocal {
		if _, err := client.Call("smartlife.p.time.get", "1.0", nil); err != nil {
			return fmt.Errorf("API verification failed: %w", err)
		}
		userInfo, err := client.GetUserInfo()
		if err != nil {
			return fmt.Errorf("get user info: %w", err)
		}
		client.UID = userInfo.ID
	}
	userKey := "account"

	for _, camera := range camsWithPath {
		skill := ""
		if camera.Local == nil {
			if err := client.P2PPreLink(camera.ID); err != nil {
				core.Logger.Warn().Err(err).Msgf("P2P pre-link failed while loading capabilities for %s", camera.Name)
			}
			if config, err := client.GetWebRTCConfig(camera.ID); err != nil {
				core.Logger.Warn().Err(err).Msgf("Could not load camera capabilities for RTSP SDP: %s", camera.Name)
			} else {
				skill = config.Result.Skill
			}
		}
		infos = append(infos, registry.CameraInfo{
			DeviceID: camera.ID, DeviceName: camera.Name, Category: "sp", ProductID: camera.ProductID,
			RTSPPath: camera.Path, UserKey: userKey, Skill: skill, Local: camera.Local, UID: client.UID,
		})
		core.Logger.Info().Msgf("Camera registered: name=%s path=%s", camera.Name, camera.Path)
	}
	store := registry.NewRegistry(infos)
	rtspServer := rtsp.NewRTSPServer(cfg.BridgePort, store)
	rtspServer.MobileClient = client
	rtspServer.ListenHost = "127.0.0.1"
	rtspServer.Talkback = cfg.Talkback
	rtspServer.OnStatus = func(id, state string, statusErr error) {
		event := "camera_status"
		if tuya.IsAuthenticationError(statusErr) {
			event = "auth_required"
		}
		emitManaged(map[string]interface{}{"event": event, "camera_id": id, "state": state})
	}
	if err := rtspServer.Start(); err != nil {
		return fmt.Errorf("start RTSP server: %w", err)
	}
	defer rtspServer.Stop()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	managedErrors := make(chan error, 1)
	cameras := make([]map[string]interface{}, 0, len(camsWithPath))
	for i, camera := range camsWithPath {
		var skill tuya.Skill
		_ = json.Unmarshal([]byte(infos[i].Skill), &skill)
		cameras = append(cameras, map[string]interface{}{"camera_id": camera.ID, "path": camera.Path, "hevc": camera.Local == nil && tuya.IsHEVC(&skill, tuya.GetStreamType(&skill, "hd")), "transport": mediaTransport(camera.Local)})
	}
	controlURL, stopControl, err := startLocalControl(ctx, rtspServer)
	if err != nil {
		return fmt.Errorf("start local controls")
	}
	defer stopControl()
	emitManaged(map[string]interface{}{"event": "ready", "source_port": rtspServer.GetPort(), "cameras": cameras, "local_control_url": controlURL})
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if allLocal {
					continue
				}
				if _, err := client.GetUserInfo(); tuya.IsAuthenticationError(err) {
					managedErrors <- err
					return
				}
			}
		}
	}()
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(sigChan)
	select {
	case <-sigChan:
		return nil
	case err := <-managedErrors:
		return err
	}
}

var managedOutputMu sync.Mutex

func emitManaged(event map[string]interface{}) {
	managedOutputMu.Lock()
	defer managedOutputMu.Unlock()
	_ = json.NewEncoder(os.Stdout).Encode(event)
}

func mediaTransport(local *registry.LocalMedia) string {
	if local != nil {
		return "lan"
	}
	return "cloud"
}
