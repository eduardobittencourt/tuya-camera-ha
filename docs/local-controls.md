# LAN camera controls (development version)

The integration provisions the exact camera's local key and public DP schema
using the existing Tuya login at initial configuration. Older entries are
provisioned once when first loaded with this version. Reconfiguration through
the account UI can repeat provisioning after re-pairing changes a local key.
No password, manual device IDs, keys, IP addresses or YAML are required.

After provisioning, settings and telemetry use only a direct TCP connection to
the camera on a private IPv4 LAN address. There is **no cloud fallback** for
status, commands or alarms. Addresses are found from Tuya UDP discovery or the
camera's MAC in the host's ARP table; discovery repeats after a connection
failure. TinyTuya implements the encrypted local protocol. Cameras without a
battery DP keep the persistent heartbeat/status path. Cameras declaring
`wireless_electricity` use the on-demand lifecycle below.

The verified 3.3 media profile shares Python's signaling socket with controls through
direct in-process calls. That path uses spontaneous reports and fresh command
confirmations, without UPDATEDPS or periodic status queries: those requests
interrupted local media on the tested camera. The TinyTuya lifecycle below
continues to apply to other media profiles. Cloud wake is still required from
standby; the integration as a whole is not fully offline.

## Entities

Settings and telemetry entities are created after the camera reports a valid
value for a recognized schema function, with the corresponding data type and
write permission. A schema declaration alone does not create an entity.
Previously created settings/sensors without a confirmed observation are
disabled by the integration, preserving their IDs and customizations. If a
valid report arrives later, they are discovered automatically. User-disabled
entities stay disabled. Choices, limits, steps and scales come from the schema.

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
  Motion/sound sensors on battery cameras are disabled by default, including
  on the first upgrade to this policy; they cannot provide continuous events
  while the camera sleeps. They can be enabled manually for live-session use.

SD formatting, factory reset and unidentified raw alarm commands are not
exposed. An enum such as a vendor-specific alarm flag does not prove that it
means motion, and is not converted into a fabricated motion sensor.

Keys live only in the HA config entry. They are excluded from diagnostics and
from any separate process configuration. Treat HA backups as sensitive. Dependency
logging is suppressed for this transport's calls so debug mode cannot dump
keys or raw camera payloads; other integrations' calls are unaffected.

## Battery-camera lifecycle

Snapshots and live video share one LAN session per camera. Starting the media
request opens a connection/retry window in parallel with negotiation, so initial
IPC reports are not missed while FFmpeg captures the first frame. Rejected initial
queries may be followed by up to
eight seconds of asynchronous state reception. Battery IPCs disable TinyTuya's
device22 auto-detection because the observed query rejection does not identify
that protocol. After connecting, the integration sends one read-only DP refresh
for readable scalar functions, without waiting for an immediate acknowledgement.
The camera can report settings one at a time over roughly twenty seconds; the
shared session receives them throughout the existing media window. This is
required for night vision/PIR and other settings that are not reported
spontaneously. Offline retries and receives are bounded; standby performs no
LAN discovery, polling or heartbeat.

After the last media consumer finishes, the LAN session closes within the
bridge's existing 30-second media shutdown grace (plus the current bounded
socket operation). This does not write a keep-awake DP. Periodic snapshots or
an ongoing live stream still wake the device and can affect battery endurance.

Only camera-reported scalar values are shown. During standby, last observations
remain available with `last_observed` and `connection_active: false`; the LAN
connectivity sensor turns off. Settings and telemetry restore their last valid
observations and original timestamps through HA's restore storage. Restored
values never count as fresh command confirmations.
Controls become available after their first observed value; a command while
asleep establishes a temporary video-only consumer of the existing managed RTSP
source. Only after FFmpeg receives media does it open the LAN window. The source
stays open while commands run, with a two-second reuse grace between consecutive
service calls. The session has a sixty-second hard limit, copies video without
transcoding or audio, and is canceled on integration unload. This avoids tying
the control window to completion of a single JPEG or HA's image deadline.
Simultaneous commands share that wake operation and serialize on the socket.
Commands require a new matching DP report, not an old matching cached value.
The first battery command waits up to twenty seconds for current reports of
known settings, then drains the end of the initial read batch. Commands send
without consuming a synchronous acknowledgement and wait for the matching DP
report through the same socket. No additional refresh is sent after CONTROL.
The bounded initialization wait also maintains the session heartbeat; standby
still sends no packets.
Their CONTROL payload uses the account UID from the existing login, matching
the native IPC client; the camera ID identifies the target device separately.
Unknown/unreported settings and telemetry do not create enabled entities.
Motion/sound sensors are available only during a live LAN connection; this is
not an always-on push alarm service for sleeping cameras.

## Real-camera evidence

Earlier refused connections on the Positivo battery camera did not establish
lack of LAN support. On 2026-10-21 a private USB capture of a working native-app
session established TCP 6668 reads and night-vision writes. The camera rejected
the initial query but sent valid state asynchronously. After the session the
port closed again; pre-link and RTC session-init calls alone did not reopen it.

A bounded probe during HA snapshot retrieval subsequently obtained battery,
power source, volume and night vision without the native app. Raw captures,
keys and device identifiers remain outside this repository. These observations
motivate the on-demand implementation; they do not establish support for every
schema function, long-term battery endurance or audible talkback.
