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
makes it available to HACS users who enable beta versions. Versions such as
`0.4.0` are stable: publish with prerelease disabled and mark the release as
latest after reviewing the draft assets and notes.

Never replace published assets or reuse a version for different code. Publish
a new beta for corrections. A beta does not advance the stable release channel.
Verify installation/update through HACS after publication. Updates within the
same domain must preserve existing entries, entity IDs and automations; no user
keys or YAML are required. The 0.4.0b2 change from `tuya_camera_bridge` to
`tuya_camera` requires an explicit reinstall or offline registry migration as
described in [installation](installation.md#updates-and-rediscovery). A file
update and restart alone do not migrate the domain. Rollback across that change
also requires a reinstall or inverse offline registry migration; selecting the
former-domain release in HACS and restarting is insufficient.

Verify HACS repository identity after a cold restart. During the beta transition,
its cached component path remained on the former domain while stable 0.3.x was
latest. That installation needed maintainer-assisted metadata reconciliation and
v0.4.0b2 explicitly selected. For stable 0.4.0, select the new stable release,
disable prereleases, and verify no fixed beta selection remains after restart
and refresh. Confirm HACS downloaded the official ZIP, its installed files match
the release and no old component directory reappears. Legacy cached records may
still require maintainer assistance; uninstall/reinstall alone did not clear
that cache. Manual ZIP installation is the fallback. Avoid instructing users
to edit credential-bearing HA stores.

The repository is in the HACS default catalog. No new catalog PR is required.
`hacs.json` selects the ZIP. Branding remains in the integration's `brand/`
directory. Retain licenses and notices in the archive and follow the
[HACS publishing requirements](https://www.hacs.dev/docs/publish/start/).

The aiortc dependency currently uses an immutable upstream development commit
for PyAV 19 compatibility. Verify that HA installs it without changing HA's own
package pins; see [architecture](architecture.md). Stable 0.4.0 retains the
tested commit after owner acceptance of the beta and review of these limits;
stable status does not establish additional model support, battery endurance or
fully offline wake. Review the dependency pin and peer/media tests before
changing it in a future release.
