# Preparing a release

The release contains only the Python integration archive and its SHA-256 checksum.
No Go build, binary manifest or architecture-specific executable is produced.

1. Align the version in `manifest.json`, `pyproject.toml` and `__init__.py`.
2. Run Python lint/tests, synthetic peer and real-media tests, package checks,
   secret scanning, HACS and hassfest. See [development](development.md).
3. Run `python scripts/package_release.py` and
   `python scripts/check_repository.py --archive dist/tuya_camera.zip`.
4. Validate the candidate on the real HA, including media/audio, controls,
   standby, reload and migration with preserved account/entity identities.
5. Record measured results and remaining limits. Never attach private media,
   account sessions, stream URLs or device identifiers.

After merging the reviewed candidate, run **Release integration** on the exact
`main` commit. The release gate requires successful CI (`secrets`, `python`,
`package`, `media`) and validation (`hassfest`, `hacs`) on that same commit.
The workflow creates a draft containing `tuya_camera.zip` and
`SHA256SUMS`. Versions such as `0.4.0b1` are prereleases. Publishing the draft
makes it available to HACS users who enable beta versions.

Never replace published assets or reuse a version for different code. Publish
a new beta for corrections. A beta does not advance the stable release channel.
Verify installation/update through HACS after publication. Existing entries,
entity IDs and automations must survive the update; no user keys or YAML are
required. Rollback uses a previously published version and a Core restart.

The repository is in the HACS default catalog. No new catalog PR is required.
`hacs.json` selects the ZIP. Branding remains in the integration's `brand/`
directory. Retain licenses and notices in the archive and follow the
[HACS publishing requirements](https://www.hacs.dev/docs/publish/start/).

The aiortc dependency currently uses an immutable upstream development commit
for PyAV 19 compatibility. Verify that HA installs it without changing HA's own
package pins; see [architecture](architecture.md). Do not publish a stable
migration release until its dependency and broader compatibility limits have
been reviewed.
