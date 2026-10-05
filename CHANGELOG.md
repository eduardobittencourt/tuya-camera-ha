# Changelog

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

This beta requires Home Assistant 2026.9+. Real Tuya model/firmware compatibility
must be verified separately. Internet access to Tuya remains necessary. PTZ,
two-way audio and interactive MFA/captcha are not implemented.
