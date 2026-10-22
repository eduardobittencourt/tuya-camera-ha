// Package core provides an internal logger. Operational status is emitted through
// the managed JSON protocol; dependency logs must never expose session material.
package core

import (
	"github.com/rs/zerolog"
	"io"
)

var Logger = zerolog.New(io.Discard)

func InitLogger() zerolog.Logger {
	Logger = zerolog.New(io.Discard)
	return Logger
}
