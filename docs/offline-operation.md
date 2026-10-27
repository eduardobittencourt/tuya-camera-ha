# Offline operation: evidence and implementation decision

Last reviewed: **2026-10-27 UTC**. [Português brasileiro](offline-operation.pt-BR.md).

**The Python migration is complete; fully offline daily operation is not.** On
the tested stock Positivo battery camera, local wake and fresh LAN video work in
research experiments, but repeated wake/standby cycles without WAN have not been
established. We are not shipping the experimental wake server or claiming 100%
LAN operation. This is an implementation decision based on incomplete acceptance
criteria, not a proof that offline operation is impossible.

## Scope and current product

The evidence concerns **one Positivo Casa Inteligente Smart Câmera Wi-Fi com
Bateria, SKU 11188736, firmware 1.1.48**, LAN protocol 3.3 and low-power protocol
v1. It must not be generalized to all Tuya cameras or firmware.

Version **0.4.0** runs account APIs, cloud wake, LAN signaling/media and cloud
WebRTC in Python inside Home Assistant. It tries LAN media first; when the
battery camera's control port is closed, the wake path still needs Tuya cloud
services. Local settings and telemetry share the media control socket. Periodic
DP refreshes are deliberately avoided because they interrupt this camera's video.
The earlier Go media prototype is historical evidence, not the current runtime.
See [architecture](architecture.md) and [stable validation](validation-0.4.0.md).

The intended offline boundary allows initial online account/key/media-password
provisioning, then daily operation on LAN. A stronger claim of cloud-free
installation or cold boot has not been demonstrated either. Media credential
lifetime across power cycles is still unknown.

## Evidence that drives the decision

The [full investigation](local-wake-investigation.md) preserves the sequence,
controls, cleanup and unsuccessful trials. The identifiers below provide a
short reading path; exact sanitized TLS observations and public schema are in
[the evidence directory](evidence/local-wake/README.md).

| Evidence | Observed result | Supported conclusion and limit |
| --- | --- | --- |
| E1: standby probes | Discovery, Wake-on-LAN and bounded UDP probes did not open TCP 6668 | No direct LAN wake listener found by those probes; other mechanisms remain possible |
| E2: low-power v1 | Real authentication, heartbeat echo and nine-byte CRC32 wake verified; one isolated wake opened TCP 6668 in 1.308 s | Wake bytes and local server work after online bootstrap; a listener on the sleeping camera is not required |
| E3: local media | Fresh 640×360 frames after experimental local wake with IPv4 WAN blocked | Local wake plus new LAN media is possible; a single cycle is insufficient |
| E4: close policy | FIN after 2.501 s was acknowledged; camera reset; no second authentication within 180 s under IPv4 block | This FIN policy did not fix repetition; RST alone is not a failure criterion |
| E5: WAN control | Two local wakes with WAN allowed, 1.282 / 1.882 s; new LAN video | Repetition works in an online control, not proof of offline repetition |
| E6: TCP 8883 exception | Three local authentications, two wakes, new LAN video while other WAN TCP/UDP IPv4 stayed blocked | External TLS on 8883 is a strong candidate in the post-wake transition; encrypted traffic does not identify the required messages or prove sole dependency |
| E7: replacement TLS | Self-signed certificate rejected twice; valid owned-domain public certificate rejected three times | Simple broker redirection did not complete TLS; public validity alone is insufficient |
| E8: name controls | Eight connections: matching SAN → `UNKNOWN_CA`; wrong SAN → `BAD_CERTIFICATE`, irrespective of CN | Strong evidence of service-name checking plus a trust barrier; no proof of leaf/SPKI pinning or complete trust-store contents |
| E9: final read-only review | Fresh firmware/schema confirmed; DP 149 `wireless_awake`, boolean, `rw`; no supported endpoint/trust setting identified in reviewed material | DP 149 remains a specific untested offline sleep-transition hypothesis, not a demonstrated workaround |

The tested IP diversion preserved the requested TLS identity `m2.tuyaus.com`.
A certificate for an owned hostname supplies a different identity. A plain local
MQTT server, DNS rewrite or NAT rule alone therefore does not establish a working
replacement. Even accepted TLS would leave MQTT application behavior to verify;
no camera TLS handshake reached the local MQTT stub.

## What the final read-only review adds

