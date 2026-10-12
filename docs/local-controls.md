# LAN camera controls (0.3.3+)

The integration provisions the exact camera's local key and public DP schema
using the existing Tuya login at initial configuration. Older entries are
provisioned once when first loaded with this version. Reconfiguration through
the account UI can repeat provisioning after re-pairing changes a local key.
No password, manual device IDs, keys, IP addresses or YAML are required.

After provisioning, settings and telemetry use only a direct TCP connection to
the camera on a private IPv4 LAN address. There is **no cloud fallback** for
status, commands or alarms. Addresses are found from Tuya UDP discovery or the
camera's MAC in the host's ARP table; discovery repeats after a connection
failure. TinyTuya implements the encrypted local protocol. Heartbeats and
status refreshes maintain a persistent connection and receive live DP reports.

This does not change the existing media bridge: its authentication and WebRTC
signaling still require Tuya internet services, and media may use TURN. The
integration as a whole is not fully offline.

## Entities

Entities are created only for recognized functions declared by that camera's
schema, with the corresponding data type and write permission. Choices,
numeric limits, steps and scales come from its schema. Commands require a
confirmed state from the camera; unavailable LAN connections reject commands.

- Switches: PIR/motion/person/sound detection, privacy, recording, siren,
  indicator, image flip, timestamp overlay, WDR, motion tracking, detection
  areas, privacy zones, alarm reporting and keeping a device awake.
- Selects: night vision (automatic/off/on), sensitivity enums, recording mode,
  anti-flicker, working mode and light mode.
- Numbers: PIR sensitivity, volume, low battery threshold and alarm interval.
- Sensors: battery, power source, SD card state and formatting progress.
- Binary sensors: LAN connectivity; motion/sound pulses from fresh local
  capture reports when those functions exist. Cached initial reports do not
  generate motion, repeated reports are deduplicated, and pulses expire after
  ten seconds. Raw capture/alarm packets are not stored in HA state or logs.

SD formatting, factory reset and unidentified raw alarm commands are not
exposed. An enum such as a vendor-specific alarm flag does not prove that it
means motion, and is not converted into a fabricated motion sensor.

Keys live only in the HA config entry. They are excluded from diagnostics and
from the Go bridge's stdin payload. Treat HA backups as sensitive. Dependency
logging is suppressed for this transport's calls so debug mode cannot dump
keys or raw camera payloads; other integrations' calls are unaffected.

## Real-camera limitation

On 2026-10-09 the existing Positivo battery camera delivered a fresh JPEG through
the media bridge. Its product schema advertised night vision, PIR, sensitivity,
person filtering, recording, volume and siren, but its LAN rejected TCP 6668
even after live viewing woke the camera. It also did not advertise itself in
Tuya UDP discovery. No privacy-mode DP was declared.

For that unit, connectivity is off and additional controls are unavailable.
The implementation does not substitute cloud values or commands. The tests
exercise encrypted local reads/writes and live motion using a synthetic TCP
camera, plus native HA entities and services. They do not establish that the
retail unit supports LAN controls. A persistent LAN connection may also affect
battery endurance on models that support it; endurance has not been measured.
