# Security policy

Report credential exposure or authentication vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/eduardobittencourt/tuya-camera-ha/security/advisories/new).
Do not open a public issue with credentials, exploit details or private media.
Describe the affected version, impact and reproduction using synthetic data.

Security fixes target the latest integration beta (currently 0.3.0b1). Older
development snapshots and the compatibility add-on have no separate maintenance
guarantee. This volunteer project does not promise a response deadline.

Passwords are transient login inputs and are never persisted. Home Assistant
stores the authenticated session in its config entry. Treat Home Assistant
backups and `.storage` as sensitive data.

The managed bridge receives its session via stdin. Executables are pinned by
version and SHA-256 checksum; replacements use atomic writes with owner-only
permissions. The bridge and FFmpeg relays bind only loopback, and HTTP streams
use random paths. They are not sandboxed away from other processes inside the
same Home Assistant container. Native Home Assistant authentication protects
remote access.

Raw bridge stdout/stderr, session fields, signing material, identifiers and
stream URLs must never be forwarded to integration logs or diagnostics.
Diagnostics expose only operational state and process counts.

The compatibility standalone add-on still exposes unauthenticated ONVIF/RTSP
on the LAN. Do not expose its ports publicly. That behavior is separate from
the managed integration's loopback-only mode.
