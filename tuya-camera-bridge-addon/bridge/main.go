package main

import (
	"fmt"
	"os"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/core"
)

const VERSION = "0.0.6"

func main() {
	core.InitLogger()

	if err := cmd.Execute(VERSION); err != nil {
		fmt.Println("Command execution failed")
		os.Exit(1)
	}
}
