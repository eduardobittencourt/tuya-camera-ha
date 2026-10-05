# Stable release validation

The stable release preparation on 2026-10-05 used Home Assistant OS with Core
2026.9.4, HACS 2.0.5 and Linux amd64, with the same Positivo battery camera and
Tuya Smart account documented in [the beta report](validation-0.3.0b1.md).
This report contains no credentials, identifiers, private URLs or camera media.

## Stable 0.3.0 installation

The complete CI suite and official HACS/hassfest validators passed on release
commit `3b6d16565dea9fdf242430f86653cc75031ac3b1` before publication. Public ZIP
and executable checksums matched reproducible Go 1.26.8 builds.

A Home Assistant backup was completed before installation. Betas were disabled
for this repository in HACS, which offered and downloaded the stable release.
All 33 installed files matched the published ZIP exactly. HA configuration
validation passed and Core was restarted.

The stable executable was absent before restart, so startup downloaded it from
the public release rather than reusing a cached binary. Its checksum matched
the packaged pin and permissions were `0700`. The existing config entry and
camera entity remained; the account/session data was unchanged. HACS reported
v0.3.0 installed with no pending upgrade and betas disabled.

- Native HA WebRTC received actual H.264 video and Opus audio.
- HLS delivered 10 distinct fragments over approximately 65 seconds, with zero
  request/decode failures; video was H.264 1280x720, audio AAC mono.
- Three warm snapshot requests returned valid, distinct JPEGs.
- Unauthenticated camera image requests were rejected with HTTP 403.
- HACS, Tuya, Intelbras, Motorola and MQTT entries loaded after restart.

## Cold snapshot finding and correction

Initial snapshots after restart failed. Reproducing this after an official
integration reload gave three HTTP 500 responses at approximately 10.02,
10.02 and 10.01 seconds, while playback and warm snapshots worked.

Home Assistant imposes a ten-second image-request deadline. FFmpeg's default
input analysis adds latency to the Tuya signaling and first-frame wait. The
snapshot command now bounds analysis to one second and 512,000 bytes, leaving
more of the deadline for connection establishment. See the
[FFmpeg format options](https://ffmpeg.org/ffmpeg-formats.html#Format-Options).

The candidate Python module was temporarily installed for diagnosis and Core
was restarted to load it. Three subsequent cold cycles, each resetting the
integration through its official reload API before requesting an image, returned
valid JPEGs with HTTP 200 in 9.85, 5.96 and 6.00 seconds. These are observations
on this device/network, not guaranteed timing for other cameras or connections.

The H.264/H.265 synthetic media tests now request a snapshot as the first media
consumer under the same ten-second deadline. Final release validation must also
use the published HACS package, replacing the temporary diagnostic module.

## Limits

This is not a blank HA installation or a new account-login test. It covers the
existing account, camera and migration path; the original login was tested in
the beta report. AArch64 assets are built and checksum-verified, but the live
Home Assistant is amd64. Day-long reliability, battery endurance, WAN failure
and other camera models remain outside this validation.
