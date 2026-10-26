# Changelog

## Unreleased

- Update English and Brazilian Portuguese installation instructions and badges
  for the HACS default catalog, including guidance for existing installations.
- Refresh stable-release links to 0.3.4 and document ongoing catalog maintenance.
- Run HACS and hassfest validation daily to detect upstream requirement changes.

## 0.3.4 — Native LAN media and confirmed battery-camera controls

- Add native protocol-3.3 LAN signaling and AES/KCP media, attempting LAN first
  and using cloud wake when the camera is sleeping. Cloud wake remains required;
  LAN talkback and fully offline daily operation are not validated.
- Share one Go signaling/DP socket with Python controls through private loopback
  IPC. Omit DP refresh queries on this media path because they interrupt the
  tested firmware; retain spontaneous reports and fresh command confirmations.
- Correct the local H.264 picture clock and PCM16 mono audio rate to 8 kHz;
  validate continuous video/audio, HLS, snapshots and native HA controls before
  and after integration reload, restoring original settings after each test.
- On the TinyTuya control path, request readable scalar DPs once per connection
  and receive their delayed reports, restoring night vision/PIR discovery.
- Drain initial LAN reports before the first battery command, use the account
  UID in CONTROL, and wait for its report without a second refresh overtaking it.
- Keep unrelated restored observations from blocking a battery command while
  still requiring a current report for the requested setting and confirmation.
- Retry an unanswered initial battery-setting read once before sending CONTROL,
  within the existing command deadline and without polling during standby.
- Remove the standalone add-on, Docker image, ONVIF gateway and independent CLI;
  move the Go executable into `bridge/` with stdin-only configuration, loopback
  listeners and an in-memory camera registry.

- Discover settings and telemetry only after valid camera reports, disable
  legacy unconfirmed entities while preserving their IDs and user choices, and
  restore timestamped settings as well as sensors during battery standby.
- Disable battery-camera motion/sound entities by default because sleeping
  cameras cannot provide continuous LAN events.
- Share on-demand LAN telemetry sessions with snapshots/video on battery cameras,
  receive asynchronous initial states and command confirmations, and close the
  socket after media use without background polling during standby.
- Retain timestamped last observations while asleep and restore telemetry sensors
  through Home Assistant; serialize and coalesce command-triggered media wakeups.

- Bind the managed talkback UDP RTP/RTCP listeners to loopback, including after
  stream reconnection.
- Import TinyTuya's discovery scanner explicitly so discovery does not depend
  on another integration having imported that submodule first.

## 0.3.3 — LAN entity setup fixes

- Fix local sensor registration: platform-specific sensor attributes no longer
  fall back to an incompatible generic entity description.
- Include schema-driven LAN controls and telemetry previously tested as a local
  development patch. Existing account and camera identities are preserved.
- Test native HA registration and values for battery, power source, SD status
  and scaled formatting progress alongside local switch/select/number services.
- Keep LAN commands and telemetry local, with no cloud fallback. Cameras that
  reject the local protocol still expose unavailable controls.
- Rebuild both checksum-pinned executables with the aligned 0.3.3 version.

A camera that is offline or has a depleted battery must be brought online before
video can resume. This release does not change camera wake-up or media signaling.

## 0.3.2 — HACS catalog manifest discovery

- Rename the executable checksum file to `bridge_checksums.json` so the HACS
  catalog finds exactly one integration manifest before running hassfest.
- Add a repository check for ambiguous manifest discovery.
- Rebuild both pinned executables with the aligned 0.3.2 version.
- Preserve the snapshot changes and documented cold-start limitations in 0.3.1.

## 0.3.1 — Faster snapshots after startup

- Probe only video and skip frame-rate sampling for snapshots.
- Bound FFmpeg snapshot input analysis to leave time for Tuya signaling within
  Home Assistant's ten-second image request deadline.
- Test the first H.264/H.265 snapshot before opening any video consumer.
- Rebuild both checksum-pinned executables with the aligned 0.3.1 version.

## 0.3.0 — Stable HACS release

- Publish the validated managed integration as a stable release installable
  through HACS without enabling beta versions.
- Preserve the media, authentication and process lifecycle behavior from 0.3.0b1.
- Align integration, package and executable versions at 0.3.0 and rebuild both
  Linux architectures with pinned SHA-256 checksums.
- Let the release workflow distinguish stable versions from prereleases.

Compatibility remains limited to the documented camera protocols and tested
model. Tuya internet access is required; PTZ, two-way audio and interactive
MFA/captcha remain unsupported.

## 0.3.0b1 — Managed integration beta

- Configure all compatible cameras from a Tuya account in the Home Assistant UI.
- Automatically download and verify the Go bridge for Linux amd64/AArch64.
- Manage startup, crash recovery, reauthentication, unloading and removal.
- Replace the integration's separate add-on/ONVIF/MediaMTX requirement with a
  private RTSP bridge and on-demand FFmpeg HTTP relay.
- Copy H.264 video, convert H.265 for playback, and retain receive-only audio.
- Use automatically allocated loopback ports and pass session material via stdin.
- Request fresh snapshots and expose connection state/last received video.
- Migrate existing version-1 integration entries and remove obsolete bridge JSON.
- Bound WebRTC connection waits, clean up partial connections, and fix races in
  the wait primitive and RTSP listener shutdown.
- Add Home Assistant lifecycle/config-flow tests, real synthetic-camera HLS and
  WebRTC media tests, race checks and reproducible release packaging.
- Drain subprocess output and abort stalled HTTP consumers during shutdown,
  including when FFmpeg requires a forced termination.

- Preserve RTP sampling clocks through burst delivery and timestamp wraparound;
  serialize forwarding/lifecycle updates and stop replaying stale RTP packets.
- Advertise Tuya codec 101 as L16 PCM and convert its sample byte order, fixing
  doubled audio duration and invalid HLS timestamps on PCM cameras.
- Report video activity for HEVC transported over the Tuya data channel.
- Package local Tuya icons/logos with attribution and license notices.
- Add HACS/hassfest validation, release/archive checks, installation and migration
  guides, Brazilian Portuguese documentation and community issue forms.
- Record live validation on Positivo Smart Câmera Wi-Fi com Bateria (11188736),
  firmware 1.1.48, including image and sound confirmed on the owner's phone.

This beta requires Home Assistant 2026.9+. Real Tuya model/firmware compatibility
must be verified separately. Internet access to Tuya remains necessary. PTZ,
two-way audio and interactive MFA/captcha are not implemented.
