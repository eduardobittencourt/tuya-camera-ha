# Repository quality review

This review targets resource ownership, protocol boundaries and reproducible
validation. Static-analysis ratings complement regression tests and physical
camera checks; they do not establish compatibility with untested hardware.

## Baseline

On 2026-11-01, the main-branch SonarQube Cloud analysis reported 76.1% coverage,
105 open findings, reliability C, security D and maintainability A. The existing
suite passed 73 Python tests and three real synthetic-media tests.

## Changes

- Bound the LAN conversation-to-peer map before admitting a new conversation.
  Previously, authenticated conversations rejected by the eight-channel limit
  could still grow the peer map. A regression sends 100 distinct conversations.
- Give the complete RTSP request a deadline, covering partial headers, bodies
  and interleaved RTCP. Bound response writes and connection shutdown too.
- Keep an acquired camera lease reachable when cancellation arrives immediately
  after acquisition. Closing the RTSP connection can then release its session.
- Bound HTTP relay consumers and response writes, retaining the existing
  four-process streaming limit and cancellation/process-group cleanup.
  Count HTTP clients separately from snapshot and control-session tasks so
  those operations do not exhaust the HTTP admission limit. Regression tests
  cover both concurrent operations and rejection of excess HTTP clients.
- Reject short signaling frames with a protocol error before unpacking fields.
  Split KCP acknowledgement processing and RTSP connection handling into smaller
  units while preserving wire formats and shared-session behavior.
- Propagate cancellation of a delayed control-session release. Remove redundant
  exception subclasses without changing the set of exceptions handled.
- Pin workflow actions to commits, scope PR-read permission to secret scanning,
  restrict media-tool redirects to HTTPS, and verify the MediaMTX archive hash.
- Lock test dependencies and source archives, including build tools. Keep the
  integration's runtime dependency pins and upstream aiortc commit unchanged.
- Restrict the synthetic WebRTC probe to explicit IPv4 loopback HTTP endpoints
  and reject redirects before sending an SDP to another destination.
- Collect Python tooling coverage alongside integration coverage. Exercise
  archive contents/checksums, path rejection, runtime failures, shared local
  operations and dependency-lock consistency. Split composite test assertions
  so a failure identifies the violated condition.

## Findings requiring contextual review

AES-ECB signaling, AES-CBC media, HMAC-SHA1 and the MD5 media-login token are
firmware wire formats. The vendored mobile client's hashes also implement the
upstream mobile protocol. Replacing these algorithms locally would prevent
interoperability; they must not be repurposed for new credential storage.
The protocol tests and synthetic camera retain these compatibility contracts.
No broad Sonar exclusions or security-query suppressions were added.

Some async functions and parameter signatures are required Home Assistant or
transport interfaces even when their current implementations do not await or
use every argument. Preserve the interface contract when reviewing those
findings. Further complexity findings remain candidates for focused changes
with targeted regression coverage, especially battery-camera startup and wake.

`check_archive` never extracts an archive. The subsequent
[security-boundary review](security-boundaries.md) restricts its input to the
repository's `dist/tuya_camera.zip`, rejects escaping symlinks and bounds archive,
member and checksum reads. It also validates member paths, the exact allowed
member set, file contents and the published checksum. Regression tests cover
outside inputs, traversal names and mismatched contents/checksums.

GitHub also reported open Go findings whose paths belong to the removed bridge.
Keep those separate from current Python findings and verify the analysis commit
and language before changing their status. This review does not dismiss them.

## Validation

Local validation on 2026-11-01 passed 128 Python tests, three real synthetic-media
tests and the JavaScript release-gate test. Ruff, actionlint, `pip check`, HACS
archive/content checks and Gitleaks also passed. The clean environment used both
hash-locked requirement files. Combined Python line/branch coverage was 82%;
the JavaScript release gate retained 100% line/branch coverage. Sonar computes
its own metric after importing the CI reports; use the PR analysis for that value.

Run the commands in [development](development.md), including a fresh locked
environment, Python tests, real synthetic media, release-gate tests and archive
checks. The pull request must also pass SonarQube Cloud, CodeQL, CodeRabbit,
secret scanning, HACS and hassfest. Record results for the final commit.

Physical verification is a separate, announced window on the Home Assistant
instance. Check account/entity identity, fresh capture, sustained video/audio,
controls with restoration, reload and final standby/process cleanup. Record
initialization failures and retries explicitly. Never retain private frames,
audio, signed stream URLs or protocol payloads in evidence.

## Physical-camera verification

The announced window on 2026-11-01 ran from 23:02:28 to 23:20:31 BRT on
Home Assistant 2026.10.4. Runtime commit `34c2e7b` passed with the configured
physical camera; these results do not certify other camera models.

- All 44 installed candidate files matched the package. Account configuration
  and all 19 entity bindings remained unchanged, with 17 entities enabled.
- The first candidate snapshot succeeded in 6.1 seconds. HLS playback decoded
  947 H.264 video frames and 959 AAC audio frames over 61.7 seconds.
- PIR, night vision and PIR sensitivity changes were confirmed and restored
  during playback. Reloading the integration preserved availability, and a
  fresh snapshot succeeded in 2.8 seconds. The camera returned to standby with
  zero media processes.
- Official 0.4.0 code was restored afterward, with all package hashes and
  account/entity fingerprints verified. Final state was HA running, integration
  loaded, camera in standby and all three startup automations restored.
  Private images and audio were processed in memory and were not retained.

The first attempt did not reach media tests: HA shutdown stalled with an
`ONVIFDevice.async_stop` task pending and required a container restart. The
successful repeat used a bounded container restart. During intentional entry
reload, the old stream worker logged an I/O error followed by connection
refusal; post-reload capture and cleanup passed. After restoring official
0.4.0, initial snapshot attempts failed until the entry was reloaded; capture
then succeeded in 6.2 seconds. These recovery events are part of the result,
not an assertion that every startup or shutdown was error-free.
