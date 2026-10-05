# Tuya Camera Bridge

Go media bridge used by the Home Assistant integration and compatibility add-on.
It performs Tuya mobile API and MQTT signaling, establishes the camera WebRTC
session and exposes RTP media over RTSP.

The integration starts `addon --managed --config -` and sends its JSON contract
through stdin. Managed mode listens only on loopback, allocates its RTSP port
automatically and emits sanitized JSON lifecycle events. It does not run ONVIF
or MediaMTX. The integration owns process startup, recovery and shutdown.

```bash
go test ./...
CGO_ENABLED=0 go build -o tuya-camera-bridge .
# The standalone add-on owns this private configuration file:
./tuya-camera-bridge addon --config /data/bridge-config.json
```

The bridge derives from the MIT-licensed Avent WebRTC bridge. See `LICENSE` and
the repository-level `NOTICE`.
