package addon

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/signal"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/core"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/onvifproxy"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/rtsp"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/storage"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/tuya"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/utils"
)

// BridgeConfig is the JSON shape written by the companion HA integration.
type BridgeConfig struct {
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
	ID        string `json:"camera_id"`
	Name      string `json:"camera_name"`
	ProductID string `json:"product_id"`
}

func loadConfig(path string) (BridgeConfig, error) {
	var cfg BridgeConfig
	var data []byte
	var err error
	if path == "-" {
		data, err = io.ReadAll(io.LimitReader(os.Stdin, 1024*1024+1))
	} else {
		data, err = os.ReadFile(path)
	}
	if len(data) > 1024*1024 {
		return cfg, fmt.Errorf("bridge config exceeds maximum size")
	}
	if err != nil {
		return cfg, fmt.Errorf("read %s: %w", path, err)
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("parse %s: %w", path, err)
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

		basePath := storage.SanitizeRTSPPath(cam.Name, cam.ID)
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

func validateConfigForMode(cfg BridgeConfig, externalSource bool) error {
	if externalSource {
		if len(cfg.Cameras) == 0 {
			return fmt.Errorf("cameras list is empty: nothing to serve")
		}
		return nil
	}
	return validateConfig(cfg)
}

var storageManager *storage.StorageManager

func SetStorageManager(sm *storage.StorageManager) {
	storageManager = sm
}

func NewAddonCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "addon",
		Short: "Run the multi-camera bridge driven by the HA integration JSON",
		Long: `Read the bridge config JSON written by the Tuya Camera Bridge integration
and serve every camera under it from one RTSP server, each on its own path.

Example:
  tuya-camera-bridge addon --config /config/tuya_camera_bridge_<entry_id>.json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			err := runAddon(cmd, args)
			managed, _ := cmd.Flags().GetBool("managed")
			if managed && err != nil {
				event := "error"
				if tuya.IsAuthenticationError(err) {
					event = "auth_required"
				}
				emitManaged(map[string]interface{}{"event": event})
			}
			return err
		},
	}
	cmd.Flags().Bool("managed", false, "Integration-managed loopback RTSP with JSON status events and stdin config")
	cmd.Flags().String("config", "", "Path to the bridge config JSON written by the HA integration")
	cmd.Flags().Bool("onvif", false, "Expose each camera as an ONVIF H.264 device")
	cmd.Flags().Int("onvif-port", 8081, "First ONVIF HTTP port (one consecutive port per camera)")
	cmd.Flags().Int("onvif-rtsp-port", 38555, "RTSP port for ONVIF H.264 streams")
	cmd.Flags().String("onvif-username", "admin", "ONVIF username")
	cmd.Flags().String("onvif-password", "", "ONVIF password")
	cmd.Flags().String("data-dir", "/data", "Persistent add-on data directory")
	cmd.Flags().Bool("external-source", false, "Use an already-running Tuya RTSP source (diagnostic mode)")
	cmd.Flags().String("source-host", "127.0.0.1", "Host of the Tuya RTSP source")
	cmd.MarkFlagRequired("config")
	return cmd
}

func runAddon(cmd *cobra.Command, args []string) error {
	cfgPath, _ := cmd.Flags().GetString("config")
	onvifEnabled, _ := cmd.Flags().GetBool("onvif")
	managed, _ := cmd.Flags().GetBool("managed")
	if managed && onvifEnabled {
		return fmt.Errorf("managed mode cannot expose ONVIF")
	}
	externalSource, _ := cmd.Flags().GetBool("external-source")

	cfg, err := loadConfig(cfgPath)
	if err != nil {
		return err
	}
	if err := validateConfigForMode(cfg, externalSource); err != nil {
		return fmt.Errorf("invalid config %s: %w", cfgPath, err)
	}

	port := cfg.BridgePort
	if port == 0 && !managed {
		port = 38554
	}

	camsWithPath := assignPaths(cfg.Cameras)
	if len(camsWithPath) == 0 {
		return fmt.Errorf("no valid cameras after filtering, refusing to start")
	}

	infos := make([]storage.CameraInfo, 0, len(camsWithPath))
	pathLog := make([]string, 0, len(camsWithPath))
	for _, camera := range camsWithPath {
		pathLog = append(pathLog, camera.Path)
	}

	var client *tuya.MobileSDKClient
	if !externalSource {
		apiHost := tuya.NormalizeAPIHost(cfg.APIHost)
		chKey := cfg.ChKey
		if chKey == "" {
			chKey = "071d81fa"
		}
		client = tuya.NewMobileSDKClient(cfg.SigningKey, cfg.SID, cfg.AppKey, cfg.DeviceID, chKey)
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

		core.Logger.Info().Msgf("Tuya API host: %s", apiHost)
		if _, err := client.Call("smartlife.p.time.get", "1.0", nil); err != nil {
			return fmt.Errorf("API verification failed: %w", err)
		}
		userInfo, err := client.GetUserInfo()
		if err != nil {
			return fmt.Errorf("get user info: %w", err)
		}
		core.Logger.Info().Msgf("User: %s (%s)", userInfo.Nickname, utils.MaskEmail(userInfo.Email))
		client.UID = userInfo.ID
		userKey := "addon_" + strings.ReplaceAll(strings.ReplaceAll(userInfo.Email, "@", "_at_"), ".", "_")
		userSession := &tuya.SessionData{
			LoginResult: &tuya.LoginResult{Uid: userInfo.ID, Email: userInfo.Email, Nickname: userInfo.Nickname, Domain: userInfo.Domain},
			ServerHost:  apiHost, Region: "addon", UserEmail: userInfo.Email,
		}
		if err := storageManager.SaveUser("addon", userInfo.Email, userSession); err != nil {
			core.Logger.Warn().Msgf("Could not save user session: %v", err)
		}
		for _, camera := range camsWithPath {
			skill := ""
			if err := client.P2PPreLink(camera.ID); err != nil {
				core.Logger.Warn().Err(err).Msgf("P2P pre-link failed while loading capabilities for %s", camera.Name)
			}
			if config, err := client.GetWebRTCConfig(camera.ID); err != nil {
				core.Logger.Warn().Err(err).Msgf("Could not load camera capabilities for RTSP SDP: %s", camera.Name)
			} else {
				skill = config.Result.Skill
			}
			infos = append(infos, storage.CameraInfo{
				DeviceID: camera.ID, DeviceName: camera.Name, Category: "sp", ProductID: camera.ProductID,
				RTSPPath: camera.Path, UserKey: userKey, Skill: skill,
			})
			core.Logger.Info().Msgf("Camera registered: name=%s path=%s", camera.Name, camera.Path)
		}
		if err := storageManager.UpdateCamerasForUser(userKey, infos); err != nil {
			core.Logger.Warn().Msgf("Could not save cameras: %v", err)
		}
	} else {
		infos = make([]storage.CameraInfo, len(camsWithPath))
	}

	var rtspServer *rtsp.RTSPServer
	if !externalSource {
		rtspServer = rtsp.NewRTSPServer(port, storageManager)
		rtspServer.MobileClient = client
		if managed {
			rtspServer.ListenHost = "127.0.0.1"
			rtspServer.OnStatus = func(id, state string, statusErr error) {
				event := "camera_status"
				if tuya.IsAuthenticationError(statusErr) {
					event = "auth_required"
				}
				emitManaged(map[string]interface{}{"event": event, "camera_id": id, "state": state})
			}
		}
		rtspServer.Talkback = cfg.Talkback
		if cfg.Talkback {
			core.Logger.Info().Msg("Two-way audio enabled: streams will ask the camera for talkback")
		}
		if err := rtspServer.Start(); err != nil {
			return fmt.Errorf("start RTSP server: %w", err)
		}
		defer rtspServer.Stop()
		port = rtspServer.GetPort()
		core.Logger.Info().Msgf("Serving %d cameras on port %d: %s", len(infos), port, strings.Join(pathLog, " "))
	} else {
		core.Logger.Info().Msgf("Using external Tuya RTSP source on port %d: %s", port, strings.Join(pathLog, " "))
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var gateway *onvifproxy.Gateway
	if onvifEnabled {
		onvifPort, _ := cmd.Flags().GetInt("onvif-port")
		onvifRTSPPort, _ := cmd.Flags().GetInt("onvif-rtsp-port")
		onvifUsername, _ := cmd.Flags().GetString("onvif-username")
		onvifPassword, _ := cmd.Flags().GetString("onvif-password")
		dataDir, _ := cmd.Flags().GetString("data-dir")
		sourceHost, _ := cmd.Flags().GetString("source-host")
		proxyCameras := make([]onvifproxy.Camera, 0, len(camsWithPath))
		for _, camera := range camsWithPath {
			proxyCameras = append(proxyCameras, onvifproxy.Camera{
				ID: camera.ID, Name: camera.Name, SourcePath: camera.Path,
				ProxyPath: proxyPath(camera.ID),
			})
		}
		gateway, err = onvifproxy.New(onvifproxy.Config{
			Cameras: proxyCameras, SourceHost: sourceHost, SourcePort: port, RTSPPort: onvifRTSPPort,
			ONVIFBasePort: onvifPort, Username: onvifUsername, Password: onvifPassword,
			DataDir: dataDir,
		})
		if err != nil {
			return fmt.Errorf("configure ONVIF gateway: %w", err)
		}
		if err := gateway.Start(ctx); err != nil {
			return fmt.Errorf("start ONVIF gateway: %w", err)
		}
		defer gateway.Stop()
		core.Logger.Info().Msgf("ONVIF gateway enabled on ports %d-%d; H.264 RTSP on %d", onvifPort, onvifPort+len(proxyCameras)-1, onvifRTSPPort)
	}

	managedErrors := make(chan error, 1)
	if managed {
		cameras := make([]map[string]interface{}, 0, len(camsWithPath))
		for i, camera := range camsWithPath {
			var skill tuya.Skill
			_ = json.Unmarshal([]byte(infos[i].Skill), &skill)
			cameras = append(cameras, map[string]interface{}{"camera_id": camera.ID, "path": camera.Path, "hevc": tuya.IsHEVC(&skill, tuya.GetStreamType(&skill, "hd"))})
		}
		emitManaged(map[string]interface{}{"event": "ready", "source_port": port, "cameras": cameras})
		if client != nil {
			go func() {
				ticker := time.NewTicker(5 * time.Minute)
				defer ticker.Stop()
				for {
					select {
					case <-ctx.Done():
						return
					case <-ticker.C:
						if _, err := client.GetUserInfo(); tuya.IsAuthenticationError(err) {
							managedErrors <- err
							return
						}
					}
				}
			}()
		}
	}
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(sigChan)
	if gateway == nil {
		select {
		case <-sigChan:
		case err := <-managedErrors:
			return err
		}
	} else {
		select {
		case <-sigChan:
		case gatewayErr := <-gateway.Errors():
			return gatewayErr
		}
	}

	core.Logger.Info().Msg("Shutting down...")
	return nil
}

var nonPathCharacter = regexp.MustCompile(`[^a-zA-Z0-9]+`)

func proxyPath(cameraID string) string {
	id := nonPathCharacter.ReplaceAllString(cameraID, "")
	if len(id) > 16 {
		id = id[:16]
	}
	if id == "" {
		id = "camera"
	}
	return "tuya_" + id
}

var managedOutputMu sync.Mutex

func emitManaged(event map[string]interface{}) {
	managedOutputMu.Lock()
	defer managedOutputMu.Unlock()
	_ = json.NewEncoder(os.Stdout).Encode(event)
}
