# Beta validation

Validation on 2026-10-05 used Home Assistant OS with Core 2026.9.4 on Linux
amd64 and one Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736),
firmware 1.1.48, signed in through Tuya Smart. The owner identified the retail
model from the [manufacturer listing](https://www.positivocasainteligente.com.br/smart-camera-bateria-wifi-11188736/p).
The camera advertised HEVC 1920×1080 and signed 16-bit PCM at 8 kHz mono.
Session material remained inside Home Assistant;
no credentials, camera IDs, media URLs, recordings or images are included here.

## Findings and fixes

The original RTP forwarder replaced sampling timestamps with packet arrival
wall time. Bursts collapsed audio intervals, and timestamps that differed by
one MPEG-TS tick became identical after MP4 time-base conversion. Native HA
HLS then failed with an invalid-argument mux error. Forwarding now rebases the
camera's original clock once per media stream and preserves sample intervals,
frame fragmentation, sequence numbers and timestamp wraparound.

Tuya codec 101 was also incorrectly advertised as G.711 mu-law. Its two-byte
PCM samples were interpreted as two one-byte samples, doubling audio duration.
HEVC data-channel audio now uses RTP L16 with little-to-big-endian sample
conversion and a dynamic payload type. Native WebRTC audio retains its existing
negotiated-track path. HEVC video now triggers the activity heartbeat.

## Verified

- Tuya Smart login through the HA configuration UI, session persistence without
  saving the account password, discovery and a loaded native camera entity.
- Real source decoding: HEVC 1920×1080 video; corrected source audio is L16 PCM.
- Authenticated HA HLS: decoded H.264 1280×720 and AAC mono. A six-second video
  segment contained 90 video frames and 94 AAC frames, representing 6.016
  seconds of audio instead of the previous doubled duration.
- Five-minute native HLS run: 53 distinct fragments decoded, with no request
  or decode failures.
- Managed bridge SIGKILL: HA marked the camera unavailable, automatically
  started a replacement bridge in 3.61 seconds, and returned a fresh snapshot
  with new video activity after 11.38 seconds. Exactly one bridge remained.
  No HA restart or Tuya login was required.
- Two independent JPEG requests produced valid, different fresh snapshots.
- Native HA WebSocket WebRTC negotiation, followed by actual H.264 and Opus RTP
  reception in the HA network namespace. This used the installed HA go2rtc
  provider, not only a separate synthetic signaling server.
- The owner confirmed image and audible sound on the phone after enabling the
  player's sound. This adds an end-user playback check to protocol-level tests.
- Bridge/relay memory during one HLS viewer stayed near 120 MiB. CPU samples
  ranged from approximately 65–74% of one core for software HEVC decoding and
  H.264 720p/15 fps encoding, including the bridge. These measurements exclude
  the rest of HA and are not limits or guarantees for other cameras.
- 43 Python unit/lifecycle tests and two synthetic real-media tests passed.
  The synthetic tests exercise H.264/H.265, audio, native HLS, go2rtc WebRTC,
  fresh snapshots and source loss. Go race tests include six regressions for
  RTP burst timing, frame fragmentation, sequence/timestamp wrap, PCM conversion,
  SDP codec selection and concurrent forwarding/lifecycle operations.
- CI checks Python, Go race/build, real media, secrets and the compatibility
  add-on Docker build. Both release architectures have pinned SHA-256 checksums.

## Limits

The native WebRTC receiver ran in the HA network namespace. Phone playback was
confirmed by the owner; the browser/app version and local/remote network path
were not recorded. This does not validate every Tuya camera or firmware.

A short live-media test does not establish 24-hour reliability, recovery after
camera power loss or a real WAN interruption. Synthetic source loss and managed
bridge failure cover separate failure paths. Tuya authentication/signaling still
require internet access; local-only/offline operation has not been established.
Battery endurance, the camera's power state during testing and long idle/wake
cycles were not measured. See [compatibility](compatibility.md).

The installed beta is from the development branch. The GitHub release remains
a draft; a general first installation through HACS requires published assets.
