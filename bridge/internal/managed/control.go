package managed

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/rtsp"
	"io"
	"log"
	"net"
	"net/http"
	"time"
)

func startLocalControl(ctx context.Context, media *rtsp.RTSPServer) (string, func(), error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return "", nil, err
	}
	var token [24]byte
	if _, err = rand.Read(token[:]); err != nil {
		listener.Close()
		return "", nil, err
	}
	path := "/" + hex.EncodeToString(token[:])
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != path || r.Method != "POST" {
			http.NotFound(w, r)
			return
		}
		var request struct {
			Camera    string `json:"camera_id"`
			Operation string `json:"operation"`
			Index     string `json:"index"`
			IDs       []int  `json:"ids"`
			Value     any    `json:"value"`
		}
		if json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192)).Decode(&request) != nil {
			w.WriteHeader(400)
			return
		}
		result, err := media.LocalRequest(request.Camera, request.Operation, request.Index, request.IDs, request.Value)
		if err != nil {
			w.WriteHeader(503)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"dps": result})
	})
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 3 * time.Second, WriteTimeout: 3 * time.Second, IdleTimeout: 5 * time.Second, ErrorLog: log.New(io.Discard, "", 0)}
	go server.Serve(listener)
	stop := func() { server.Close() }
	go func() { <-ctx.Done(); stop() }()
	return "http://" + listener.Addr().String() + path, stop, nil
}
