# Tuya Camera Bridge for Home Assistant

A standalone Home Assistant add-on for Tuya Smart and Smart Life cameras that
use Tuya's mobile WebRTC signaling path. The add-on authenticates with Tuya,
discovers the cameras, converts their video to H.264 on demand and exposes each
camera as a standard ONVIF device. No HACS integration is required.

## Architecture

```text
Tuya Camera Bridge add-on
  ├─ Ingress setup UI (password stays in memory)
  ├─ Tuya account and camera discovery
  ├─ private session storage in /data (0600)
  ├─ Tuya mobile API session
  ├─ MQTT wake-up and signaling
  ├─ WebRTC / TURN media session
  ├─ H.265 → H.264 transcode on demand
  └─ ONVIF + RTSP on the local network
         │
         ▼
Home Assistant built-in ONVIF integration → camera entities
```

The account password is submitted only during setup and is never written to
disk. The session, regional endpoint and discovered cameras are stored in the
add-on's private data directory so normal Home Assistant and add-on restarts do
not require another login.

## Current scope

- Tuya Smart and Smart Life account namespaces.
- Email or telephone password login.
- Explicit country calling code; Brazil defaults to `55`.
- One account and all compatible cameras discovered in that account.
- H.264 video exposed through an ONVIF Profile S facade.
- Native Home Assistant camera entities, live streaming and snapshots.
- On-demand transcoding: CPU is used only while a stream or snapshot is open.

Interactive captcha and MFA are detected but cannot currently be completed in
the add-on. Accounts requiring either step must complete it in the mobile app
first. This project relies on Tuya's private mobile APIs, so app-side changes can
require a bridge update.

## Installation

1. Add this repository URL to the Home Assistant add-on store.
2. Install and start **Tuya Camera Bridge**.
3. Open the add-on web UI, choose Tuya Smart or Smart Life, and enter the same
   account and country code used in the mobile app.
4. Home Assistant discovers one ONVIF device per camera. Confirm each device in
   **Settings → Devices & services**. ONVIF is built into Home Assistant.

The add-on warms and persists one snapshot after startup. Home Assistant can
show that image immediately while the camera wakes and the on-demand H.264 relay
starts; the cache is refreshed in the background and survives restarts.

## Security

Live Tuya session material is stored only under the add-on's private `/data`
directory with mode `0600`; the add-on no longer maps Home Assistant's `/config`.
The Ingress UI is protected by Home Assistant authentication and sends no-cache
and restrictive browser security headers. ONVIF/RTSP are currently unauthenticated
on the local network so Home Assistant can adopt discovered cameras without a
second credential step. Do not expose ports 8081+, 8554 or 38554 to the
internet.

## Development

```bash
pytest
ruff check custom_components tuya-camera-bridge-addon/app tests
docker run --rm -v "$PWD/tuya-camera-bridge-addon/bridge:/src" -w /src golang:1.26-bookworm \
  bash -c 'gofmt -w . && go test ./... && CGO_ENABLED=0 go build -o tuya-camera-bridge .'
```

## Credits and license

MIT licensed. The media bridge derives from
[aventproxy](https://github.com/thekoma/aventproxy) and its Avent WebRTC bridge.
The vendored `tuya-mobile` implementation retains its own MIT license under the
vendor directory. See [NOTICE](NOTICE).
