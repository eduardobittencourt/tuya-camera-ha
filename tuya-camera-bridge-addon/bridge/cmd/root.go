package cmd

import (
	"fmt"
	"os"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd/addon"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd/auth"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd/cameras"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd/direct"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd/rtsp"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/storage"

	"github.com/spf13/cobra"
)

var (
	storageManager *storage.StorageManager
)

var rootCmd = &cobra.Command{
	Use:   "tuya-camera-bridge",
	Short: "Tuya Smart Camera RTSP Bridge",
	Long: `A CLI tool to connect Tuya Smart Cameras to RTSP clients.

This tool allows you to:
- Authenticate with Tuya Smart accounts
- Discover cameras
- Provide RTSP endpoints for your cameras

Examples:
  tuya-camera-bridge auth list
  tuya-camera-bridge auth add eu-central user@example.com
  tuya-camera-bridge cameras refresh
  tuya-camera-bridge rtsp start --port 8554`,
}

func Execute(version string) error {
	rootCmd.Version = version
	return rootCmd.Execute()
}

func init() {
	cobra.OnInitialize(initConfig)

	// Add subcommands
	rootCmd.AddCommand(auth.NewAuthCmd())
	rootCmd.AddCommand(cameras.NewCamerasCmd())
	rootCmd.AddCommand(rtsp.NewRTSPCmd())
	rootCmd.AddCommand(direct.NewDirectCmd())
	rootCmd.AddCommand(addon.NewAddonCmd())
}

func initConfig() {
	var err error
	storageManager, err = storage.NewStorageManager()
	if err != nil {
		fmt.Println("Failed to initialize storage")
		os.Exit(1)
	}

	// Make storage manager available to subcommands
	auth.SetStorageManager(storageManager)
	cameras.SetStorageManager(storageManager)
	rtsp.SetStorageManager(storageManager)
	direct.SetStorageManager(storageManager)
	addon.SetStorageManager(storageManager)
}

func GetStorageManager() *storage.StorageManager {
	return storageManager
}
