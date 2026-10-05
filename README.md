<p align="center">
  <img src="custom_components/tuya_camera_bridge/brand/logo.png" alt="Tuya" width="220">
</p>

# Tuya Camera Bridge for Home Assistant

[![CI](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/ci.yml)
[![HACS validation](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/validate.yml)
[![HACS custom integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://www.hacs.dev/docs/faq/custom_repositories/)
[![Home Assistant 2026.9+](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-blue.svg)](https://www.home-assistant.io/)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Connect compatible Tuya Smart and Smart Life cameras from the Home Assistant
UI.** Sign in with the account used in the mobile app; the integration discovers
cameras and manages the media bridge automatically.

[Português brasileiro](docs/README.pt-BR.md) · [Installation](docs/installation.md) ·
[Compatibility](docs/compatibility.md) · [Troubleshooting](docs/troubleshooting.md)

## What you get

- Native camera entities, live video with audio, and fresh JPEG snapshots.
- HLS streaming and WebRTC through Home Assistant's provider.
- Account login, camera discovery, reconfiguration and session reauthentication.
- A bridge installed with checksum verification and restarted after a crash.
- H.264 passthrough; H.265 converted to H.264 at 720p / 15 fps for playback.
- Setup through the UI: no separate add-on, ONVIF configuration or manual IDs.

**This is a beta using Tuya's private mobile APIs.** Compatibility depends on
camera model and firmware. Internet is required for Tuya authentication and
signaling; media can travel directly or through TURN. This project does not
promise offline/local-only operation or compatibility with every Tuya camera.
PTZ, two-way audio, camera settings and interactive MFA/captcha are not supported.

## Install with HACS

Published beta: [0.3.0b1](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.3.0b1).
HACS installation and automatic bridge download have been verified on HA OS
2026.9.4; see the [validation report](docs/validation-0.3.0b1.md).

Requires **Home Assistant 2026.9+ on Linux amd64 or AArch64**, an existing HACS
installation, and FFmpeg. Home Assistant OS and Container include FFmpeg;
other Linux installations must provide a build with H.264/AAC encoding support.

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

1. Add `https://github.com/eduardobittencourt/tuya-camera-ha` under **HACS → Custom
   repositories**, selecting **Integration**.
2. Select a published release; enable beta versions for `0.3.0b1`. Download it
   and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Tuya Camera Bridge**.
4. Select **Tuya Smart** or **Smart Life**, then enter the same account, password
   and country calling code as the app (`55` for Brazil).
5. Open a discovered camera and enable sound in the player.

Use a **published release**. A draft release is not downloadable by the public,
and a development checkout may reference unpublished bridge files. First setup
and upgrades need GitHub access to download the matching executable. The verified
cache is reused on later starts. See [installation and migration](docs/installation.md).

This repository can be added manually to HACS; it is not currently listed in the
HACS default catalog. Passing validation is separate from catalog acceptance.

## Tested cameras

**Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736), firmware
1.1.48**, tested using Tuya Smart, has passed live video, audio, snapshots,
automatic bridge recovery and playback on the owner's phone. The owner identified
the model from its [manufacturer listing](https://www.positivocasainteligente.com.br/smart-camera-bateria-wifi-11188736/p).
Battery endurance and long idle/wake cycles have not been measured. This is one
tested unit, not a guarantee for every firmware or other Tuya camera.

See the [compatibility table](docs/compatibility.md) and
[beta validation report](docs/validation-0.3.0b1.md). Report another model with the
[compatibility form](https://github.com/eduardobittencourt/tuya-camera-ha/issues/new?template=compatibility_report.yml).

## How it runs

The Python integration supervises a small Go subprocess that handles Tuya
signaling and camera WebRTC. A private RTSP endpoint feeds an on-demand FFmpeg
relay, which provides H.264/AAC to Home Assistant. These processes run inside
the HA environment and use CPU/RAM, especially when converting H.265 video.

For the tested camera, one HLS viewer used about 120 MiB for bridge plus relay,
with roughly 65–74% of one CPU core. This excludes the rest of HA and is not a
guarantee for other cameras or multiple viewers.

Read [architecture](docs/architecture.md) for process lifecycle and transport
choices. The standalone add-on remains a [legacy compatibility path](tuya-camera-bridge-addon/DOCS.md).

## Privacy and support

The account password is used for login and is not saved. Sessions are sensitive
and stored in HA's `.storage`; treat backups as private. RTSP and relay HTTP
listen on loopback, and remote access goes through HA authentication.

Use [troubleshooting](docs/troubleshooting.md) and [support](SUPPORT.md) before
opening an issue. Never publish credentials, tokens, `.storage`, raw bridge
captures, camera IDs or private images. Report security problems through
[private vulnerability reporting](SECURITY.md).

## Contributing

Compatibility reports, documentation fixes and code contributions are welcome.
See [CONTRIBUTING.md](CONTRIBUTING.md), [development](docs/development.md),
[release preparation](docs/releasing.md) and the [code of conduct](CODE_OF_CONDUCT.md).
Changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Credits

Community project maintained by [Eduardo Bittencourt](https://github.com/eduardobittencourt).
Software is MIT licensed; original notices for aventproxy/Avent and the vendored
`tuya-mobile` library are preserved. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Tuya names and images belong to their respective owners. The project is not
affiliated with or endorsed by Tuya or Home Assistant. [Image provenance](custom_components/tuya_camera_bridge/BRAND_ASSETS.md).
