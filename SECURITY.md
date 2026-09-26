# Security policy

Report credential exposure or authentication vulnerabilities privately through
GitHub security advisories.

Passwords are transient config-flow inputs and must never be persisted. The
integration stores a renewable Tuya session in an owner-only `0600` bridge file.
Logs and diagnostics must redact session IDs, encryption codes, signing material,
local keys, MQTT credentials and signed request bodies.