Two existing account read APIs, `thing.m.device.get` v4.1 and
`tuya.m.device.ref.info.my.list` v2.0, returned firmware **1.1.48** and **21 public
DP definitions**, identical to HA's cached schema. Only definitions were exported;
no device state or account identifiers are published. The schema includes
`wireless_awake` (149, boolean, `rw`), `wireless_powermode` (146, read-only) and
`wireless_lowpower` (147, writable integer 10–30). The latter is a low-battery
alarm threshold, not a sleep mode: see the
[iOS battery documentation](https://developer.tuya.com/en/docs/app-development/low-power-doorbell?id=Kad3pl13guhil).

Tuya's [Android guide](https://developer.tuya.com/en/docs/app-development/doorbell?id=Ka6nxw2gncv8t)
uses DP 149 as awake status. Its
[4.x firmware SDK guide](https://developer.tuya.com/en/docs/iot-device-dev/sdk?id=K95019g5w3eiq)
also describes sleep control and a server-notification sequence before sleep.
That guide's boolean descriptions conflict with its later awake report example.
Neither the name nor `rw` establishes which LAN write, if any, bypasses the
external transition on firmware 1.1.48. Earlier UDP DP149 probes are not a test
of an authenticated TCP write while the camera is awake. **No DP writes were
performed in the final review.**

The [source review and bibliography](local-wake-investigation.md#final-read-only-review-2026-10-27-utc)
distinguish firmware developer APIs from retail-device settings. Changing the
mobile API endpoint in our Python client changes account routing, not the
camera's MQTT broker or trust store. The review covered this client's source,
public SDK documentation, manufacturer product information and current schema;
it did **not** decompile the installed phone app or inspect a firmware image.
No supported offline/broker/CA setting was identified within that scope. Absence
from these sources is not proof that no undocumented setting exists.

## Why this is not ready to integrate

Receiving one wake is solved experimentally. Returning to a usable low-power
channel without external service access remains unresolved. The tested broker
replacement stops at TLS, and no supported stock-device configuration has been
identified to change its service identity/trust. Research redirection also needs
router/AP control; it is not a Home Assistant UI feature or a supported deployment.
We will not turn those assumptions into product requirements.

DP 149 is a reason to preserve an open question, not to erase the observed
failures or declare all alternatives exhausted. Firmware replacement, CA
replacement and rooted-device approaches would be a different scope from an
integration for the stock camera.

## Limits and criteria for reopening

The experiments used online bootstrap. Later isolation covered camera WAN
TCP/UDP **IPv4**, not verified dual-stack isolation; LAN DNS remained available.
A TLS-focused direct probe intentionally allowed WAN and normal cloud wake.
Port closure and return to low-power authentication are observable proxies;
physical sleep and power consumption were not measured. Bounded negative
windows, AP capture gaps and one relay offload bug limit negative conclusions.
The full report records these separately from positive results.

A useful next result would be one of:

- A documented, model-applicable endpoint/trust/offline setting, with a supported
  way to configure and restore it on stock firmware.
- A precise, confirmed DP149 command/meaning that restores local low-power
  authentication without TCP 8883. Observe the normal command first, then test
  authenticated LAN control with a known recovery path; do not guess polarity
  from the conflicting SDK prose.
- An accepted local TLS session and the required application exchange, or an
  independent reproduction of repeated isolated cycles on this model/firmware.

Before claiming offline daily operation, require fresh media, confirmed setting
changes and telemetry with **camera and consumer WAN blocked on IPv4 and IPv6**;
multiple complete idle/wake cycles; long standby; HA restart and camera power
cycle; and credential persistence/recovery. Verify isolation using counters or
upstream capture including established states, control DNS/alternate uplinks,
and distinguish local traffic from cloud/TURN fallbacks. Define observation
windows beforehand and retain a positive online control and cleanup record.
Cached values, an available entity or an already-running video are insufficient.
Battery endurance and event delivery require separate measurements.

## Reading and reproducing the reasoning

Read this decision first, then the [chronological report](local-wake-investigation.md)
and [sanitized evidence](evidence/local-wake/README.md). The report explains the
network roles, protocol comparisons and positive controls needed to repeat the
experiments on one's own hardware. Raw captures, keys, private app binaries and
credential-bearing laboratory scripts are not distributed; this is an auditable
account of observations, not a turnkey reproduction harness or independently
verifiable packet archive. New evidence can overturn the decision above.
