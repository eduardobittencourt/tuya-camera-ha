# How it works

Starting with 0.4.0b1, all camera protocols execute as Python tasks in the Home
Assistant integration. No project-specific executable, Go runtime, add-on or
container is downloaded or supervised. The integration domain remains
`tuya_camera_bridge` to preserve existing accounts, entities and automations.

## Account and media ownership

`api.py` and the vendored mobile client handle UI login and device provisioning.
`media/runtime.py` owns account-scoped camera sessions and a private RTSP server.
It creates sessions only when FFmpeg requests a camera, shares a session among
consumers, and closes it when the final consumer disconnects.

For provisioned protocol-3.3 cameras, `media/lan.py` negotiates command-32 offers
and candidates over the camera's TCP signaling connection. It performs the
firmware's LAN connectivity checks, authenticates UDP datagrams with HMAC-SHA1,
reassembles KCP messages, decrypts AES-CBC media and interprets H.264/PCM frames.
`media/kcp.py` implements bounded message-mode KCP in Python: reordering,
deduplication, ACKs, retransmission, receive/send windows and fragmented messages.
This is a camera transport, not a general-purpose KCP server.

The same Python session receives scalar DP observations and sends allowlisted
controls. `lan.py` adapts this session to the entity layer through direct Python
calls; no HTTP control IPC or second signaling socket is used. Other device
profiles retain the TinyTuya control path. Periodic DP refreshes remain disabled
on the shared socket because they interrupted the tested camera's video.

A sleeping camera may still require Tuya MQTT wake, with WebRTC wake as fallback.
A LAN negotiation/authentication failure never silently switches playback to
cloud video. Removing Go does not establish fully offline operation; see
[offline evidence](offline-operation.md).

Other camera profiles use `media/cloud.py`: the existing mobile API client,
Paho MQTT and aiortc negotiate WebRTC. H.264 RTP is forwarded through a narrowly
isolated aiortc receiver hook while preserving normal RTCP/NACK processing.
Tuya's H.265 variant carries RTP in the `fmp4Stream` datachannel and includes a
codec/start/recv/complete handshake. Both adapters have synthetic peer tests.
Retail-model compatibility beyond the tested camera remains unverified.

## Playback

`media/rtsp.py` packages received media as RTP and serves RTSP/TCP only on
loopback, with random paths and ephemeral ports. It preserves H.264 parameter
sets, fragments large NAL units and converts local PCM16 to RTP network byte
order. Each reader has a bounded queue; a stalled reader is disconnected.

`transcoder.py` starts Home Assistant's FFmpeg on demand. H.264 is copied; H.265
is converted to H.264 at 720p / 15 fps. Audio is converted to AAC, and snapshots
are fresh JPEG frames. The private HTTP MPEG-TS relay feeds HA's native Stream
and go2rtc provider for HLS/WebRTC playback. FFmpeg remains a subprocess; there
is no separate protocol executable.

## Dependencies and compatibility

- Vendored `tuya_mobile`: mobile API signing/login, already implemented in Python.
- TinyTuya: discovery and local controls on profiles without shared LAN media.
- Paho MQTT: Tuya signaling and wake; TLS certificates remain verified.
- aiortc/aioice: WebRTC, ICE and STUN, with their normal cryptographic dependencies.
- HA's FFmpeg/Stream: decoding, snapshots, conversion and frontend delivery.

The published aiortc 1.15.0 requires PyAV below 18, incompatible with HA 2026.10's
PyAV 19. This beta pins the official upstream
[PyAV compatibility change](https://github.com/aiortc/aiortc/commit/10ccd168528d93996d013d0ecfae679c3a764b68)
by immutable commit URL. No HA package is downgraded and no dependency constraint
is bypassed. Replace this development pin with a compatible published aiortc
release after rerunning dependency and peer/media tests. Installation needs
access to GitHub and Python package indexes; URL requirements may be rechecked
by HA at startup. This is a beta limitation, not a zero-dependency claim.

## Lifecycle and privacy

Unload and removal cancel owned tasks, close TCP/UDP sockets and listeners, and
terminate FFmpeg process groups. Camera failures close affected readers; the
next media request establishes a new session. Authentication errors request UI
reauthentication. Last video timestamps reflect received media rather than process
liveness. Battery observations retain their timestamps during standby.

Account sessions and device credentials stay in HA's private config entry and
Python memory. No account JSON, command-line session argument or subprocess
stdin contract is needed. HA authenticates remote viewers. Loopback does not
isolate these listeners from other processes in the same container. Protect
HA backups and see [SECURITY.md](../SECURITY.md).
