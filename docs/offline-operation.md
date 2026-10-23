# Offline operation: investigation, not a supported feature

The intended boundary is cloud access for account provisioning, function
discovery and the local key, with daily operation entirely over the LAN.
The current integration does not meet this boundary: its wake path for the
tested battery camera still uses Tuya cloud services. Research prototypes have
demonstrated local wake and fresh LAN media with controlled network redirection
and IPv4 WAN isolation; this is not integrated or supported. The development
bridge attempts LAN media first, with cloud wake only if the local control port
is closed.

## What was tested

On 2026-10-21, the tested Positivo battery camera was associated with its AP,
with its LAN control port closed and no HA media subprocesses. A bounded probe
sent the same discovery request format observed in the native app (command 37
on UDP 7000), then a standard Wake-on-LAN packet. Neither opened the control
port or produced camera UDP responses during its twelve-second observation.
No settings were written. WAN access was not blocked, and physical sleep was
not measured. This does not rule out another firmware-specific wake mechanism.

Reanalysis of the existing native-app capture found discovery broadcasts before
the camera initiated STUN traffic, followed by LAN control. Cloud traffic was
also active. The only local command-32 signaling frame was an ICE candidate;
there was no captured local offer/answer demonstrating offline startup.

## Experimental local wake: current evidence

The [October 2026 investigation report](local-wake-investigation.md) records
protocol verification, hardware experiments and their cleanup. On the tested
Positivo battery camera, firmware 1.1.48:

- A local endpoint authenticated the real Tuya low-power v1 connection and sent
  the nine-byte wake frame while camera IPv4 WAN traffic was blocked after an
  online bootstrap. TCP 6668 reopened in 1.308 seconds in the first experiment.
- Separate experiments opened fresh LAN media after local wake and decoded
  H.264 at 640×360. Wake-to-port-open times were 1.964 and 3.293 seconds.
- A passive 90-second control sustained three heartbeats. After wake, the
  channel reset following the next heartbeat. A later wake-only control
  reproduced this without starting media or probing the local control port.
- Packet capture confirmed the wake, acknowledgements, heartbeat replies and
  camera-originated RST. External port-8883 connection attempts after wake are
  consistent with MQTT but do not establish the application protocol or cause.

The prototype's server-close policy differs from the original cloud capture,
where the server sent FIN after wake. That comparison is pending; the delay
observed in one cloud exchange is not a universal protocol requirement.

No experiment has established repeatable wake/standby cycles, long-standby
recovery, physical sleep or battery consumption, IPv6 isolation, or cold boot
without cloud. Returning from the hotspot sometimes required an On/Off cycle.
The current hotspot also removes the Mac from the home LAN: HA needs a verified
TCP and bidirectional UDP/KCP path before it can be the media client in that
isolated setup. Ordinary HA recovery snapshots do not prove that path.

Temporary camera blocks and PF rules were removed after each completed test;
private provisioning files were consumed and removed. Recovery of the camera
after the latest wake-only run remains pending in the investigation record.
These results do not change the installed integration's cloud-wake path.

## Two separate requirements

1. **Wake from standby.** Tuya documents a low-power Wi-Fi module maintaining an
   authenticated TCP connection to a cloud keepalive server and receiving wake
   data on that connection. Knowing the local key does not by itself expose a
   LAN wake listener. This protocol version was verified on our unit in the hotspot capture
   and local-endpoint experiments described in the investigation report.
   See [Tuya's low-power protocol](https://developer.tuya.com/en/docs/iot-device-dev/tuyaos-package-ipc-device?id=Kcn1qc5he02rw).
2. **Start media locally.** This now has direct evidence on the tested camera:
   an external research prototype opened two fresh sessions while the camera's
   WAN TCP/UDP traffic was blocked. It does not establish wake from standby.

## Local video startup: hardware proof

On 2026-10-21, a Go prototype adapted from
[aventproxy](https://github.com/leonardpitzu/aventproxy/tree/f9b5fe6db65495e73355455cf0bf4f6854487f6c)
was tested against the Positivo battery camera, firmware 1.1.48, advertising
LAN protocol 3.3. It negotiated offer/answer and candidates through local TCP
command 32, then received encrypted AES/KCP media over local UDP. FFmpeg decoded
fresh H.264 frames at 640×360. Protocol 3.3 command 32 must omit the clear
15-byte version header added by the generic TinyTuya encoder.

Provisioning and an initial cloud media connection woke the camera. The cloud
media process was then stopped before the first local offer. Three successive
local sessions decoded video using the same credentials held in memory, with
no new provisioning calls. In a separate run, the first local session held
the camera active while a temporary gateway rule blocked that camera's WAN
TCP/UDP traffic, including established connections. IPv6 was disabled on the
queried LAN. Two subsequent sessions, with new processes and new offers, each
decoded a fresh frame while that rule remained enabled. Their media candidates
were restricted to the configured camera IP; the receiver has no API/MQTT/TURN
fallback. The temporary rule and group were removed, and the original rule
list was verified unchanged. ACL configuration was checked through the
controller; no gateway packet counters or upstream packet capture were taken.

The first attempts to block WAN before sending an offer failed. A control run
with WAN allowed and the same 20-second idle delay failed identically, even
with TCP heartbeats. Those failures cannot be attributed to loss of cloud
access. Holding local media active during rule application allowed the two
successful reconnects. Standby and cold boot remain separate acceptance tests.

The P2P media login also requires a device media password obtained through
`m.ipc.v4.rtc.config.get`, distinct from the account password and local key.
It was provisioned once per test run and kept only in memory. Its lifetime
across camera power cycles has not been established. No images, decrypted
payloads or credentials were saved.

## Managed integration candidate

The unpublished 0.3.4 candidate incorporates protocol-3.3 command-32 signaling
and camera-only AES/KCP media. Device media passwords are provisioned once into
the private HA config entry; runtime session material reaches Go only on stdin.
The bridge attempts LAN first. A closed control port invokes cloud MQTT wake;
cloud WebRTC wake remains a fallback. A local negotiation or authentication
failure does not switch playback to cloud media. Other protocol versions retain
the existing cloud-signaled transport.

The local profile supplies H.264 video and PCM16 mono at 8 kHz, independent of
cloud codec declarations. In the HA container, 1,003 decoded video frames covered
65.47 seconds while audio covered 65.68 seconds. A setting command was confirmed
and the original night-vision setting restored during that playback. No image,
audio or decrypted protocol payload was retained.

Go owns one TCP signaling/DP socket. Python consumes filtered scalar reports and
sends commands through private loopback IPC. Periodic DP queries and UPDATEDPS
are deliberately omitted on this path: tested queries prevented negotiation or
interrupted media on this firmware. Only spontaneous reports and new command
responses refresh observations; other values retain their original timestamps.
This is a limitation of state refresh, not proof of complete offline telemetry.
Talkback on the LAN media profile is not yet supported.

The earlier temporary-WAN-block test covered the prototype. The current hardware
playback tests do not establish cold wake, camera power-cycle recovery, event
coverage or full daily operation without WAN. HA frontend playback, snapshots,
commands and reload/reconnection validation are recorded in [the candidate report](validation-0.3.4.md#native-lan-media-candidate--2026-10-22-utc).

## Acceptance criteria

Claim offline daily operation only after fresh media, telemetry and confirmed
setting changes work with WAN blocked for both camera and consumer, including
repeated reconnects after long standby, HA restart and camera power cycling.
Cached values, an existing video session or an available entity do not satisfy
these checks. Sensor events also require separate verification.
