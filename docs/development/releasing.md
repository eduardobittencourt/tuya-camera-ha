# Release preparation

[Documentation index](../README.md)

1. Align versions in the component manifest, `pyproject.toml` and `__init__.py`.
2. Run the checks in [testing](testing.md), including synthetic media, archive
   validation, secret scanning, HACS and hassfest.
3. Build `dist/tuya_camera.zip` with `python scripts/package_release.py` and run
   `python scripts/check_repository.py --archive dist/tuya_camera.zip`.
4. Verify account/entity preservation, playback/audio, controls, standby and
   reload on an available camera. Report the model, firmware and test limits in
   the release PR, without private media, identifiers or deployment transcripts.
5. After merge, run **Release integration** on the intended `main` commit.
   The gate requires passing CI and validation on that commit.
6. Review the draft release, ZIP and SHA256SUMS. Publish betas as prereleases;
   publish stable versions with prerelease disabled and the correct latest status.
7. Verify installation/update through HACS and check repository identity after
   a restart. Retain license notices and branding in the payload.

Never reuse a published version or replace its assets. Dependency updates do
not publish a release. Keep `hacs.json`, the minimum HA requirement and test
configuration consistent. Cross-domain upgrades use the
[migration guide](../guides/migrations.md); normal updates preserve entry and
entity IDs. Do not ask users to edit credential-bearing HA registries.
