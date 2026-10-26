# Tuya Camera rename beta validation — 0.4.0b2

This beta renames the integration to **Tuya Camera**, the domain/directory to
`tuya_camera` and the HACS archive to `tuya_camera.zip`. Python protocols,
TinyTuya and the other declared dependencies remain unchanged from 0.4.0b1.
The repository and HACS repository identity remain `tuya-camera-ha`.

## Automated validation

73 Python tests passed using the new package namespace, including actual HA
config flows, platform setup, controls, reload/unload and protocol peer tests.
Three real synthetic-media tests passed with FFmpeg, HLS/WebRTC and encrypted
Tuya LAN media. Ruff, dependency consistency, release gate and archive checks
passed. Packaging rejects a leftover `tuya_camera_bridge` component directory.

## Existing installation

The candidate was installed on HA Core 2026.10.4, Linux amd64, using the same
Positivo battery camera as the [Python migration](validation-0.4.0b1.md).
An explicitly authorized offline registry migration was performed with Core
stopped. This operator procedure is not a runtime dependency or an automatic
migration shipped in the integration; see [installation](installation.md).

- The old component directory and empty legacy binary-cache directory were
  removed. The new `tuya_camera` entry loaded after Core startup; no old-domain
  account entry remained.
- The account entry ID, account provisioning data, all 19 entity registry
  identities and the device identity/associations were preserved. The same
  17 entities remained enabled. Sanitized fingerprints were compared before
  and after; no private configuration was exported.
- LAN HLS decoded 761 H.264 video frames and 783 AAC audio frames over 64.78 s.
- Six native HA setting changes/restorations were confirmed. The cold first
  call took 6.349 s; the others took 0.084–0.204 s. Night vision, PIR and
  sensitivity were restored to off, off and 7 respectively.
- Integration reload completed in 0.333 s and a fresh JPEG in 1.985 s. After
  consumers settled, standby and zero owned media processes were confirmed,
  including an independent check of actual FFmpeg processes.
- No integration warnings/errors were observed in the checked runtime log.

No camera image, video/audio recording, raw protocol payload or credential was
persisted. This naming change does not expand model compatibility, offline wake
or battery-endurance claims. The aiortc development pin and other limitations in
[architecture](architecture.md#dependencies-and-compatibility) still apply.
