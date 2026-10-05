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
snapshot command now accepts only video and skips frame-rate sampling, which
is unnecessary for a single image. Analysis is bounded to one second and
512,000 bytes, leaving more of the deadline for connection establishment. See the
[FFmpeg format options](https://ffmpeg.org/ffmpeg-formats.html#Format-Options).

An initial candidate Python module with the bounded probe was temporarily installed for diagnosis and Core
was restarted to load it. Three subsequent cold cycles, each resetting the
integration through its official reload API before requesting an image, returned
valid JPEGs with HTTP 200 in 9.85, 5.96 and 6.00 seconds. These are observations
on this device/network, not guaranteed timing for other cameras or connections.

The H.264/H.265 synthetic media tests now request a snapshot as the first media
consumer under the same ten-second deadline. Both codec tests and all other CI
jobs passed on release commit `52bba2af75a2906ffe746167d68345d2551341d8` before
publication.

## Published 0.3.1 reinstallation

The integration was disabled and its package removed through HACS. The component
directory was confirmed absent and no managed bridge process remained. The
existing configuration entry was preserved. With betas disabled, HACS offered
v0.3.1 and installed it through the normal download flow without selecting a
version manually. All 33 files matched the published ZIP exactly.

HA configuration validation passed and Core was restarted to replace the
in-memory diagnostic module with the public release. Startup downloaded the
previously absent v0.3.1 executable, whose SHA256 matched the packaged pin and
whose permissions were `0700`. The existing camera entity and account/session
data were preserved. HACS, Tuya, Intelbras, Motorola and MQTT entries loaded.

Five cold-image trials each reloaded the integration before requesting an image.
Three returned valid JPEGs with HTTP 200 in 5.72, 9.42 and 6.08 seconds. Two
returned HTTP 500 at 10.49 and 10.02 seconds. **Cold snapshots remain intermittent
when camera wake-up/signaling exceeds HA's ten-second deadline.** The probe
change improves latency but does not eliminate this limitation. These results
supersede the initial candidate's three successful trials; they are not a
promise of reliable first-image timing.

A first simultaneous HLS/native-WebRTC attempt after the cold-image tests failed
with an HLS request timeout and a WebRTC negotiation error. Sequential retries
succeeded; simultaneous viewer startup is not established by this validation.

- Native HA WebRTC received actual H.264 video and Opus audio.
- HLS delivered 13 distinct fragments over approximately 65 seconds, with zero
  decode failures; video was H.264 1280x720 and audio AAC.
- Two warm snapshot requests returned valid, distinct JPEGs.
- Unauthenticated camera image requests returned HTTP 403.
- HACS reported v0.3.1 installed, v0.3.1 available and betas disabled, with no
  manually selected tag. HA was RUNNING and one managed bridge process remained.
- Temporary diagnostic modules and synthetic test tools were removed from HA.


## Published 0.3.2 catalog compatibility fix

The catalog's hassfest job initially failed before running Docker: its helper
searches the entire clone for `*manifest.json`, so it counted `binary_manifest.json`
as a second integration manifest. The checksum file was renamed to
`bridge_checksums.json`, its reader and release tooling were updated, and the
repository check now rejects ambiguous catalog discovery.

Both push and PR CI suites and official HACS/hassfest validators passed on
release commit `ec8cda1de4f4f226101c7612790c615d0f029ce5` before publication.
Downloaded release assets matched the reviewed source and executable pins.
The HACS catalog PR subsequently passed all 12 checks, including hassfest.

The existing v0.3.1 installation was upgraded through HACS's normal stable flow
with betas disabled. All 33 files matched the public v0.3.2 ZIP, with no extra
files (including no obsolete checksum manifest). Configuration validation passed
and Core was restarted. The previously absent v0.3.2 executable was downloaded
automatically; SHA256 and `0700` permissions matched expectations. The account
configuration remained unchanged, one managed bridge process remained, and all
five integration entries loaded again.

Native HA WebRTC again received actual H.264 video and Opus audio. Two warm
snapshots returned distinct valid JPEGs with HTTP 200 in 0.94 and 1.85 seconds;
an unauthenticated request returned HTTP 403. HACS reported v0.3.2 installed and
available, no manual tag selected and betas disabled. HA was RUNNING with no
active FFmpeg relay processes after the probes. The cold-image limitation and
simultaneous-viewer uncertainty observed on v0.3.1 remain applicable: this
release changes checksum discovery/version metadata, not media behavior.

## Limits

This is not a blank HA installation or a new account-login test. It covers the
existing account, camera and migration path; the original login was tested in
the beta report. AArch64 assets are built and checksum-verified, but the live
Home Assistant is amd64. Day-long reliability, battery endurance, WAN failure
and other camera models remain outside this validation.
