package main

import (
	"fmt"
	"os"

	"github.com/eduardobittencourt/tuya-camera-ha/bridge/cmd"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/core"
)

var VERSION = "0.3.0b1"

func main() {
	core.InitLogger()

	if err := cmd.Execute(VERSION); err != nil {
		fmt.Println("Command execution failed")
		os.Exit(1)
	}
}
