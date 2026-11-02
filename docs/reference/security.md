# Security boundaries

[Documentation index](../README.md)

## Runtime

Credentials and device keys stay in private HA config entries and memory.
Account passwords are used for login and are not saved. Internal RTSP and HTTP
media listeners bind loopback; HA authenticates remote viewers. Loopback does
not isolate listeners from other processes in the same container.

Private vendor APIs and camera protocols impose compatibility constraints.
HMAC-SHA1 authenticates LAN media; legacy MD5 constructions are used for protocol
login and request signing. These are interoperability formats, not general
password-storage APIs. Changing one client algorithm does not upgrade the
camera or service. Do not infer end-to-end confidentiality from local playback.

Diagnostics and logs must omit credentials, sessions, local keys, raw protocol
payloads and camera identifiers. Keep HA configuration and backups private.
See [SECURITY.md](../../SECURITY.md) for vulnerability reporting.

## Release tooling

`scripts/check_repository.py --archive dist/tuya_camera.zip` accepts only the
repository's fixed archive. It verifies member names, sizes and bytes against
the component plus LICENSE/NOTICE and checks SHA256SUMS. It rejects escaping
member paths and filesystem symlinks in the release directory, archive and
adjacent checksum paths. ZIP member symlink metadata is not inspected. ZIP input
size and reads are bounded. The checker does not extract or run archive contents.
The local checkout and filesystem remain trusted inputs.

## Synthetic media probe

`scripts/webrtc_probe.py` accepts a go2rtc API port, not an arbitrary URL.
HTTP is fixed to IPv4 loopback, ignores proxies, rejects redirects and bounds
the SDP answer. ICE and authenticated STUN sources are constrained to loopback;
external destinations are rejected. Its aiortc gatherer substitution is isolated
to test tooling and must be checked on dependency updates. Peer negotiation
tasks are cancelled and joined before shutdown.
