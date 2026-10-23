# Local wake investigation: October 2026

This report records experimental hardware evidence, not a feature of the
integration. The [offline-operation guide](offline-operation.md) summarizes the
current product boundary and remaining acceptance criteria. Times below are UTC.

The tested device is the Positivo battery camera, firmware 1.1.48, using local
protocol 3.3 and Tuya low-power v1. Experiments used an initially online bootstrap
before camera-only IPv4 isolation. They do not establish cloud-free cold boot,
IPv6 isolation, repeatable standby transitions or a production network setup.

Research scripts, raw packet captures and private material remain outside the
repository. Only sanitized observations are recorded here. Recovery checks on
the home network are separate from the isolated experiments.

## Additional standby probes: 2026-10-22 UTC

With the app closed and the camera associated in Wi-Fi power-save mode,
repeated native discovery and Wake-on-LAN probes produced no UDP response or
opening of TCP 6668. Common service ports were also unavailable in standby.
Sending the documented v1 wake bytes over UDP, with either CRC byte order,
failed to wake the camera. That was a transport hypothesis: Tuya specifies
those bytes on an already authenticated TCP connection, not as a UDP service.

Two further bounded UDP probes used correctly framed protocol-3.3 DP_QUERY
and authenticated CONTROL with DP 149=true, using the existing account identity
and local key only in memory. Neither produced a response or opened TCP 6668
within twelve seconds. This does not establish UDP support for these commands,
and DP 149 alone does not establish a persistent keep-awake setting.

Positive controls through the existing cloud-wake path returned fresh decoded
640×360 JPEGs in 6.306 and 6.638 seconds, with the cloud-wake counter increasing
and subsequent media using LAN. AP captures exposed external TCP 443 and MQTT
TLS 8883 connections, but did not identify a complete low-power authentication
or wake payload. A 105-second camera-only WAN interruption also failed to expose
that handshake. A subsequent camera-only Wi-Fi reconnect request was accepted
by Omada, but TCP 6668 remained closed and the 120-second AP capture exposed no
camera IP flows. No physical power cycle was performed. Capture visibility is incomplete; these negative observations
do not prove that a proprietary local wake mechanism is impossible.

The temporary WAN ACL and address group were removed, the original ACL list
verified, and diagnostic SSH restored to its original disabled state. No
firmware, pairing, SSID or integration settings were changed. Investigation
scripts and camera-only metadata remain outside this repository under
`~/research/tuya-camera-ha/local-wake/2026-10-22/`; no keys, media or captured
private payloads were added to the product. These probes did not expose a direct LAN wake listener; the later TCP-server
experiment below is a separate mechanism.

## Hotspot capture: the low-power channel is identified

A subsequent macOS hotspot test routed the camera through an iPhone USB uplink.
The camera joined the hotspot without reset or pairing, and two app video
accesses succeeded. A complete new TCP connection to the keepalive server
exposed Tuya low-power v1 authentication and a nine-byte wake frame, without TLS
on this particular connection. AES-128-CBC decryption using the existing local
key verified both authentication messages. Their HMAC-SHA256 signatures use the
opaque device identifier carried on the wire, rather than the camera ID used
by the integration. The authentication payload uses three interleaved
length/value fields. The server returned success and a 60-second heartbeat
interval. The wake payload matched CRC32(local_key) in big-endian order.

This identified the real protocol for the subsequent local-endpoint experiment.
Cold boot without cloud access remains unproven.
The capture ring retained only its final 32.328 seconds, including that complete
new authentication/wake exchange; earlier traffic was overwritten. Private
captures and cryptographic material remain outside the repository. No offline
support has been added to the integration from this finding alone. The camera
did not automatically rejoin its original AP after the hotspot was stopped in
standby; the user restarted it and confirmed recovery. Automatic AP-change
recovery is therefore also unproven.

## Local wake: first hardware proof, 2026-10-22 UTC

A macOS research endpoint accepted the camera's low-power TCP connection through
camera-only PF redirection. Initial association and app video were allowed to
use the cellular uplink. After the user closed the app, the endpoint verified
the camera's authentication request using the existing local key, installed
IPv4 ingress and egress block rules, removed preexisting external states in both
directions, and checked that no other camera WAN states remained. It then sent
a correctly encrypted and signed authentication response. The only keepalive
channel terminated on the Mac's loopback listener.

At 17:38:50.051540 UTC, after TCP 6668 had been observed closed for six seconds,
the endpoint sent the nine-byte wake frame. TCP 6668 reopened at
17:38:51.360553 UTC: **1.308 seconds after the local wake**. The prototype made
no cloud API calls. Post-result PF counters showed 19 camera egress packets
(1,080 bytes) dropped; the ingress block rule was also loaded. A heartbeat was
received and answered at 17:39:13, followed by a connection reset from the
camera; the reset's cause was not determined.

This is one successful wake experiment from observed local-port standby, with
IPv4 WAN isolation following an initially online bootstrap. Physical power
consumption was not measured. Repeated wake, long standby, fresh video after
this wake, IPv6 isolation, recovery and cold boot without cloud have not been
validated by this run. The earlier offline-media proof was a separate test.
The temporary PF anchor was verified empty at 17:42:35 UTC, and the temporary
key file was absent after shutdown. The Omada client block was removed.
After returning the Mac to the home network, the camera needed a user-operated
On/Off cycle to recover. Omada then showed it active, and HA returned a valid
640×360 JPEG over LAN in 1.367 seconds without increasing its cloud-wake counter.
This recovery check was separate from the isolated wake experiment.
Production integration still needs a supported way to direct the camera's
keepalive connection to HA; the experimental hotspot/PF setup is not an
installation requirement or a shipped feature. Research scripts, sanitized
results and restoration notes are kept outside the repository.

