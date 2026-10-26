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

The supported firmware fixes the legacy wire algorithms: protocol-3.3 TCP
signaling uses AES-ECB with CRC framing, local media uses AES-CBC with verified
per-datagram HMAC-SHA1, and P2P login uses an MD5-derived token. These operations
are limited to Tuya interoperability; they are not used to store user passwords
or to define a new encryption format. Changing the algorithms requires firmware
support. The signaling protocol is a reason to restrict camera access to a
trusted LAN. Protocol-algorithm scanner findings must be reviewed with this
scope rather than "fixed" by silently changing the on-wire format.
