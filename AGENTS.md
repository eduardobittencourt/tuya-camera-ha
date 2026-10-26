# Contributor guidance

The primary product is `custom_components/tuya_camera`: a UI-driven Home
Assistant integration. All Tuya account, signaling, LAN media and WebRTC protocol
code runs in Python inside the integration. Do not reintroduce a Go bridge,
standalone add-on, Docker image, ONVIF gateway or credential-managing CLI.
FFmpeg is Home Assistant's existing media executable, managed on demand.

Users must not copy device IDs, sessions, keys, ports or YAML. Keep internal
listeners on loopback. Share the LAN signaling/DP socket with media; do not add
periodic DP refreshes on the verified battery camera, which interrupt video.
Bound queues and tasks, and close sockets/FFmpeg processes on cancellation,
unload and removal. Reuse HA's async HTTP client and keep blocking work off its
main event loop.

Never commit credentials, session IDs, encryption codes, local keys, captured
MQTT payloads or generated account configurations. Public app-profile constants
under `vendor/tuya_mobile/profiles.py` identify shared mobile builds, not user
secrets. Never log raw protocol output or credential-bearing errors.

Run Python lint/tests, package checks and real synthetic-camera media tests
before release. Build the Python-only HACS archive with
`scripts/package_release.py`. The domain is `tuya_camera` starting with 0.4.0b2.
Preserve account config and entity unique IDs during explicitly authorized
migrations. The aiortc raw RTP adapter is version-sensitive: run its synthetic
H.264 and H.265/datachannel peer
tests when updating the pinned upstream dependency.
