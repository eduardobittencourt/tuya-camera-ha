# Local wake investigation: October 2026

This report records experimental hardware evidence, not a feature of the
integration. The [offline-operation guide](offline-operation.md) summarizes the
current product boundary and remaining acceptance criteria. Times below are UTC.

The tested device is the Positivo battery camera, firmware 1.1.48, using local
protocol 3.3 and Tuya low-power v1. Experiments used an initially online bootstrap
before camera-only IPv4 isolation. They do not establish cloud-free cold boot,
IPv6 isolation, repeatable standby transitions or a production network setup.

Research scripts, raw packet captures and private material remain outside the
repository. Only sanitized observations are recorded here and in the linked
[evidence bundle](evidence/local-wake/README.md). The
[final read-only review](#final-read-only-review-2026-10-27-utc) records the closing
source/schema audit and the unresolved DP149 hypothesis. Recovery checks on
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

## Planned FIN comparison at that stage (subsequently completed)

Reviewing the original cloud capture exposed another difference: after two
wake frames, the cloud sent TCP FIN 2.465604 seconds after the first wake, and
the camera answered with RST. The local endpoint instead kept the channel open
until the camera reset it. A reset alone therefore does not establish failure;
the meaningful acceptance criterion is return to standby and another successful
authenticated wake. The capture does not establish a universal FIN delay or
whether two wake frames are required.

The preceding wake-only control reproduced the reset without media or port
probes. At that stage, the planned comparison was to change only the server's
graceful-close policy (results are recorded in the October 26 sections below). Packet capture must cover authentication through the post-wake period,
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


## Wake injection on the existing home network, 2026-10-26 UTC

Without moving the camera to a dedicated AP, a temporary EAP610 capture exposed
its authenticated low-power TCP channel and current sequence numbers. A research
process in the Home Assistant container delivered one nine-byte wake directly
on the LAN, using the existing server's source IP/port and the observed TCP
sequence/acknowledgement. Session parameters and the local key stayed in memory;
no cloud API was called by the probes.

Three successive trials opened TCP 6668 from an initially closed state. The
first opened the port in **1.302 seconds**, and the AP capture confirmed the
camera's acknowledgement of the injected wake. The port was observed closed
again afterward. The second received 56 video packets through the installed
Python LAN implementation, but its RTSP test decoder failed without selecting
TCP transport. Its verification capture contained no camera packets, so that
capture cannot establish whether the wake was acknowledged.

With RTSP-over-TCP selected in the test client, the third trial reopened the
port in **1.963 seconds** and decoded a fresh **640×360** frame through the
installed Python LAN transport, receiving 49 video packets. No image was saved,
and the test instantiated only the LAN session, without a cloud media fallback.

These are repeated local packet-injection wakes on a previously cloud-established
TCP channel, with WAN connectivity still available. They do **not** validate
repeated offline cycles, a local keepalive endpoint, cold boot, physical sleep
or a production wake mechanism. Injection advances the camera's TCP sequence
state without synchronizing the real server and can disrupt that connection;
it is a diagnostic technique, not an integration design. The first verification
capture also contained camera RSTs across its observed flows, without identifying
their cause. Direct UDP discovery/wake variants, Ethernet Wake-on-LAN and a
1,062-port TCP scan had not opened the control port before this experiment.

The practical remaining requirement is still a supported path for the camera
to establish its authenticated keepalive connection to a local endpoint. The
isolated endpoint FIN/reconnection comparison was still pending at this stage;
the following experiment records its result.
Sanitized trial results and scripts are stored in the external research area.

At completion, HA's cloud-wake counter remained **2**, with no media processes,
and TCP 6668 was closed again. Temporary AP SSH settings were restored after
every trial, the serial console was disconnected and the research HTTP server
was stopped. The third trial's post-wake AP capture also contained zero camera
packets; its decoded frame is the positive media evidence. Product code and
installed integration configuration were unchanged.

## Local endpoint on the home LAN and FIN comparison, 2026-10-26 UTC

A subsequent research trial avoided the hotspot. A camera-only ARP diversion
passed its gateway traffic through the devbox, where a temporary nftables rule
redirected external TCP 443 to a local Python low-power endpoint. Other traffic
was initially relayed without changing the camera's network configuration.
An independent watchdog restored the two neighbor mappings, removed only the
experiment's NAT/connection state and deleted its temporary camera WAN ACL.
This requires privileged network intervention and is not a supported installation
method or a feature of the integration.

At 22:50:56.968 UTC the camera established a new connection, and the local
endpoint verified its authentication signature using the existing local key
and sent a signed/encrypted response. The key was read from HA in memory and
transferred with ephemeral RSA-OAEP encryption, without a plaintext credential
file. A camera-only gateway ACL then blocked WAN TCP/UDP IPv4, including existing
states. The local relay also stopped forwarding external IPv4 traffic in either
direction. IPv6 isolation was **not** verified: the controller reports IPv6
addresses for this camera, despite its queried LAN configuration having IPv6
disabled. No complete offline claim follows from this trial.

The endpoint echoed three heartbeats during 90 seconds of passive observation,
then established a six-second closed-port baseline. One application wake sent
at **22:52:34.080 UTC** reopened TCP 6668 in **1.882 seconds**. It made no cloud
API call and did not start media. At **22:52:36.580 UTC**, 2.501 seconds after wake,
the endpoint shut down its TCP write side gracefully. The camera reset the
connection immediately afterward. Metadata-only Ethernet observation confirmed
one server FIN and a camera acknowledgement of that FIN, followed by one camera
RST. Two wake-bearing TCP transmissions were observed for the single application
send; these do not represent two separately requested wakes.

No second local authentication was observed in the following 180 seconds. The
control port remained open at a later check, and the relay counted 22 dropped
external IPv4 packets. This establishes that the tested FIN policy alone did
not complete a repeatable cycle under these conditions; it does not identify
which dependency or firmware behavior prevented recovery.

A WAN-permitted control was attempted next, retaining the local redirect and
FIN policy. It captured no camera IP traffic and no authentication during its
150-second window. A normal HA snapshot requested as an online bootstrap also
failed. Subsequent controller detail confirmed the camera inactive and not
blocked, last seen at **22:55:25.935 UTC**, before the isolated trial's cleanup.
The camera was absent from the current client list and stopped answering ARP;
thus a closed TCP port in this control cannot be treated as a standby baseline.
The controller rejected a camera-only reconnection request. This control is
inconclusive and cannot establish the effect of permitting WAN or MQTT.

Both watchdog cleanups confirmed the temporary ACL and address group absent.
The local NAT table, research HTTP/keepalive listeners and serial sessions were
removed. HA's integration remained loaded; its camera entity became unavailable
when the device left the network. No HA installation, restart, product-code
change or camera configuration write was performed. Only the devbox gained the
APT `conntrack` diagnostic utility. No packets, credentials or media were saved.

A physical recovery was requested, but the user could not power-cycle the
camera. A later controller query nevertheless found it active again, and HA
recovered without physical intervention. A fresh 640×360 image decoded in
7.333 seconds using the installed cloud wake path (counter 6 to 7). This is a
separate online recovery check, not isolated media evidence. The delay is
consistent with a retry/backoff mechanism but does not identify the cause.
A supported way to configure the local keepalive destination, repeated isolated
cycles, IPv6 isolation and cold boot remain open requirements.

## Two local wake cycles with WAN permitted, 2026-10-26 UTC

After normal online image recovery, a control reauthenticated locally and
reopened TCP 6668 in 1.293 seconds. A second authentication arrived about
27.7 seconds after that wake, but this run was stopped before its second wake:
the initial diversion intercepted every external TCP 443 destination and could
also capture non-low-power traffic. It is not an unrestricted-WAN comparison.

The relay was corrected to learn `SO_ORIGINAL_DST` only after a valid local
low-power authentication, then atomically restrict the redirect to that server.
Other external destinations, including other TCP 443 destinations, were relayed
normally. The endpoint made no cloud API calls; camera WAN connectivity remained
available. Observed external port-8883 traffic included TCP responses and TLS
handshake/application-data record types in both directions. These encrypted
records do not identify MQTT messages or establish a particular dependency.

This corrected control completed two wakes:

- Local authentication at **23:05:43.515 UTC**, followed by three heartbeat echoes
  and a six-second closed-port baseline. Wake at **23:07:19.746 UTC** reopened
  TCP 6668 in **1.282 seconds**; write-side shutdown followed 2.501 seconds later.
- A new authentication arrived at **23:08:15.774 UTC**. After another 90-second
  observation, three more heartbeat echoes and a closed-port baseline, wake at
  **23:09:52.723 UTC** reopened TCP 6668 in **1.882 seconds**. A new LAN-only
  Python media session then decoded **640×360**, receiving 49 video packets.

The HA cloud-wake counter was 7 before the second local wake, following the
separately documented online recovery. The research media client instantiated
only the LAN implementation, with no cloud fallback. Wire observation recorded
acknowledgements of both FINs. It also counted additional FIN/RST packets across
other port-443 flows; those aggregate counts are not low-power cycle counts.
No image or raw packet capture was persisted.

This establishes two successive locally authenticated wake cycles and fresh
Python LAN media **with WAN available**, in addition to the single wake under
TCP/UDP IPv4 isolation. The different outcomes justify a controlled post-wake
WAN-dependency investigation. They do not prove MQTT dependence or repeated
offline operation; the network diversion was also refined between experiments.
IPv6 isolation, long standby, cold boot and a supported local-endpoint discovery
mechanism remain unverified.

The corrected control ended at **23:10:14 UTC** with its watchdog confirming
removal of NAT, the temporary camera ACL/group and restorative neighbor updates.
Research listeners and packet-observation processes were stopped. No HA restart,
installed integration change or physical camera power cycle was needed.

The final normal-HA recovery check decoded a fresh **640×360** image in
**6.409 seconds**, using its existing cloud wake path (counter **7 to 8**).
This check followed removal of the research network intervention and is
separate from the LAN-only media result during the WAN-permitted control.

## Reconnection with only WAN TCP 8883 available, 2026-10-26 UTC

A subsequent trial changed WAN policy within the same authenticated local cycle.
Separate camera-only gateway rules blocked TCP and UDP in every connection state.
After three heartbeat echoes and a six-second closed-port baseline, one local
wake at **23:54:13.792 UTC** reopened TCP 6668 in **1.861 seconds**. The server
sent FIN after 2.501 seconds; the camera reset the connection. No second local
authentication arrived during the next 60 seconds.

At **23:55:14.820 UTC**, the gateway TCP rule was changed to block all ports
except **8883**. UDP remained blocked; the devbox relay applied the same
exception. The rule and its IP/port group were reread from the controller and
verified. The group covered both halves of IPv4 and port ranges 0–8882 and
8884–65535; no general WAN release occurred in this completed trial. An earlier
attempt had stopped safely when the controller rejected a custom /0 group;
the corrected /1 groups passed a separate preflight without an active ACL.

The camera exchanged TLS traffic on 8883 and authenticated to the local
low-power endpoint again at **23:56:24.417 UTC**, approximately **69.6 seconds
after enabling the exception**. After another 90-second observation and three
heartbeat echoes, a second local wake at **23:58:00.922 UTC** reopened TCP 6668
in **1.290 seconds**. A new LAN-only Python media session decoded **640×360**
from 49 video packets. A **third local authentication** arrived at
**23:58:39.589 UTC**, approximately 38.7 seconds after the second wake, while
only WAN TCP 8883 remained permitted. Thus this run observed a return to the
low-power channel after both wakes. Research wake/media code made no cloud API
calls and had no cloud media fallback.

Passive public TLS metadata showed TLS 1.2 with cipher suite `0xC027`,
[TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256](https://www.iana.org/assignments/tls-parameters),
and no PSK cipher in the captured client offer. No TLS identities, certificates,
application payloads or account credentials were retained. The encrypted port
traffic does not expose MQTT messages. TCP retransmissions were also observed;
packet counters must not be interpreted as distinct application requests.

The outcome narrows investigation to the external TLS service on TCP 8883 during
the post-wake transition. It does not establish that it is the only possible
external dependency, prove causality from a single phased trial, or demonstrate
fully offline operation. IPv6 isolation, cold boot and long standby remain
unverified. There was still an online bootstrap, and LAN DNS remained available.

Cleanup completed at **23:58:50 UTC**, confirming removal of this trial's NAT,
ACLs/address groups and temporary neighbor updates. No firmware, pairing, SSID,
HA configuration or production integration code was changed. A separate local
TLS acceptance test follows to assess whether the external endpoint can be
replaced without changing the camera's trust configuration.

## Local TLS/MQTT replacement probe, 2026-10-27 UTC

The next bounded experiment redirected camera TCP 8883 to a local Python TLS
endpoint, alongside the authenticated low-power server. Camera WAN TCP/UDP IPv4
remained blocked in all connection states. The local endpoint generated its
certificate/key in memory, offered the observed TLS 1.2 cipher, and used an SNI
callback for certificate selection. No trust-store or firmware change was made
on the camera. A synthetic client had first verified the server's TLS handshake
and basic MQTT CONNECT/SUBSCRIBE/PING acknowledgements over loopback.

After local authentication and three heartbeat echoes, wake at
**00:02:45.969 UTC** reopened TCP 6668 in **2.393 seconds**. The camera attempted
the redirected TLS service, but rejected the experimental self-signed certificate
at **00:02:51.358 UTC** and **00:02:52.109 UTC**, each time producing
**`TLSV1_ALERT_UNKNOWN_CA`**. No local TLS handshake completed, so no MQTT CONNECT
or application authentication was processed by the stub. The test stopped after
the two failures, before attempting another wake cycle.

This identifies a trust barrier to replacing the observed external TLS service
with a simple local broker. It establishes rejection of this self-signed
certificate, **not** certificate pinning, hostname checking, or the full contents
of the device's trust store. Nor does it rule out a supported firmware
configuration or a different local sleep/wake path. It does not justify adding
an assumed MQTT emulator to the production integration.

Watchdog cleanup completed at **00:03:00 UTC**. Both camera-only rules/groups and
NAT/connection state were removed; temporary TLS, HTTP and keepalive listeners
and observation processes were stopped. A normal HA recovery check decoded a
fresh **640×360** image in **2.319 seconds**, with its cloud-wake counter unchanged
at **8**. No image, credential, private TLS key or raw packet capture was saved.
No HA installation/restart, camera firmware change, re-pairing or physical power
cycle was needed.

The next research boundary is to determine whether endpoint/trust configuration
or a native local sleep transition can avoid this external TLS requirement.
At this stage, testing a public certificate and separating hostname validation
remained pending; the next section records those later controls. Repeated operation with complete WAN
isolation, IPv6 isolation and a supported deployment path remain unproven.

## Public certificate and service-name controls, 2026-10-27 UTC

The next investigation separated public certificate validity, service identity
and device trust. An AP capture confirmed a normal HA image but did not capture
a usable MQTT TLS handshake. A bounded camera-only gateway diversion then
identified an external port-8883 endpoint. An independent TLS certificate query
retrieved its two-certificate Tuya chain. The leaf signature verified under the
second certificate, whose self-signature also verified. Both use RSA-2048 and
SHA-256, have the same Tuya subject/issuer DN, and expire in October 2118.
A later query with the camera's observed SNI returned identical certificate
fingerprints. These public certificates were retained; no private key or raw
packet capture was saved.

A dedicated certificate for an owned lab domain was obtained from Let's Encrypt
through DNS-01. Only a temporary TXT challenge was created; it was removed after
issuance, and no public service, A/AAAA/CNAME record or tunnel was created.
The certificate key and temporary ACME account key stayed in memory. Before the
camera test, an independent local client verified the public chain, owned-domain
hostname, observed TLS 1.2 cipher and MQTT CONNACK. This positive control passed.
The candidate certificate was valid and unrevoked during the camera experiment.

An initial combined low-power/TLS setup captured no new low-power authentication
in 150 seconds and was restored without drawing a certificate conclusion. The
subsequent direct probe preserved the normal HA wake and WAN connectivity,
redirecting only camera TCP 8883 to the test TLS endpoint. At
**00:28:50–00:28:51 UTC**, the camera supplied **`m2.tuyaus.com`** in SNI and
rejected the public owned-domain certificate three times with
**`SSLV3_ALERT_BAD_CERTIFICATE`**. No TLS handshake or MQTT CONNECT completed.
Because both issuer chain and certificate name differed from the real service,
this result alone did not isolate hostname checking from CA trust.

### Controlled CN/SAN comparison

A separate probe therefore held the experimental issuer CA, root/leaf keys,
validity, key usages and TLS settings fixed, varying only the certificate's CN
and DNS SAN names. A local client trusting that test CA first verified the four
variants' expected hostname results. The camera itself was never given the CA.
Its actual SNI remained `m2.tuyaus.com` throughout the completed matrix:

| CN matches requested service | DNS SAN matches | Camera alert | Repetitions |
|---|---|---|---|
| Yes | Yes | `UNKNOWN_CA` | 2 |
| Yes | No | `BAD_CERTIFICATE` | 2 |
| No | Yes | `UNKNOWN_CA` | 2 |
| No | No | `BAD_CERTIFICATE` | 2 |

These eight connections at **00:35:20–00:35:33 UTC** provide strong experimental
evidence of DNS SAN identity checking taking precedence over CN when SAN exists.
Matching the name still failed at the trust barrier. They do not establish leaf
or public-key pinning, enumerate the camera's trust store, or prove that every
public CA is rejected. The alert mapping is observed behavior, not decoded
internal firmware verification flags. Certificate path and service identity
are separate requirements in [RFC 9525](https://www.rfc-editor.org/rfc/rfc9525.html).

One earlier matrix attempt was incomplete because the user-space relay received
a TCP packet aggregated above the interface MTU and its forwarding worker exited.
The bounded watchdog restored that attempt. The laboratory forwarder was then
corrected to segment offloaded TCP packets and recompute IPv4/TCP checksums;
synthetic tests covered payload reassembly, checksums, sequence wrap, FIN and PSH.
The completed matrix handled two aggregated packets and finished all eight
controls. Previous relay packet counts/timings must be interpreted with that
instrumentation limitation; native local TLS rejection alerts remain distinct
from forwarded WAN application traffic.

The public test certificate was revoked at **00:33:28 UTC**, after its own probe
and before the separate ephemeral-CA matrix, which did not reuse it. The temporary
ACME account was deactivated and key broker stopped. DNS queries confirmed zero
challenge/service records for the lab hostname. The name matrix restored its
route at **00:35:35 UTC**. No camera certificate, firmware, pairing or HA
configuration was changed. A final normal-HA check decoded fresh **640×360**
video in **6.466 seconds**, using the existing cloud wake path (counter 15 to 16).
Normal preparation/recovery wakes in this investigation are not offline evidence.

Because no camera handshake completed against either replacement certificate,
local MQTT and the conditional IPv4/IPv6-isolated cycle test did not proceed.
The implementation boundary is now clearer: the tested IP diversion preserves
the camera's requested Tuya service identity, while a certificate for an owned
hostname supplies a different identity. Further discovery must find a supported
endpoint/trust configuration or a native local sleep transition that avoids this
external TLS path. The experiments do not prove impossibility for all firmware
or all alternative mechanisms.

## Final read-only review, 2026-10-27 UTC

### Question, scope and collection

After the TLS name controls, the final bounded task was to look for a supported
stock-device escape from the observed post-wake external dependency: an offline
mode, configurable broker/trust, or a native sleep transition. This round
performed **no DP writes, new wake experiments, firmware changes, pairing,
network interception or HA install/restart**. It reused the existing account
session for two read calls from the installed Python integration:

- `thing.m.device.get`, version 4.1: current device metadata/firmware.
- `tuya.m.device.ref.info.my.list`, version 2.0: matching product schema.

The device/product match was resolved in memory. Only public DP definitions,
firmware versions and read success flags were exported. Current firmware was
**1.1.48**; **21 schema definitions** matched the existing HA cache exactly.
The [public schema](evidence/local-wake/public-schema.json) lets readers inspect
the relevant advertised functions without account/device IDs or live states.

Source inspection covered [account provisioning](../custom_components/tuya_camera/api.py),
the [vendored mobile client](../custom_components/tuya_camera/vendor/tuya_mobile/client.py)
and shared app profiles. The app-profile version identifies the Python client's
signing profile; it is not evidence of the installed phone application's version
or the camera's embedded SDK version. No APK/IPA or camera firmware image was
available in the research materials reviewed. There was **no decompilation,
firmware dump or disassembly**. Public SDK references below describe possible
implementations, not an identification of this unit's internal code.

### Schema result: DP149 remains an open hypothesis

| DP | Advertised code | Type/access | Interpretation within this review |
| --- | --- | --- | --- |
| 145 | `wireless_electricity` | value 0–100, `ro` | Battery telemetry |
| 146 | `wireless_powermode` | enum 0/1, `ro` | Reported power source; not a writable sleep selector |
| 147 | `wireless_lowpower` | value 10–30, `rw` | Low-battery alarm threshold, not an offline mode |
| 149 | `wireless_awake` | bool, `rw` | Candidate awake/sleep function; exact local behavior unverified |

A writable schema entry does not establish transport support, acknowledgement,
effect, persistence or cloud independence. In particular, the previous standby
UDP probes did **not** test a DP149 write over authenticated TCP while awake.
The final review did not test that write either. It would be incorrect to report
that no sleep-related DP exists or that this candidate has been disproved.

The public SDK descriptions are not a safe source for guessing a write value:
the 4.x guide associates boolean values with sleep but later reports `1` for
awake, while the mobile guide treats the DP as awake status. The guide also
places server notification and keepalive preparation in the sleep sequence.
That makes a native transition worth a focused future test, not a demonstrated
way around the external service.

### Public references and what they establish

Reviewed on 2026-10-27; links are primary sources. No complete manuals or binaries
are redistributed here. Section names help locate relevant text if pages move.

| Source / section | Relevant fact | Limit |
| --- | --- | --- |
| [Tuya Keep-Alive and Wake-Up in Low Power](https://developer.tuya.com/en/docs/iot-device-dev/tuyaos-package-ipc-device?id=Kcn1qc5he02rw), low-power protocols | Authenticated keepalive/wake protocol and separate low-power component | Does not supply a verified homeowner setting to choose a local endpoint on this camera |
| [Android Low-Power Camera](https://developer.tuya.com/en/docs/app-development/doorbell?id=Ka6nxw2gncv8t), wake | `wirelessWake` API and DP149 awake status | An API name does not establish LAN transport |
| [iOS Low-Power Camera](https://developer.tuya.com/en/docs/app-development/low-power-doorbell?id=Kad3pl13guhil), wake and battery management | Wake-request success differs from camera awake; DP147 is low-battery threshold | Does not prove an offline transition on this firmware |
| [4.x SDK Development Guide](https://developer.tuya.com/en/docs/iot-device-dev/sdk?id=K95019g5w3eiq), Doorbell feature | Sleep sequence uses `tuya_ipc_book_wakeup_topic`, MQTT socket and heartbeat preparation | Firmware developer API, not evidence of a user-accessible LAN setter; DP149 polarity is inconsistent in the page |
| [5.x SDK guide, Chinese](https://developer.tuya.com/cn/docs/iot-device-dev/IPC_SDK?id=Kaqe10hg0htn5) | Additional public firmware-development reference reviewed | No model-specific endpoint/trust control identified; English page fetch timed out, and this does not identify firmware 1.1.48's SDK |
| [Official Tuya IoT Core SDK](https://github.com/tuya/tuya-iot-core-sdk), Sample application | MQTT initialization supplies `host`, `port` and `cacert` in application code | Capability of a developer-owned program, not a supported configuration interface on this retail camera |
| [Manufacturer product page, SKU 11188736](https://www.positivocasainteligente.com.br/smart-camera-bateria-wifi-11188736/p) | Retail model reference used by the owner | Reviewed product text did not expose offline/broker/trust configuration; no firmware image or service manual was analyzed |

The mobile client's configurable account API URL is unrelated to the camera's
MQTT endpoint/trust. No supported offline/broker/CA setting was identified in
this bounded source/schema review. This is a search result within a stated scope,
not an exhaustive claim about the firmware or proprietary mobile SDK internals.

### Decision and remaining falsifiable questions

The [offline-operation decision](offline-operation.md) is the maintained summary;
[Portuguese readers can start here](offline-operation.pt-BR.md). The findings
support keeping the stock integration's cloud wake rather than shipping the
research server as a fully offline feature. They do not prove that firmware
modification is necessary, that every public CA is rejected, that the device pins
a certificate, or that DP149 cannot solve the transition.

The narrow remaining questions are whether a supported model-specific setting
can change endpoint/trust, and whether an observed native DP149 transition can
return to local low-power authentication without the external TLS service.
Before any new DP experiment, establish command meaning/polarity from normal
behavior and a recovery path; then compare authenticated LAN behavior with the
external service blocked. Merely closing the local control port is insufficient:
require return to authenticated low-power service and another successful local
wake followed by new media. No such experiment is claimed in this report.

The [sanitized evidence bundle](evidence/local-wake/README.md) preserves the new
schema and exact completed TLS matrix events. Chronological tests above remain
the source for E1–E8 in the decision table. Raw private captures and research
scripts are not published, so independent packet-level verification requires a
new experiment on the reader's hardware. The final review changed no camera or
HA configuration and introduced no new temporary network rules to remove.
