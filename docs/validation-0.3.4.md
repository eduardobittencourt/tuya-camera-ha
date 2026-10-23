# 0.3.4 candidate validation

Candidate prepared and installed for testing on 2026-10-21; published as stable
on 2026-10-23.

## Publication — 2026-10-23

[Version 0.3.4](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.3.4)
was published at 13:19:27 UTC from commit
`c63cdb09986919583bc62edcd80ad15eb14ba280` and marked as the latest stable release.
[CI](https://github.com/eduardobittencourt/tuya-camera-ha/actions/runs/39959818928)
passed Python, Go, secrets and synthetic media checks;
[HACS and hassfest](https://github.com/eduardobittencourt/tuya-camera-ha/actions/runs/39959818834)
also passed on that exact commit. The release workflow rebuilt and verified
the pinned assets before creating the draft.

All four draft assets matched the local verified package byte for byte. After
publication, unauthenticated downloads returned HTTP 200 for the HACS ZIP, both
Linux executables and SHA256SUMS, with matching SHA-256 hashes. The public tag
resolves to the checked commit. The existing HA installation's 40 files and
running executable were verified against this package, and the maintainer
confirmed normal operation before authorizing publication. No fresh-account
setup or HACS UI reinstall was repeated during publication.

The experimental local-wake endpoint is not included in this release. The
installed integration continues to use cloud wake for the tested battery camera.

## Repository reconciliation and local release checks — 2026-10-23

Merge `5229f38` reconciles the candidate with published 0.3.3 commit `1c21bd1`.
The published LAN sensor-registration fix was already included in the candidate;
the reviewed merge preserves the 0.3.4 source tree while incorporating the remote
ancestry. The offline-operation guide now links to a separate sanitized
[wake investigation report](local-wake-investigation.md). Experimental endpoint
scripts and private captures remain outside the repository and release archive.

Local validation of the reconciled candidate passed:

- Ruff and public repository checks.
- 71 non-media Python tests using Python 3.14.8 and the pinned HA test environment.
- Go formatting and `go test -race ./...` with Go 1.26.8.
- Two real synthetic-camera media tests, using FFmpeg, MediaMTX 1.21.1, go2rtc
  1.9.14 and a freshly built Go WebRTC receiver.
- Reproducible Linux amd64/arm64 packaging with `package_release.py --verify`;
  the tracked executable checksums did not change. The HACS ZIP and executable
  contents passed the archive checker.
- Gitleaks 8.30.1 scanned all 144 commits reachable at the merge, with no leaks
  reported. This scan covers the product history, not private research captures.

No product code or Go source changed during reconciliation. No HA installation,
restart, new hardware test, push, tag or GitHub release was performed for these
repository checks. At that stage HACS/hassfest and remote CI on the final
candidate were pending and the latest published release was 0.3.3;
the installed candidate's wake path still uses cloud services. Local-wake
experiments do not establish a supported offline feature.

## Entity policy

Home Assistant integration tests exercise schema-only legacy entities being
disabled, valid reports discovering/re-enabling the same entity ID, invalid
reports being ignored, user-disabled entities staying disabled, and battery
settings/sensors restoring observations and timestamps after reload. Battery
motion/sound entities default to disabled. Reauthentication preserves the
migration marker so it does not reset subsequent user choices.

## Checks

- Python lint and 64 non-media tests passed on the pinned HA test environment
  after removing obsolete standalone-app/config-file tests.
- Two synthetic real-media tests passed with FFmpeg, MediaMTX and go2rtc.
- Go race tests passed for the Go changes; 0.3.4 executables built with Go
  1.26.8 for Linux amd64/arm64 and their pinned checksums were regenerated.
- Deterministic rebuild and archive/repository verification passed.
- Remote HACS/hassfest/secrets checks remain pending. The add-on and its Docker
  build have been removed; the native integration is the sole product.

## Live evidence and limits

Before the entity-discovery changes, the installed 0.3.3 with the battery-session
candidate received battery, power-source and volume observations during HA
snapshot retrieval without the native app. The LAN session later returned to
standby, retaining timestamps with `connection_active: false` and no active
media processes. This demonstrates session closure, not physical sleep or
battery endurance. No camera settings were written in that validation.

The first snapshot returned HTTP 500 after 10.474 seconds; a subsequent JPEG
succeeded in 9.007 seconds. Cold snapshots remain a known limitation. The battery
percentage scale needs verification against the device/app. Audible talkback
is not supported or certified by these tests.

## Installed-candidate test

The QEMU guest channel on `core / VM 100` did not respond; installation used
the existing serial console. All 40 archive members and the preseeded amd64
executable were checksum-verified. `ha core check` passed. After the user
confirmed that the child was awake, Core was restarted and the integration
returned loaded with bridge version 0.3.4 and no reauthentication request.

Before installation, 19 entities were enabled and two were unavailable.
After migration, there were no unavailable enabled entities. Sensors restored
their prior readings/timestamps; controls from the old non-restoring entity
class need rediscovery on this first upgrade. Valid LAN reports subsequently
re-enabled volume and keep-awake under their existing entity IDs.

The first snapshot after startup returned HTTP 500. A command from standby
resent the current volume (80) without changing it: HTTP 200 in 10.282 seconds,
with a new confirmed observation. A subsequent fresh JPEG succeeded in 2.144
seconds (71,403 bytes). No image was saved and no siren/talkback was activated.
The filtered post-restart log check found no Tuya integration errors/warnings.

Final comparison retained all 19 registry IDs: eight entities enabled, eleven
disabled, zero enabled entities unavailable. After media stopped, LAN returned
to standby with no media subprocesses. An integration-only reload returned
HTTP 200 and preserved all six known scalar observations and their original
timestamps, including volume. This exercises real restoration after the new
entity classes have been registered.

Complete the remote release checks before publishing. Battery scaling and
long-term endurance remain unresolved; installation does not establish either.

## Revised integration-only candidate

The first entity policy disabled working controls because the previous entity
class had no stored observations and battery cameras do not spontaneously
report every setting. A bounded native LAN probe recovered night vision, PIR,
sensitivity and other settings through read refresh and delayed reception.
The revised transport requests readable scalar DPs once per connection without
waiting for an immediate acknowledgement; standby still performs no polling.

The standalone add-on, repository metadata, Docker build, ONVIF gateway and
independent login/camera CLI were removed at the owner's request. Managed Go
source moved to `bridge/`; Python starts it without arguments and sends config
on stdin. The camera registry is memory-only. Old Go account files were removed
from HA after the new executable loaded. The HA app inventory contained no
installed Tuya add-on.

A combined cold-media/control test then timed out. With the HA Tuya entry
temporarily disabled and no LAN control client, the new Go executable delivered
a JPEG in 10.983 seconds and the previous executable in 5.167 seconds. This
showed that both executables could still deliver media. Delaying the LAN window
until after the JPEG was unsuccessful: an isolated read obtained no DPs, and
combined HA commands still failed. This experiment was reverted.

Commands now start the existing snapshot path but await LAN readiness separately,
so JPEG completion cannot hold a ready control connection hostage. Snapshot tasks
remain bounded and are canceled on unload. Battery writes receive fresh DP
reports separately from queued acknowledgements. Encrypted TCP tests cover these
sequences, including a pending JPEG and delayed refresh responses.

Real HA still did not confirm a night-vision change. A Tuya Local entry matching
the same camera was temporarily disabled; the failure persisted. Both entries
were re-enabled afterward. Do not attribute the failure to an open app/video.
The owner explicitly confirmed that neither video was open, camera preload was
false, and a process check found no FFmpeg instances between tests.

A structural comparison against the earlier native-app capture established
that CONTROL uses the **account UID**, whereas TinyTuya defaults to the camera
ID. Python now passes the account UID directly to the private LAN payload,
without adding it to the Go contract or diagnostics. The encrypted camera test
requires the distinct account identity. This source revision awaits live
installation/verification; earlier diagnostic attempts alone did not establish
that the identity difference explains the whole failure.

At 18:00 UTC the current Tuya API reported `cloudOnline=false`, with the same
local key as HA. Recent isolated media and LAN attempts timed out. Physical
power/charge confirmation is required before further command validation. Last
loaded HA inventory: 17 enabled entities, zero unavailable; two intentionally
unconfirmed/session-event entities remained disabled. Historical observations
must not be confused with successful current writes.

## Control wake revision after power confirmation

The owner confirmed that the camera was powered and fully charged. A fresh
Tuya metadata read at 18:40 UTC reported online with the same local key. The
account-UID-only revision did not fix cold commands. An isolated continuous
media session did confirm a night-vision change and restoration in roughly
50 ms, while the snapshot-based cold path still failed.

The final source now holds a bounded video-only RTSP consumer during commands,
opens LAN only after the first media bytes, drains initial telemetry before the
read refresh, waits for current known settings, and keeps heartbeats during that
wait. CONTROL is sent on its own and receives a fresh matching report. A two-
second release grace lets consecutive HA calls share the same media session.
The media process copies video without audio/transcoding and has a sixty-second
hard limit. Unload cancels timers and reaps all subprocesses.

At 19:08 UTC an isolated cold test using the installed Python source confirmed
night vision in 26.489 seconds, restored automatic night vision, then changed
and restored PIR and numeric sensitivity. All six writes were confirmed by
local DP reports. A single LAN connection and one initial refresh served the
whole sequence, followed by cleanup. HA-service verification follows below.

## Restored-observation command regression

The initial HA service test failed despite the isolated transport test passing.
A regression test reproduced a difference in startup state: HA restores old
observations for every entity, while the isolated test seeded only two settings.
The initialization gate required all restored values to be reported again,
including unrelated settings/sensors absent from the current session. Commands
now wait only for the requested setting's initial report, drain the pending
batch, and still require a fresh matching report after CONTROL.

Python lint, 67 non-media tests, two synthetic real-media tests, deterministic
Go 1.26.8 binary verification and repository/archive checks passed. The revised
candidate was installed with all 40 files and the executable checksum-verified;
`ha core check` passed before restarting Core. Live service results follow.

The first real HA command sequence succeeded from standby: night vision changed
in 22.386 seconds, followed by restoration, PIR change/restoration and numeric
sensitivity change/restoration. All six services returned HTTP 200 and all
changes had fresh matching observations. The corresponding Tuya Local entry
was then re-enabled. A further cold attempt failed before CONTROL because
the initial setting report never arrived, so this did not establish reliability.

A bounded revision retries the requested setting's read once, five seconds
after an unanswered initial refresh, before sending any CONTROL. The original
20-second initial-report limit and fresh write confirmation remain in place.
Tests cover a dropped initial refresh, a successful retry, no write when the
retry also receives no report, and no dependency on unrelated restored values.
Debug instrumentation records only operation names, timings and return types;
it does not record addresses, identities, values, errors or raw payloads.

With the bounded retry installed and Tuya Local enabled, all six HA services
returned HTTP 200: cold night vision changed in 27.592 seconds; restoration,
PIR change/restoration and sensitivity change/restoration each took 0.9–1.4
seconds. Timing diagnostics show the retry at five seconds and the initial
report arriving before CONTROL. This is successful command evidence, not a
reliability guarantee.

A second run, explicitly starting after LAN standby and zero media processes,
failed again: night vision returned HTTP 500 in 40.878 seconds and resending
the original automatic setting returned HTTP 500 in 46.472 seconds. The HA
state stayed automatic without a fresh observation. A final isolated experiment
bypassed only the initial-report gate, retaining write confirmation, but failed
to obtain media readiness; no LAN operations or writes were executed. Removing
the read gate alone therefore was not validated as a fix and was not applied
to the integration. Both integration entries were re-enabled afterward.

Cold command/media startup remains intermittent. Do not publish this candidate
as a confirmed cold-command fix. Synthetic test success and available entities
do not establish successful current commands.

Final read at 21:59:42 UTC: integration loaded, 17 enabled entities, zero
unavailable enabled entities, LAN/media standby and zero media subprocesses.
Tuya Local was re-enabled and temporary debug logging disabled. The last
reported settings were automatic night vision, PIR off and sensitivity 7.
The maintenance HTTP server and serial connection were closed.

## Native LAN media candidate — 2026-10-22 UTC

This section supersedes the earlier cloud-media cold-command findings for the
new LAN transport only. Installed 40 component files and the Go binary were
verified against the packaged archive, with HA config check, Core restart and
integration reload approved. No release was published.

- 71 Python tests and Ruff passed; Go race tests and build passed; both real
  synthetic H.264/H.265 media tests passed. Release manifest rebuilt with Go
  1.26.8; deterministic packaging and archive checks passed.
- Isolated HA-container playback decoded 1,003 H.264 frames over 65.47 s, with
  PCM16 audio at 8 kHz covering 65.68 s. A LAN command was freshly confirmed
  during playback and the original night vision setting restored.
- HA frontend HLS decoded 757 video frames over 49.059 s, AAC audio over
  49.112 s, and a fresh 640×360 JPEG. Native HA services changed and restored
  night vision, PIR detection and PIR sensitivity, each with a new observation.
- After restoring Tuya Local and reloading this integration, another frontend
  session decoded 751 frames over 48.628 s, with audio over 48.664 s, a fresh
  JPEG and zero cloud wakes for that new LAN session.
- All 17 enabled entities were available. Settings and telemetry received new
  LAN observations. No Tuya Camera Bridge or stream warnings/errors were found
  in the checked runtime log window.

After another reload with no frontend video open, all three native controls
again changed and restored successfully: first session startup took 6.745 s;
subsequent confirmations took 0.279–1.155 s. This validates a bounded command
session independently of an existing frontend stream.

The bridge omits runtime DP refresh queries on its shared media socket because
those requests prevented or interrupted media on this firmware. Values refresh
from camera pushes and new command responses, with historical timestamps kept
for other observations. Cloud wake remains necessary from standby. LAN talkback,
long-duration battery endurance, events and cold operation with WAN blocked
remain unverified. No image, audio, session material or raw protocol log retained.

A stream demux warning was emitted when a frontend source was forcibly closed
for the final reload. No Tuya warning/error accompanied the command-only test.
At shutdown, Tuya Local remained enabled and media subprocesses returned to zero.
The camera connection_status attribute keeps its last video event; consult
active_media_processes and the LAN connection sensor for current activity.
