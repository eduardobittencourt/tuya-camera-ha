<p align="center">
  <img src="custom_components/tuya_camera/brand/icon.png" alt="Tuya Camera icon" width="128">
</p>

<h1 align="center">Tuya Camera for Home Assistant</h1>

<p align="center">Connect compatible Tuya Smart and Smart Life cameras to Home Assistant.</p>

[![CI](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/ci.yml)
[![HACS validation](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/eduardobittencourt/tuya-camera-ha/actions/workflows/validate.yml)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Documentation](docs/README.md) · [Releases](https://github.com/eduardobittencourt/tuya-camera-ha/releases) · [Changelog](CHANGELOG.md)

## Features

- Native camera entities with live video, audio and fresh JPEG snapshots.
- HLS and WebRTC playback through Home Assistant's media components.
- Tuya Smart / Smart Life account login, camera discovery and reauthentication.
- H.264 passthrough and H.265-to-H.264 conversion for playback.
- Model-dependent [LAN controls and telemetry](docs/guides/entities.md).

Camera protocols run in Python inside the integration, using Home Assistant's
FFmpeg executable. Setup is through the UI; no separate add-on, ONVIF setup,
Tuya developer project or manually copied device IDs are required.

## Requirements

- **Home Assistant 2026.9 or newer on Linux.**
- A compatible camera already linked to a Tuya Smart or Smart Life account.
- Internet access for Tuya authentication and signaling, and for dependency installation.
- FFmpeg with H.264/AAC encoding support; Home Assistant OS and Container include it.

## Installation

Available in the **default HACS catalog**.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

1. Open **HACS**, search for **Tuya Camera** and download the latest stable release.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Tuya Camera**.

See [installation](docs/guides/installation.md) for manual setup and
[migration notes](docs/guides/migrations.md) for upgrades from **Tuya Camera Bridge**.

## Configuration

Select **Tuya Smart** or **Smart Life** and enter the account, password and country
calling code used in that app (`55` for Brazil). Open a discovered camera and
enable sound in the player. Use **Reconfigure** to refresh the camera list or
sign in again; session expiry can also trigger Home Assistant reauthentication.

## Compatibility and limitations

The **Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736)** has
been tested. See the [compatibility guide](docs/guides/compatibility.md) for firmware,
verified features and evidence. Discovery alone does not establish playback support.

- Private Tuya mobile APIs can change; model, firmware and app account affect compatibility.
- Internet is required for authentication and signaling. Media can be direct or
  relayed through TURN; fully offline operation is not established.
- PTZ, two-way audio and interactive MFA/captcha are not supported.
- Battery cameras may need cloud wake; long idle/wake cycles and battery endurance
  remain unverified. The first snapshot can exceed Home Assistant's timeout.
- H.265 conversion uses software encoding and can be expensive on small hosts.

## Support and security

Start with [troubleshooting](docs/guides/troubleshooting.md) and [support](SUPPORT.md).
Use the issue forms for bugs and compatibility reports. Never publish credentials,
session data, camera IDs, raw captures, private images or HA backups.

The account password is used for login and is not saved. Sessions are stored in
HA's private storage; protect configuration and backups. Internal media listeners
use loopback; remote playback goes through Home Assistant authentication.
Report vulnerabilities privately through [SECURITY.md](SECURITY.md).

## Contributing

Compatibility reports, documentation fixes and code contributions are welcome.
See [CONTRIBUTING.md](CONTRIBUTING.md), [development](docs/development/testing.md)
and the [Code of Conduct](CODE_OF_CONDUCT.md).

## License and attribution

Original code is MIT licensed. Upstream notices for aventproxy/Avent and the
vendored `tuya-mobile` library are preserved in [LICENSE](LICENSE) and [NOTICE](NOTICE).
Tuya names and artwork belong to their respective owners; see
[brand assets](custom_components/tuya_camera/BRAND_ASSETS.md).
This independent community project is not affiliated with or endorsed by Tuya
or Home Assistant.
