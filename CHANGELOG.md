# Changelog

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
