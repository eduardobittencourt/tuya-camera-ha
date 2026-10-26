# Stable Python integration — 0.4.0

Version 0.4.0 promotes the validated Tuya Camera Python integration to the stable
release channel after the owner confirmed normal operation on the real camera
and explicitly requested stable publication. Runtime differences from 0.4.0b2
are limited to the version strings in the manifest and runtime module. Protocol
implementations and dependency requirements are unchanged.

## Automated validation

73 Python tests and three real synthetic-media cases passed for the stable
candidate. Coverage includes HA setup/config flows, controls, lifecycle, AES/KCP,
H.264 aiortc peers and H.265/datachannel handshake. The media cases use actual
FFmpeg, encrypted synthetic Tuya LAN transport, HLS/WebRTC and codec conversion.
Ruff, Python dependency consistency, release gate and deterministic package
checks passed. A source comparison against 0.4.0b2 confirmed only integration
version strings changed; no protocol or dependency update is part of promotion.

## Promotion baseline

The published [0.4.0b2 validation](validation-0.4.0b2.md) used HA Core 2026.10.4,
Linux amd64, and the same Positivo battery camera, firmware 1.1.48. HACS installed
the official package; all 44 files matched the release. Account data, the entry
ID and entity/device bindings were preserved (19 registry entries, 17 enabled).

That installation decoded 703 H.264 video / 723 AAC audio frames over 63.12 s,
confirmed six control changes/restorations, reloaded in 0.493 s, returned a fresh
JPEG in 2.413 s and reached standby with zero owned media processes. The owner
subsequently confirmed the camera worked correctly and accepted stable promotion.
These measurements are the beta baseline, not post-publication 0.4.0 results.

## Dependency review and scope

On 2026-10-26 the [official PyPI metadata](https://pypi.org/pypi/aiortc/json)
still listed aiortc 1.15.0 with
`av>=14,<18`, incompatible with HA's PyAV 19. Stable 0.4.0 therefore retains the
same immutable official upstream compatibility commit tested during the beta;
see [architecture](architecture.md#dependencies-and-compatibility). No dependency
constraint is bypassed and no HA package is downgraded. Installation still needs
GitHub/Python package-index access. A compatible published aiortc release remains
preferable for a future tested dependency update.

Stable publication does not expand real-device coverage beyond this unit. Other
models, long standby, battery endurance, fully offline wake, PTZ and talkback
remain outside the validated claims. Cloud H.265 has real-camera evidence from
the Python migration; H.264 cloud peer coverage is synthetic.

## Installation identity

The domain/directory remains `tuya_camera` and the archive `tuya_camera.zip`.
Users already on 0.4.0b2 retain their account and entities. When installing the
stable release, select 0.4.0 in HACS and disable prereleases; the beta pin is no
longer needed once the stable channel describes the same domain.

Old `tuya_camera_bridge` installations still need explicit reinstall or operator
migration, and stale HACS repository identity may require maintainer assistance.
The [installation procedure](installation.md#updates-and-rediscovery) includes
the manual ZIP fallback. Stable publication does not automatically migrate
former-domain account or registry entries. Downgrades across domains need the
inverse procedure or a clean reinstall.
