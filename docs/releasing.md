# Preparing a release

A GitHub draft is for maintainer review. HACS users cannot download its assets
until the release is published. Adding a custom repository and acceptance into
the HACS default catalog are separate steps.

## Verify the candidate

1. Keep versions aligned in `manifest.json`, `pyproject.toml`, the changelog and
   `binary_manifest.json`. Review compatibility and security notes.
2. Use Go 1.26.8 to run `scripts/package_release.py --verify`. An intentional Go
   change needs a newly generated and reviewed binary manifest first.
3. Run `scripts/check_repository.py --archive dist/tuya_camera_bridge.zip`.
   Confirm that the archive contains the integration at its root, branding and
   all license notices, and that both Linux executables match their SHA-256 pins.
4. Require green Python, Go race/build, synthetic real-media, secrets, add-on
   Docker build, HACS and hassfest checks on the candidate commit.
5. Review live-camera results and remaining limits. Synthetic success does not
   certify another retail model. Never attach account data or private media.

See [development commands](development.md) and the
[beta validation report](validation-0.3.0b1.md).

## Draft and publish

After the candidate is reviewed and merged, run **Release integration** on the
exact intended commit. The workflow builds reproducible assets and creates or
refreshes a **draft release** for the manifest version (stable for `X.Y.Z`, prerelease for
versions such as `X.Y.Zb1`). It refuses to replace
a published release. Review the full target commit, notes and assets:

- `tuya_camera_bridge.zip`
- `tuya-camera-bridge-linux-amd64`
- `tuya-camera-bridge-linux-arm64`
- `SHA256SUMS`

Publishing is a separate maintainer action. Never replace published executables
or reuse a version for different code: the integration pins executable hashes.
Use a new version and release for corrections. Only beta releases require enabling prereleases
in HACS. Stable releases use the normal download flow. After publication, verify a clean install and an upgrade through HACS,
including automatic executable download, UI login, playback and removal.

For 0.3.0b1, the first HACS download onto the existing beta installation and a
fresh automatic bridge download were verified after publication. The existing
account and camera entity were preserved. See the [validation report](validation-0.3.0b1.md).
This migration check does not represent a blank HA installation or a new account.

## HACS catalog

The repository supports the **custom integration** category and contains one
integration directory. `hacs.json` selects the release ZIP and hides installation
from the development/default branch. This avoids installing code whose executable
assets have not yet been published.

Icons and logos live in the integration's `brand/` directory, supported by HA
2026.3+ and the current HACS validator. This project's minimum HA is 2026.9;
an external Home Assistant brands submission is not required for these assets.
See the [HA announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/).

For default-catalog inclusion, first publish a working release, complete the
public installation check, then follow the current
[HACS publishing requirements](https://www.hacs.xyz/docs/publish/start/) and
[integration requirements](https://www.hacs.xyz/docs/publish/integration/).
Catalog submission and acceptance are not automatic and are not part of creating
the release draft. Keep repository description, topics, issues and community
documentation current.