## Local wake followed by fresh video, 2026-10-22 UTC

A second isolated experiment repeated the authenticated local wake and opened a
new LAN media session immediately afterward. Following an online bootstrap and
app closure, the endpoint blocked camera IPv4 ingress and egress and verified
zero other WAN states. After TCP 6668 stayed closed for six seconds, a local wake
at 18:31:44.733064 UTC reopened it in **1.964 seconds**. The new media session
decoded one H.264 frame at **640×360**, with 80 video packets received. The
prototype made no cloud API calls; the post-result egress block counter showed
30 dropped packets (1,992 bytes). Images were decoded in memory without saving
them.

The channel reset immediately after its first heartbeat at 18:32:07 UTC, before
the second planned cycle could establish a 30-second standby baseline. No
reconnection was observed before shutdown. The cause remains unknown; timing
alone does not establish that the heartbeat response caused the reset. Neither
repeated wake/video cycles nor the planned 120-second standby were validated.
This run establishes fresh media after one local wake under IPv4 isolation,
following an initially online bootstrap; cold boot, IPv6 and production routing
remain unproven. Shutdown at 18:35:48 UTC verified the temporary PF anchor empty,
and the temporary credential file was absent when logs were collected by SSH.
Returning to the home network again required a user-operated On/Off cycle.
Omada then showed the camera active, and HA decoded a valid 640×360 JPEG over
LAN in 7.594 seconds. This separate recovery check used the installed cloud
wake path (counter 43 to 44), outside the isolated experiment.

## Idle-channel control, 2026-10-22 UTC

A third experiment observed the authenticated local channel for **90.032
seconds without sending wake or probing TCP 6668**, after online bootstrap and
IPv4 WAN isolation. Three empty heartbeat frames were received and answered at
approximately 30, 60 and 90 seconds; the channel stayed open. The endpoint then
observed TCP 6668 closed for six seconds and sent wake at 23:44:22.420412 UTC.
The port reopened in **3.293 seconds**, and a fresh LAN session decoded one
H.264 frame at **640×360** (235 video packets).

The next heartbeat was answered at 23:44:45 UTC, followed immediately by a peer
reset, 119.699 seconds after connection acceptance. No second wake cycle was
completed. The IPv4 egress block counted 29 dropped packets (1,944 bytes).
A subsequent camera-only TCP SYN observation captured no packets in its
limited window; it does not establish that the camera never reconnects.

This control demonstrates that the implemented authentication and heartbeat
exchange can sustain an idle channel across three heartbeat intervals. It
narrows investigation toward behavior after wake/media, without establishing
why the peer resets or whether heartbeat handling contributes. Cleanup was
verified at 23:51:48 UTC: temporary PF anchor empty, prototype stopped, and
temporary credential file absent.
After returning the Mac to the home network, HA recovered a valid 640×360 JPEG
over LAN in 8.121 seconds using its installed cloud wake path (counter 48 to
49). No additional user-operated On/Off cycle was requested for this recovery.

## Wake without media or port probes, 2026-10-23 UTC

The next run completed 90.083 seconds of passive observation and three
heartbeats, then sent one wake at 00:12:00.545282 UTC without starting media or
probing TCP 6668. The first subsequent heartbeat received its exact five-byte
reply, followed by a camera RST at 00:12:29.917949 UTC in the endpoint log.
The 180.232-second post-wake observation ended without a new authentication in
the log. IPv4 egress filtering counted 24 dropped packets (1,320 bytes).
Thus neither the experimental media client nor local port probes were required
to reproduce the reset under these conditions.

The private, truncated packet capture retained the full authentication-to-reset
timeline. It confirms the transmitted wake and camera acknowledgement, exact
heartbeat replies and camera-originated RST packets; it also shows heartbeat
retransmissions after the reset. Starting about 1.8 seconds after wake, the
camera repeatedly attempted TCP connections to an external port 8883 endpoint.
This is consistent with an MQTT reconnection attempt but does not establish
application protocol or prove that blocking it caused the failure. No media
or independent physical-sleep measurement was performed in this run.

Cleanup at 00:15:50 UTC verified the temporary PF anchor empty, capture stopped,
prototype exited and temporary credential file absent. The next isolated
comparison remains the server's graceful FIN policy; the observed external
connection attempts provide a concrete target for a later dependency control.

## Next diagnostic comparison

Reviewing the original cloud capture exposed another difference: after two
wake frames, the cloud sent TCP FIN 2.465604 seconds after the first wake, and
the camera answered with RST. The local endpoint instead kept the channel open
until the camera reset it. A reset alone therefore does not establish failure;
the meaningful acceptance criterion is return to standby and another successful
authenticated wake. The capture does not establish a universal FIN delay or
whether two wake frames are required.

The wake-only control below reproduced the reset without media or port
probes. The next comparison will change only the server's graceful-close
policy. Packet capture must cover authentication through the post-wake period,
not just a later search for SYN packets. Tuya's
[low-power protocol documentation](https://developer.tuya.com/en/docs/iot-device-dev/tuyaos-package-ipc-device?id=Kcn1qc5he02rw)
confirms the heartbeat echo and describes device/server close behavior; these
references guide comparisons rather than establish this firmware's behavior.

Testing the installed HA media client also requires a verified network path.
In the current hotspot arrangement the Mac leaves the home Wi-Fi, and HA has
no validated route to the camera's hotspot address. TCP control and bidirectional
UDP/KCP must work before that comparison. An HA recovery snapshot on the home
network is a separate check, not evidence of HA media during the isolated wake.
The external research plan records the test order and acceptance criteria.

