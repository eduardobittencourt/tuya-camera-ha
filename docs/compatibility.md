# Camera compatibility

The integration targets Tuya Smart/Smart Life cameras that support the Tuya
mobile WebRTC protocol. Being listed in the app or discovered by this integration
does not prove that a camera can deliver media through that protocol.

## Tested devices

| Commercial model | Firmware | App | Camera source | Validated behavior | Status |
| --- | --- | --- | --- | --- | --- |
| [Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736)](https://www.positivocasainteligente.com.br/smart-camera-bateria-wifi-11188736/p) | 1.1.48 | Tuya Smart | HEVC 1920×1080; 16-bit PCM, 8 kHz mono | UI login, discovery, HLS video/audio, native HA WebRTC, fresh snapshots, automatic bridge recovery, image/sound on owner's phone | Working on HA OS 2026.9.4 amd64 with 0.3.0b1 |

This row describes a single tested unit. The owner identified its retail model
using the manufacturer listing above; firmware came from authenticated device
metadata. Firmware 1.1.48 is not a unique model identifier. The tested account
used Tuya Smart: login through the Positivo-branded app is not implemented.

This is a battery-powered model, but the test did not record its power state or
measure battery endurance, long idle/wake cycles or continuous day-long operation.
Live viewing can keep a battery camera awake and affect endurance. No battery,
motion, PTZ or talkback controls are exposed by this integration.

See [the validation report](validation-0.3.0b1.md) for measured results and
untested failure paths. H.264 and H.265 also have synthetic media coverage;
synthetic fixtures are not additional verified retail models.

## Supported features and limits

| Feature | Current implementation |
| --- | --- |
| H.264 video | Passed through without re-encoding |
| H.265/HEVC video | Converted to H.264 at 720p / 15 fps |
| Receive audio | Implemented G.711 paths and 16-bit PCM on the HEVC data-channel path; the real device tested used PCM |
| Snapshots | Fresh JPEG capture through FFmpeg |
| HLS / WebRTC | Native HA stream / go2rtc provider |
| PTZ, settings, two-way audio | Not exposed |
| MFA / interactive captcha | Not implemented |
| Offline operation | Not established; Tuya authentication/signaling require internet |

Other battery/low-power models, OEM-specific app accounts, NVRs, doorbells and
other audio codecs are not covered by the real-device test. Shared devices and regional account
variations may also affect discovery. Some Tuya cameras expose only a different
proprietary media transport and will not work with this bridge.

## Report your model

Use the [compatibility report form](https://github.com/eduardobittencourt/tuya-camera-ha/issues/new?template=compatibility_report.yml).
Include the retail brand/model, firmware, app, HA/integration versions and which
features actually worked. State whether a result is a short test or sustained use.
Reports should distinguish discovery from successful video/audio playback.

Do not include device IDs, serial numbers, product IDs, account details, local
keys, session data, signed URLs or private camera images. Public product links
and model names are enough. If a model name cannot be established, say so.
