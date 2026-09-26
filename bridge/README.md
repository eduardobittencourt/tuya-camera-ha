# Tuya Camera Bridge

Go media bridge used by the companion Home Assistant add-on. It consumes the
owner-only JSON contract written by the integration, performs Tuya mobile API
and MQTT signaling, establishes the camera WebRTC session and exposes RTP media
over RTSP.

```bash
go test ./...
CGO_ENABLED=0 go build -o tuya-camera-bridge .
./tuya-camera-bridge addon --config /path/to/tuya_camera_bridge_entry.json
```

The bridge derives from the MIT-licensed Avent WebRTC bridge. See `LICENSE` and
the repository-level `NOTICE`.
