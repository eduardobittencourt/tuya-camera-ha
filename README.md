# Tuya Camera Bridge for Home Assistant

Home Assistant integration and companion add-on for Tuya Smart and Smart Life
cameras that use Tuya's mobile WebRTC signaling path. It turns the on-demand
camera session into RTSP and exposes a native Home Assistant `camera` entity.

## Architecture

```text
Home Assistant config flow
  ├─ password login (password stays in memory)
  ├─ camera discovery and selection
  └─ /config/tuya_camera_bridge_<entry>.json (0600)
         │
         ▼
Tuya Camera Bridge add-on
  ├─ Tuya mobile API session
  ├─ MQTT wake-up and signaling
  ├─ WebRTC / TURN media session
  └─ RTSP :38554
         │
         ▼
Home Assistant CameraEntity → stream / go2rtc / dashboard
```

The account password is submitted only during setup or reauthentication and is
not stored in the config entry, add-on options, logs or bridge configuration.
The session, regional endpoint and selected camera are stored so normal Home
Assistant and add-on restarts do not require another login.

## Current scope

- Tuya Smart and Smart Life account namespaces.
- Email or telephone password login.
- Explicit country calling code; Brazil defaults to `55`.
- One account and one selected camera per installation in the current release.
- H.265/H.264 video and G.711 audio through the Go bridge.
- Native Home Assistant camera entity with streaming and snapshots.

Interactive captcha and MFA are detected but not yet completed inside the config
flow. Accounts requiring either step must complete it in the mobile app first.

## Installation

This repository contains two installable parts:

1. Add the repository to HACS as an **Integration** custom repository and install
   **Tuya Camera Bridge**.
2. Add the same URL to the Home Assistant add-on store and install the
   **Tuya Camera Bridge** add-on.
3. Start the add-on. It waits safely for the integration configuration.
4. Add the integration in **Settings → Devices & services** and select the same
   app namespace and country used by the mobile app.

## Security

The integration writes live Tuya session material to `/config` with mode `0600`.
The add-on has no password option. Logs must never include passwords, session
IDs, encryption codes, local keys or signed request payloads.

## Development

```bash
pytest
ruff check custom_components tests
docker run --rm -v "$PWD/bridge:/src" -w /src golang:1.26-bookworm \
  bash -c 'gofmt -w . && go test ./... && CGO_ENABLED=0 go build -o tuya-camera-bridge .'
```

## Credits and license

MIT licensed. The media bridge derives from
[aventproxy](https://github.com/thekoma/aventproxy) and its Avent WebRTC bridge.
The vendored `tuya-mobile` implementation retains its own MIT license under the
vendor directory. See [NOTICE](NOTICE).
