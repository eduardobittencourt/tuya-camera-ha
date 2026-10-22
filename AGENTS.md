# Contributor guidance

The primary product is `custom_components/tuya_camera_bridge`: a UI-driven Home
Assistant integration that installs and supervises the Go media bridge under
`bridge`. This repository ships only the native integration; do not reintroduce
a standalone add-on, Docker image, ONVIF gateway or credential-managing CLI.

Users must not copy device IDs, sessions, keys, ports or YAML. Contract changes
must be implemented and tested on both the Python and Go sides. Keep managed
listeners on loopback and account session material on stdin, not command lines.

Never commit credentials, session IDs, encryption codes, local keys, captured
MQTT payloads or generated bridge JSON. Public app-profile constants under
`vendor/tuya_mobile/profiles.py` identify shared mobile builds, not user secrets.
Do not log raw bridge output or credential-bearing errors.

Run Python lint/tests, Go race tests/build and real synthetic-camera media
tests before release. Releases use Go 1.26.8 and `scripts/package_release.py`; regenerate the checked-in binary
manifest whenever Go source changes.
