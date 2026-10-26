# Contributing

Bug fixes, documentation improvements and reports from other camera models are
welcome. English and Portuguese are both fine. Read the [community guidelines](CODE_OF_CONDUCT.md)
and [compatibility notes](docs/compatibility.md) before opening a report.

## Report a problem or a working camera

Use the issue forms for bugs, compatibility reports and feature requests.
Include HA/integration versions, host architecture, the retail model, firmware
and what you actually tested. Discovery alone is not a successful media test.
For general help, see [SUPPORT.md](SUPPORT.md).

Never attach credentials, device IDs, serial numbers, session data, local keys,
signed URLs, raw API/MQTT responses, HA backups or private camera recordings.
Use synthetic media for reproducible tests. Security reports belong in the
[private reporting channel](SECURITY.md).

## Change the code

1. Fork the repository and create a branch from `main`.
2. Follow the [development guide](docs/development.md) and repository [AGENTS.md](AGENTS.md).
3. Keep UI configuration automatic. Users should not need keys, device IDs or YAML.
4. Add regression coverage when changing behavior. Update the Python/Go
   contract together when changing the managed executable.
5. Run the checks appropriate to your change and describe the results in the PR.

Changes to Go source require deterministic builds with Go 1.26.8 and updated
binary checksums. See [release preparation](docs/releasing.md). Do not commit
compiled executables or account-specific files. Preserve upstream license notices
when changing vendored code.

Keep PRs focused and explain the user-visible problem and resulting behavior.
Real-camera tests are useful, but never make CI depend on someone's Tuya account.
Maintainers review contributions as time permits.

## Merge and dependency updates

The protected `main` branch requires a pull request, resolved review conversations
and passing Python, Go, synthetic-media, secret-scanning, HACS, hassfest and CodeQL checks
against the current base branch. No mandatory approval count is configured, so
the sole maintainer can merge their own checked contributions. Pull requests use
squash merge; merged branches are deleted automatically. Auto-merge is available
after the required checks pass. Dependabot PRs automatically enable squash
auto-merge for all version changes, including majors, across all three ecosystems.
CodeRabbit must finish successfully and review conversations must be resolved;
automation never dismisses findings or bypasses the required checks.

Dependabot checks GitHub Actions, Python and `bridge/` Go dependencies weekly,
grouping minor/patch version updates per ecosystem and limiting open version-update
PRs to three per ecosystem. Security alerts and security-update PRs are also enabled.
Keep Home Assistant and its pytest plugin together for compatibility. The
workflow only enables auto-merge using the built-in `GITHUB_TOKEN`; no dedicated
automation secret is required. It does not refresh branches, approve workflow
runs or commit generated files. Outdated branches, conflicts, failing checks and
review findings can require maintainer intervention.

Go dependency updates that change the bridge binaries require a maintainer to
regenerate and review `bridge_checksums.json` using Go 1.26.8 and
`scripts/package_release.py`, then commit it to the PR branch. Until the checksums
match, the required Go verification blocks the merge.
No dependency update publishes a release. Compatibility review and real-camera
validation remain part of [release preparation](docs/releasing.md).

Version tags matching `v*` cannot be updated or deleted. Publish fixes under a new
version. CodeQL analyzes Python, Go and GitHub Actions through GitHub's default
setup; its aggregate security result is also required before merge.
