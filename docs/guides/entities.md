# Entities and LAN controls

[Documentation index](../README.md)

## Camera entities

Each supported camera provides live video and fresh JPEG snapshots through HA's
native media components. Audio reception depends on the camera codec; talkback
and PTZ are not exposed. See [compatibility](compatibility.md).

## Settings and readings

The integration provisions camera metadata through the account setup. Settings
and readings then use the camera's local encrypted connection, without cloud
fallback for status, commands or alarms. Reconfigure the account if re-pairing
changes the local key; keys and manual device IDs are not user setup fields.

An entity is created only after the camera reports a valid value for a recognized
schema function. Types, permissions, choices, limits and scales follow that
schema. A declaration alone does not establish a working feature. Previously
created entities without valid observations are disabled while their IDs and
customizations are preserved; later valid reports allow discovery. User-disabled
entities stay disabled.

Depending on the camera's reported capabilities, entities can include:

- Switches for detection settings, privacy, recording, indicators, image flip,
  overlays, motion tracking, zones and keeping the device awake.
- Selects for night vision, sensitivity, recording, anti-flicker and operating modes.
- Numbers for PIR sensitivity, volume, low-battery threshold and alarm interval.
- Sensors for battery, power source, SD-card state and formatting progress.
- Binary sensors for LAN connection and fresh motion/sound reports.

SD formatting, factory reset and unidentified raw alarm commands are not exposed.
A vendor-specific enum is not interpreted as motion without supported semantics.

## Detection events

Fresh local motion/sound reports produce ten-second pulses; initial cached
reports do not. Repeated reports are deduplicated. Motion/sound entities on
battery cameras are disabled by default because they cannot receive continuously
while the camera sleeps. They can be enabled for live-session use.

## Battery cameras and standby

Snapshots, video and settings share a managed media session. A setting command
can temporarily open video to wake the camera before confirming the new value.
This uses the existing media path and can still need Tuya cloud signaling.
Concurrent commands share that wake operation and are serialized. A fresh
matching camera report is required to confirm each setting.

Standby performs no LAN discovery, polling or heartbeat. Last valid readings
remain available with their original `last_observed` timestamp and
`connection_active: false`; the LAN connection sensor turns off. Restored values
are not fresh command confirmations. Settings cannot be continuously monitored
on a sleeping camera. Frequent snapshots, control writes or live viewing can
affect battery endurance, which has not been measured.

See [architecture](../reference/architecture.md) for session ownership and
[security](../reference/security.md) for credential storage.
