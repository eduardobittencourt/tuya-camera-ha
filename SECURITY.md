# Security policy

Report credential exposure or authentication vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/eduardobittencourt/tuya-camera-ha/security/advisories/new).
Do not open a public issue with credentials, exploit details or private media.
Describe the affected version, impact and reproduction using synthetic data.

Security fixes target the latest published native integration. Development
snapshots have no separate maintenance guarantee. This volunteer project does not promise a response deadline.

Passwords are transient login inputs and are never persisted. Home Assistant
stores the authenticated session in its config entry. Treat Home Assistant
backups and `.storage` as sensitive data.

All camera protocol sessions run in Python memory inside Home Assistant. Private
RTSP and FFmpeg HTTP listeners bind only loopback, with random paths. FFmpeg is
HA's existing executable and shares the container's permissions. These listeners
are not sandboxed from other processes in that container. Home Assistant
authentication protects remote access.

Raw protocol output, credential-bearing errors, session fields, signing material,
identifiers and stream URLs must never appear in logs or diagnostics. Diagnostics
expose operational state, sanitized counters and FFmpeg process counts only.
Dependencies are declared in the integration manifest; the current beta's aiortc
upstream commit pin and compatibility limits are documented in
[architecture](docs/architecture.md).
