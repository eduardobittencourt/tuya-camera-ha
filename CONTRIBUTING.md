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
and passing Python, Go, synthetic-media, secret-scanning, HACS and hassfest checks
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
Keep Home Assistant and its pytest plugin together for compatibility. The dependency
maintenance workflow refreshes outdated PR branches and explicitly dispatches CI
after its own commits. It runs when PRs change, checks finish, `main` changes,
hourly and on demand. Conflicts and failing checks still require a fix.

For PRs changing only Go module files and the binary manifest, an isolated build
with Go 1.26.8 regenerates checksums without write permissions, secrets or shared
build caches. A separate trusted job validates and commits only that manifest,
then reruns CI. Other bridge changes require the normal manual regeneration.
No dependency update publishes a release. Compatibility review and real-camera
validation remain part of [release preparation](docs/releasing.md).

Version tags matching `v*` cannot be updated or deleted. Publish fixes under a new
version. CodeQL analyzes Python, Go and GitHub Actions through GitHub's default
setup, separately from the required CI jobs.
