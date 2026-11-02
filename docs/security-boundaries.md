# Validation tooling and protocol security boundaries

This review follows the six security findings left on the main-branch Sonar
analysis of commit `b34f0e9`. Findings require analysis of their input sources,
effects and compatibility constraints. No issue state, query exclusion or
security-rule suppression is changed by this review.

## Operator-selected release archive

`scripts/check_repository.py --archive PATH` intentionally accepts a local ZIP
selected by the operator. CI and release workflows select `dist/tuya_camera.zip`.
The checker does not extract members, execute archive code or print file data.
The CLI path selects an input file; it is not an archive member extraction path.

Member names must exactly match the reviewed component files plus LICENSE and
NOTICE. Absolute paths, traversal components and backslashes are rejected.
Every member must match the reviewed file's size and bytes, including the
manifest. The complete archive must match its adjacent SHA256SUMS file.

The size checks also address resource exhaustion from untrusted ZIP input:

- The input must be a regular file. Its size cannot exceed the total reviewed
  file sizes plus 64 KiB and 2 KiB of metadata per member. This rejects excessive
  padding or directory metadata before the ZIP directory is parsed.
- Declared uncompressed member sizes are checked before reading. Actual reads
  are limited to the reviewed file size plus one byte.
- The archive checksum is streamed, and reading SHA256SUMS is bounded by the
  expected checksum-line length plus one byte. The checksum must be a regular file.

These limits accommodate the repository's generated ZIPs and ordinary stored
or deflated archives without supporting arbitrary ZIP comments or extra fields.
Regression tests cover generated packages, malicious names, a compressed member
with one million uncompressed bytes, oversized input, content and checksum
mismatches. Choosing a ZIP outside the repository remains supported and tested.

The path-traversal finding needs contextual review against this read-only
interface. The resource limits are additional hardening, not evidence that the
original checker extracted files or disclosed arbitrary input contents.

## Synthetic WebRTC probe

`scripts/webrtc_probe.py` is test tooling. Its caller starts a synthetic go2rtc
instance with the stream name `camera`; it does not access the user's camera.
The CLI accepts only an integer API port in the range 1 through 65535. The HTTP
scheme, IPv4 loopback host, route and stream query are fixed by the script.
Caller-provided URLs, hostnames, credentials, paths and queries are not accepted.

The HTTP client ignores environment proxies, rejects redirects and limits the
SDP answer to 256 KiB. It reads a fragmented answer through EOF within the HTTP
deadline. Before applying the answer to aiortc, it rejects ICE addresses and
related addresses other than `127.0.0.1`, including mDNS names, LAN addresses,
link-local addresses and IPv6. The peer has no configured STUN/TURN servers.
This closes the separate candidate-address boundary even when HTTP uses loopback.

Tests reject invalid ports before peer creation, verify that redirects are not
followed, and reject external ICE targets before `setRemoteDescription` can
start connectivity checks. The real synthetic H.264/H.265 media tests exercise
the port-only CLI and receive video and audio through go2rtc.

## Protocol hashes

| Location | Purpose | Compatibility constraint |
| --- | --- | --- |
| `media/crypto.py: authenticate` | HMAC-SHA1 media authentication | Both peers must use the camera's wire format. |
| `media/lan.py: LanSession.start` | MD5 media-login token | Firmware expects the token derived from its media password and local key. |
| `vendor/tuya_mobile/client.py: _swap_md5` | Mobile API request canonicalization | The service expects the upstream client's byte ordering. |
| `vendor/tuya_mobile/mqtt_auth.py: _md5hex` | Mobile MQTT authentication derivation | The service expects the upstream nested-MD5 construction. |

These functions implement authentication or request formats; they are not
general password-storage APIs. Replacing their algorithms in only this client
would change authentication bytes and requires protocol compatibility evidence.
The protocol's limitations remain relevant security findings. Existing protocol
vectors and synthetic media protect interoperability, not the cryptographic
strength of the firmware or service. The vendor license notices are preserved.

## Scope

This tooling change does not alter Home Assistant runtime code, account storage,
entity identities, media-session recovery or protocol algorithms. Runtime
startup/recovery investigation is a separate change with its own regressions and
announced physical-camera validation.
