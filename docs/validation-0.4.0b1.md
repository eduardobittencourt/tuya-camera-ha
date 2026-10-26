# Python migration beta validation — 0.4.0b1

This beta replaces the Go implementation with protocol clients running inside
the Python integration. It preserves domain, account config and entity unique
IDs. It does not promise universal model support or fully offline operation.

## Automated validation

70 Python tests and three actual synthetic-media tests passed.
The Python 3.14 test environment uses HA 2026.10.2, its matching pytest plugin
0.13.373 and PyAV 19.0.2. Ruff, Python dependency consistency and deterministic
archive checks pass. Protocol tests cover signal framing and corruption,
AES padding, KCP wire layout/loss/duplicates/reordering/retransmission, bounded
buffers, MAC-based address resolution and cancellation during negotiation.

Synthetic aiortc peers cover H.264 RTP and the H.265 RTP/datachannel handshake,
including little-to-big-endian PCM conversion and filtering unusable ICE
endpoints. Actual FFmpeg media tests cover a synthetic encrypted Tuya LAN camera
through the Python RTSP server, fresh JPEG, video/audio, shared-socket DP writes,
H.264/H.265 relay playback, native HA HLS, WebRTC and source loss. No private
account or media is used in automated tests.

## Real camera

Validation used the previously tested Positivo battery camera, firmware 1.1.48,
on HA OS / Core 2026.10.4, Linux amd64. These are measurements from one unit.

- Migration retained all 19 entity registry records and the same 17 enabled
  entities, with no new account login or manually entered credentials.
- First Python LAN snapshot returned a valid JPEG in 7.143 seconds.
- LAN HLS decoded 730 video frames and 751 audio frames over 61.20 seconds;
  the delivered codecs were H.264 and AAC. A repeat on the final runtime decoded
  732 video / 753 audio frames over 62.55 seconds.
- Six native HA service calls confirmed night vision, PIR and sensitivity
  changes and restoration of their original values. The first cold call took
  6.338 seconds; subsequent calls took 0.199–1.126 seconds.
- An isolated Python cloud/WebRTC probe received H.265 via Tuya's datachannel,
  produced a fresh JPEG in 11.49 seconds and decoded 173 video / 184 audio frames
  over 20.03 seconds through the H.264/AAC relay. The main Tuya entry was
  temporarily disabled for this test and re-enabled afterwards.

Only dimensions, durations, counts and codec/state information were retained.
No private image, video/audio recording, signed URL or raw protocol payload was
saved. Other integrations were not changed.

## Dependencies and limits

The published aiortc 1.15.0 conflicts with HA's PyAV 19. This beta uses the
immutable official upstream PyAV compatibility commit documented in
[architecture](architecture.md#dependencies-and-compatibility). HA installs it
normally; its own package constraints are not overridden. A compatible published
aiortc release is preferable before promoting this migration to stable.

Cold cloud snapshots can exceed HA's ten-second image deadline, as the measured
11.49-second probe did. Internet provisioning/wake remains necessary in the
current battery-camera path. No new claim is made about offline wake, battery
endurance, cold boot, long standby, multi-camera scaling, other retail models or
other host architectures. H.264 cloud peers are synthetic coverage; the real
camera's cloud test used H.265. Talkback and PTZ remain unsupported.
