# Architecture

[Documentation index](../README.md)

## Account and media ownership

All camera protocols run as Python tasks inside `custom_components/tuya_camera`.
`api.py` and the vendored mobile client handle account login and provisioning.
`media/runtime.py` owns account-scoped camera sessions and a private RTSP server.
Sessions are started on demand, shared among consumers and closed after the last
consumer leaves, with a bounded shutdown grace.

For supported protocol-3.3 devices, `media/lan.py` owns signaling and encrypted
LAN media. `media/kcp.py` provides bounded message reassembly, ordering and
retransmission. The entity adapter in `lan.py` shares that signaling session for
camera reports and allowlisted controls. Other profiles use TinyTuya for controls.
Periodic status refreshes must not interrupt a shared media session.

Cloud media uses `media/cloud.py`, the mobile API, MQTT and aiortc. H.264 RTP
uses a narrowly isolated receiver hook; the H.265 path uses Tuya's data channel.
A LAN authentication/negotiation failure does not silently select cloud video.
Cloud signaling can still be needed to wake a sleeping camera.

## Playback

`media/rtsp.py` serves RTP over RTSP/TCP on loopback with random paths, ephemeral
ports and bounded reader queues. Stalled readers are disconnected.
`transcoder.py` runs HA's FFmpeg on demand: H.264 is copied, H.265 becomes H.264
at 720p / 15 fps, and audio becomes AAC. Snapshots are fresh JPEG frames.
A private MPEG-TS relay feeds Home Assistant Stream and its WebRTC provider.

## Dependencies and compatibility

The integration manifest is authoritative for runtime dependency versions.
The vendored mobile client handles account API access; TinyTuya handles relevant
local-control profiles, Paho MQTT handles signaling, and aiortc/aioice handle
WebRTC. HA provides FFmpeg and Stream.

The aiortc requirement is pinned to an immutable upstream commit for PyAV
compatibility. Installation requires GitHub and Python package-index access;
HA may recheck URL requirements at startup. Do not downgrade HA's own packages
or bypass dependency constraints. Changes to that pin or the RTP adapter require
fresh dependency resolution and synthetic H.264/H.265 peer/media tests.

## Lifecycle

Unload and removal cancel owned tasks, close sockets/listeners and terminate
FFmpeg process groups. Media failure closes affected readers; the next request
creates a new session. Last-reader cleanup completes even when the caller is
cancelled, so a new request cannot reuse a closing session. Authentication
failures request UI reauthentication.

Battery observations retain original timestamps in standby. Connection status
must distinguish a ready service from actual camera reachability. Keep queues,
retries and cleanup bounded, and keep blocking work off the HA event loop.
See [security](security.md) and [testing](../development/testing.md).
