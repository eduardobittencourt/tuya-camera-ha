# Recovery after interrupted media cleanup

## Trigger and resulting behavior

The final reader removes its queue before closing the shared camera session.
If that close is cancelled, the source retains the session so its resources
can still be cleaned up. Previously, the next acquire could reuse that partially
closed session or reject it forever as recovering, even with no readers left.
Further image/video requests could therefore fail until the integration reloaded.

Acquisition now retries cleanup of a retained session with no consumers before
allocating the new reader or opening another camera session. Cleanup and new
acquisition remain under the same source lock. The old session stays owned until
close succeeds; a failed or cancelled cleanup can be retried on a later request.
Old codec parameters and activity markers are cleared by the existing stop path.

Sessions with existing consumers retain the prior sharing behavior. In
particular, a failed session with outstanding readers rejects overlapping
acquisition until those readers release. The change does not refresh DP state,
open another signaling socket during active media, alter wire formats or change
account/entity identifiers.

## Regression evidence

- Two unit cases cancel final-reader cleanup with the old failure flag either
  clear or set. Both failed before the fix. They verify that old cleanup finishes
  before the replacement factory runs, metadata is reset and cancellation is
  propagated to the interrupted caller.
- A real TCP RTSP case disconnects a reader, cancels its pending cleanup and
  verifies that a fresh DESCRIBE request uses a replacement session and its codec.
- An additional real synthetic-media case interrupts a LAN session's
  `StreamWriter.wait_closed` after its UDP transport has closed. The next FFmpeg
  snapshot must complete cleanup and reconnect without reloading the source.
  The existing video/audio, shared-socket DP command and final resource-cleanup
  assertions then run against the replacement session.

## Scope of the diagnosis

This establishes a concrete recovery defect, not the definitive cause of every
cold-start image failure. During the earlier HA validation, initial snapshots
after restoring official 0.4.0 recovered following an entry reload; the exact
sequence of that physical-camera failure was not captured. Synthetic cancellation
reproduces one way a source can become stuck and proves the corresponding fix.

## Physical verification

The announced window on 2026-11-02 ran from 00:55:38 to 01:05:47 BRT. The
pre-installation query identified HA 2026.11.0b2 already running on the host.
Runtime commit `b8c8e89` was installed temporarily; all 44 candidate files matched
the package. Account configuration and all 19 entity bindings were preserved,
with 17 entities enabled.

The first cold snapshot succeeded in 6.5 seconds. HLS reception decoded 606
H.264 video frames and 977 AAC audio frames over 63.0 seconds. PIR, night vision
and sensitivity changes were confirmed and restored during playback. Entry
reload preserved availability; the next snapshot succeeded in 2.1 seconds and
the camera returned to standby with zero media processes.

The old stream worker logged an I/O error followed by connection refusal during
intentional entry reload. Post-reload capture and cleanup passed. The physical
checks exercise normal startup/reload and control/media sharing; cancellation
inside final-reader cleanup remains a synthetic fault-injection test.

Official integration 0.4.0 was restored afterward, with all 44 files and
account/entity fingerprints verified. Its first snapshot succeeded in 6.9
seconds. Final state was HA running, integration loaded, camera standby with
zero media processes and all three startup automations restored. The installed
HA Core version remained 2026.11.0b2. Images/audio were processed in memory only.

The observed HA libraries were aiortc 1.15.0, PyAV 19.0.0, aioice 0.10.2 and
TinyTuya 1.20.0. These physical results complement the locked CI environment;
they do not certify other cameras, every cloud/WebRTC path or all HA versions.
