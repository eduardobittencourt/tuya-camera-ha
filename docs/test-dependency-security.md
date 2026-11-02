# Validation dependency security review

On 2026-11-02, the repository had 42 open Dependabot alerts in
`requirements-test.txt`: one for uv and 41 for Pillow. This lock installs the
development and CI validation environment. It is not included in the HACS ZIP.
The integration's runtime requirements are declared separately in its manifest;
the Home Assistant installation also has its own dependency constraints.
An alert's presence in this test lock does not establish runtime exposure in a
particular user's HA instance, or imply that their instance is unaffected.

## Compatible uv fix

The [uv advisory GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62)
affects versions below 0.13.4 and concerns trust in a compromised certificate
authority chain. The previous test lock selected uv 0.12.23 through
Home Assistant 2026.10.2.

Updating the validation pair to Home Assistant 2026.10.4 and
`pytest-homeassistant-custom-component` 0.13.375 selects uv 0.13.5 through normal
dependency resolution. The hash-locked diff changes only those three packages.
Build-tool pins, integration runtime requirements and the aiortc source commit
remain unchanged. No resolver override or ignored dependency conflict is used.

Manual validation on 2026-11-02 used a fresh environment installed from both hash-locked requirement
files, `uv pip check`, Ruff, the Python suite, real synthetic media, the release
gate and generated HACS package checks. Synthetic peers do not test physical
devices. Changing this development environment does not update the user's HA.

## Remaining Pillow constraint

The current alert snapshot identifies Pillow 13.0.0 as the first patched version.
However, [Home Assistant 2026.10.4](https://pypi.org/project/homeassistant/2026.10.4/)
requires Pillow 12.3.0 exactly. Its matching pytest plugin requires that same HA
version. The refreshed lock therefore retains Pillow 12.3.0 and its alerts.

Install Pillow 13 only after a compatible HA/plugin pair permits it and the
fresh locked installation and regression suites pass. Forcing an override would
discard HA's dependency contract and does not validate compatibility. The
remaining alerts are neither dismissed nor described as fixed by this change.
Any update to Pillow in a deployed HA instance requires its own supported
Home Assistant update path; this repository's test lock is not that update path.
