# Compatibility

[Documentation index](../README.md)

## Tested model

The Positivo Casa Inteligente **Smart Câmera Wi-Fi com Bateria (11188736)**,
firmware **1.1.48**, has been tested through Tuya Smart. Confirmed features include
account discovery, local H.264/PCM media, cloud HEVC/PCM media, live video/audio,
fresh snapshots, LAN settings and telemetry, reload and standby.

The [0.4.0 stable release](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.4.0)
uses the physical-device baseline from 0.4.0b2 on Home Assistant Core 2026.10.4,
Linux amd64. This is the baseline carried into stable promotion, not a separate
post-publication test. See the immutable
[release validation record](https://github.com/eduardobittencourt/tuya-camera-ha/blob/b6a317bf04f5b96d598bd34b2e07c4769c6c5c60/docs/validation-0.4.0.md#promotion-baseline).

This describes one unit. Firmware is not a unique model identifier. Positivo's
own branded account login is not implemented. Synthetic H.264/H.265 tests do
not establish support for additional retail models.

## Supported behavior and limits

- H.264 passes through; H.265 is converted to H.264 at 720p / 15 fps.
- Received audio includes implemented G.711 and PCM paths. Other codecs are not guaranteed.
- HLS and WebRTC playback use HA's native media components.
- Settings and telemetry are LAN-only, created from valid reports and capabilities.
- PTZ, two-way audio and interactive MFA/captcha are not exposed.
- Tuya private APIs can change. Model, firmware, app and regional accounts affect compatibility.

## Internet and battery cameras

Authentication and signaling require the Tuya service. Sleeping cameras may need
cloud wake even when media uses the LAN. Fully offline operation is not supported
as a guaranteed mode. LAN controls do not provide a cloud-independent wake path.

Battery endurance, prolonged idle/wake cycles, multi-day reliability, other
battery models, NVRs, doorbells and OEM accounts are not established. Live viewing
or frequent snapshots can keep a camera awake. The first image request can time
out while the device wakes; see [troubleshooting](troubleshooting.md).

## Report another model

Use the repository's compatibility issue form. Include retail model, firmware,
app, HA/integration versions and the features actually exercised. Distinguish
discovery, playback, controls and sustained use. Do not publish device IDs,
serials, local keys, signed URLs or private images.
