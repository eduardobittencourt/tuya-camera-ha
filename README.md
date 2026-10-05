# Tuya Camera Bridge for Home Assistant

A custom integration for Tuya Smart and Smart Life cameras using Tuya's mobile
WebRTC protocol. Install through HACS, sign in once, and all compatible cameras
appear as native Home Assistant camera entities. No separate add-on, ONVIF setup,
manual device IDs or YAML are required by the integration.

**0.3.0b1 is a beta.** Camera compatibility still depends on the model and
firmware. Authentication and signaling require Tuya's internet services; this
is not an offline camera integration. Media may use a direct connection or TURN.

## Installation

Requires Home Assistant **2026.9 or newer**, running on **Linux amd64 or
AArch64**. Home Assistant OS and Container include FFmpeg. Other Linux setups
must already have an FFmpeg build with H.264/AAC encoding support.

1. Add `https://github.com/eduardobittencourt/tuya-camera-ha` as an **Integration**
   custom repository in HACS.
2. Enable beta releases if installing `0.3.0b1`, download the integration and
   restart Home Assistant.
3. In **Settings → Devices & services → Add integration**, choose **Tuya Camera
   Bridge**.
4. Select Tuya Smart or Smart Life and enter the same account, password and
   country calling code as the mobile app (`55` for Brazil).

The integration downloads a version-pinned bridge for the host architecture,
verifies its embedded SHA-256 checksum, and manages it automatically. First
setup and upgrades need access to GitHub Releases. A verified cached executable
is reused on subsequent restarts. Use a published release: development branches
may reference bridge assets that have not been published yet.

## How it works

```text
Native Home Assistant integration
  ├─ Account login, discovery and reauthentication
  ├─ Session in Home Assistant's config entry; password is never saved
  ├─ Managed Go bridge (session passed through stdin)
  │    ├─ Tuya mobile API / MQTT signaling
  │    ├─ Camera WebRTC / TURN connection
  │    └─ RTSP on an automatically allocated loopback port
  └─ FFmpeg relay on a private loopback HTTP endpoint
       ├─ H.264 copied without video re-encoding
       ├─ H.265 converted to H.264 at 720p / 15 fps
       └─ Receive-only audio converted to AAC
             ↓
       Native camera entities, snapshots, HLS and HA's WebRTC provider
```

FFmpeg runs on demand, with up to four streaming consumers per camera. Native
HA streaming normally shares a stream between viewers. Opening the camera in
multiple independent consumers can create additional FFmpeg processes. Snapshots
start a short-lived decoder and always request a fresh frame: a failed capture
does not return an old cached image. Camera wake-up can take several seconds.

The integration restarts a crashed bridge with bounded backoff, reports received
video and connection errors, and requests reauthentication when a recognized
Tuya session-expiry error occurs. Once a connection error is detected, periodic
camera updates try to recover it. Standby means the bridge is ready but nobody
has requested media; it does not assert that the camera is reachable.

Use **Reconfigure** on the integration entry to sign in again and rediscover
cameras. MFA and interactive captcha are not implemented. A challenge completed
in the mobile app does not guarantee that the add-on/integration login will be
accepted. Tuya's private APIs and public app profiles can change.

Two-way audio, PTZ and camera settings are not exposed by this integration.

## Security and removal

RTSP and HTTP listen only on `127.0.0.1`, using ephemeral ports. HTTP stream URLs
include a random path. Remote viewing goes through Home Assistant authentication;
the integration does not open camera ports on the LAN. Loopback does not isolate
processes already running inside the same HA container.

Account sessions are sensitive and are stored by Home Assistant in `.storage`.
The Go bridge receives its session via stdin, rather than arguments or a
persistent bridge JSON. Runtime metadata and verified binaries live under
`.storage/tuya_camera_bridge`. Passwords and raw bridge output are excluded from
logs and diagnostics. Unloading the entry stops the bridge and media processes;
removing it also removes its account runtime directory. The shared verified
binary cache is retained for other accounts.

The old HACS integration's version-1 entries migrate automatically, preserving
camera IDs. Its obsolete root-level bridge JSON is removed. Existing standalone
add-on/ONVIF installations are not automatically removed: stop the old add-on
when switching and remove its old ONVIF entities separately to avoid duplicates.
The add-on source remains available for compatibility.

## Development and validation

Use Python 3.14 and Go 1.26.8 (the pinned release toolchain):

```bash
pip install '.[test]'
ruff check custom_components tuya-camera-bridge-addon/app tests scripts
pytest -m 'not media'
cd tuya-camera-bridge-addon/bridge
go test -race ./...
cd ../..
python scripts/package_release.py
```

Real media tests use a synthetic RTSP camera and check H.264, H.265, audio,
native HA HLS, snapshots and source disconnection:

```bash
TEST_FFMPEG_BINARY=/usr/bin/ffmpeg \
TEST_MEDIAMTX_BINARY=/path/to/mediamtx \
pytest -m media --timeout=90
```

For the WebRTC receive test, also set `TEST_GO2RTC_BINARY` to go2rtc 1.9.14 and
`TEST_WEBRTC_PROBE` to the executable built with
`go build -o /tmp/webrtc-probe ./internal/testmedia/webrtc` from the bridge
directory. This checks H.264 video and Opus audio using the same two-source
arrangement as HA's go2rtc provider. CI runs this extended test for both codecs.

MediaMTX is only a development test fixture for the new integration. CI also
builds the compatibility add-on Docker image. Release packaging produces amd64
and arm64 executables, their SHA-256 checksums and `tuya_camera_bridge.zip`.
`package_release.py --verify` fails when source/toolchain changes make a binary
differ from the committed manifest. After changing Go code, regenerate the
manifest before releasing. The release workflow creates a **draft** for review.

The intended HEVC/PCM camera has also been tested on HA OS; see the
[beta validation report](docs/validation-0.3.0b1.md) for results and limits.

Automated tests do not replace verification with the intended Tuya camera:
check mobile login, wake-up, live video/audio, source/network interruption,
restarts and sustained resource usage before relying on a beta.

## Credits and license

MIT licensed. The media bridge derives from
[aventproxy](https://github.com/thekoma/aventproxy) and its Avent WebRTC bridge.
The vendored `tuya-mobile` implementation retains its MIT license. See `NOTICE`.
