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

## Published release and HACS

The release was published from `be857c34efe34d1523edee4fc7b68ecbee4760a7`
after its exact-commit CI/validation passed. The workflow-produced ZIP and
checksum matched the candidate build. Stable v0.3.4 remained the stable channel.

HACS initially retained `tuya_camera_bridge` as its component path and read the
stable 0.3.4 manifest. Uninstalling/reloading did not clear that identity, and an
uninstalled repository did not retain its beta preference. With HACS disabled,
only this repository's public cached metadata was reconciled to the installed,
hash-verified beta and `selected_tag` was set to `v0.4.0b2`. HACS was enabled and
used to download the official release. The version was explicitly selected
again through its native API after download. All 44 installed files matched
that release; no HACS source patch was applied. Selecting beta versions for the
list alone does not select the manifest HACS reads during this transition.

After a cold Core restart and native HACS refresh, the installed version,
selected tag and domain remained v0.4.0b2 / v0.4.0b2 / `tuya_camera`. No former
component directory or account entry reappeared. Account data and entity/device
binding fingerprints still matched the pre-rename baseline (19 / 17 enabled).

The published installation decoded 703 H.264 video frames and 723 AAC audio
frames over 63.12 s. Six control calls/restorations passed (0.069–1.472 s).
Reload took 0.493 s, a fresh JPEG 2.413 s, and the camera returned to standby
with zero owned media processes. No camera integration warnings/errors or HACS
errors for this repository were found in the checked post-restart log window.

This HACS cache transition is an operator-assisted beta limitation. Keep the
explicit beta selection while the stable channel has the former domain, and
review the repository metadata when selecting another release. Manual ZIP
installation remains the fallback described in [installation](installation.md).
