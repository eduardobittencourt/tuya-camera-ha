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
4. Add regression coverage when changing behavior. Shared Go changes must keep
   both the managed integration and the compatibility add-on working.
5. Run the checks appropriate to your change and describe the results in the PR.

Changes to Go source require deterministic builds with Go 1.26.8 and updated
binary checksums. See [release preparation](docs/releasing.md). Do not commit
compiled executables or account-specific files. Preserve upstream license notices
when changing vendored code.

Keep PRs focused and explain the user-visible problem and resulting behavior.
Real-camera tests are useful, but never make CI depend on someone's Tuya account.
Maintainers review contributions as time permits.
