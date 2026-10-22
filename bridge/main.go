package main

import (
	"fmt"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/internal/managed"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/core"
	"os"
)

var VERSION = "dev"

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println(VERSION)
		return
	}
	if len(os.Args) != 1 {
		fmt.Fprintln(os.Stderr, "This executable is managed by Home Assistant and accepts configuration on stdin.")
		os.Exit(2)
	}
	core.InitLogger()
	if err := managed.Run(); err != nil {
		os.Exit(1)
	}
}
