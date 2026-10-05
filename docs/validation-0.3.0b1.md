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

## Published release and HACS installation

On 2026-10-05, the reviewed change was merged and
[0.3.0b1](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.3.0b1)
was published as a prerelease at commit
`196144c407f9211ad441c206c39b8cc18aafffca`. Official HACS/hassfest validation,
Python, Go race/build, synthetic media, secrets and add-on Docker checks passed
on that commit. The release workflow prepared and verified its assets.

- The release ZIP downloaded without GitHub authentication and matched the
  merged integration source and license notices.
- The existing HACS 2.0.5 installation registered the repository as a custom
  integration, enabled prereleases and downloaded `v0.3.0b1` through its normal
  download commands. No manual component-file replacement was used in this step.
- HA configuration validation passed. After a Core restart, HACS and the camera
  integration loaded; HACS reported the release as installed with no pending
  restart or available update. Its update entity tracked the published version.
- All 33 installed files exactly matched the public release ZIP. The previous
  bridge executable was moved aside before restart to force a cache miss;
  startup downloaded a new executable from the public release, matching its
  pinned SHA-256 checksum and owner-only `0700` permissions.
- The same Tuya session, config entry and camera entity were retained. No new
  password, login or device configuration was required. One managed bridge ran.
- Post-installation HLS decoded H.264 1280×720 with AAC mono: 90 video frames
  and 94 audio frames in a six-second segment, with 6.016 seconds of audio.
  A further 92-second run decoded 17 distinct fragments with zero failures.
- Native HA WebRTC negotiated successfully and received H.264 video and Opus
  audio. Two subsequent snapshots were valid, different fresh JPEGs.
- HA served the correct packaged Tuya icon/logo. Camera proxy requests without
  authentication were rejected. Mosquitto and Zigbee2MQTT stayed running.
- Temporary rollback and probe files were removed after validation. No session
  data, identifiers, raw logs or private media were published.

This was the first HACS installation over the existing manually installed beta,
with a fresh bridge download. It was not a blank HA installation or a new-account
test. The original UI-login test and owner's phone image/sound confirmation are
recorded above; phone playback was not separately re-confirmed after migration.

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

The published prerelease can be installed through HACS as a custom repository.
It has not been submitted to the default HACS catalog.
