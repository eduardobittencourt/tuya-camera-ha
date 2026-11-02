# Contributor guidance

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and
[Development and testing](docs/development/testing.md) for development and validation commands.
Use English for public code comments, documentation and review feedback.

- The product is the UI-configured Home Assistant integration in
  `custom_components/tuya_camera`. Account, signaling, LAN media and WebRTC
  protocols run in Python inside the integration. Do not reintroduce a standalone
  bridge, add-on or credential-managing CLI. Use Home Assistant's FFmpeg executable.
- Keep account setup UI-driven; do not require users to copy protocol identifiers,
  session keys or internal ports into YAML. Keep internal listeners on loopback.
- Share the LAN signaling/DP socket with media. Periodic DP refreshes interrupt
  video on the battery-camera implementation; preserve its session-sharing
  behavior and cover changes with synthetic-camera tests.
- Keep blocking work off Home Assistant's event loop and reuse its async HTTP
  client. Bound queues and tasks, and close sockets and FFmpeg processes on
  cancellation, unload and removal.
- Keep credentials, session IDs, encryption codes, local keys, captured MQTT
  payloads and generated account configurations out of logs and contributions.
  Never log raw protocol output or credential-bearing errors.
  Public app-profile constants in `vendor/tuya_mobile/profiles.py` identify shared
  mobile builds and are not user credentials. Preserve upstream license notices.
- Preserve account configuration and entity unique IDs across upgrades. Add
  regression tests for config-entry migrations.
- Run Python lint/tests, package checks and synthetic-media tests before release.
  Build the HACS archive with `scripts/package_release.py`. Changes to the pinned
  aiortc raw RTP adapter require synthetic H.264 and H.265/datachannel peer tests.
  Keep physical-device verification distinct from synthetic test results.

See [SonarQube Cloud and coverage](docs/development/ci.md) for CI coverage reporting
and review configuration. Fix underlying failures without weakening assertions
or bypassing CI requirements.

## Documentation maintenance

- Keep the root README focused on public Home Assistant use: features,
  requirements, installation, configuration, compatibility limits, support,
  contribution links and licensing. Use the existing brand icon and shared
  section order; preserve each project's actual capabilities and HACS route.
- Keep release announcements and version-specific implementation history in
  CHANGELOG.md. Keep supported upgrade procedures in docs/guides/. Report
  test results in PRs or release notes; do not keep investigation diaries,
  decompilation procedures, local lab setups or obsolete plans in docs/.
  Minimum supported HA versions and current limits belong in the README.
- Use the common docs/ layout: guides/ for users, reference/ for current
  architecture, security and branding, and development/ for testing, CI and
  releases. Use docs/README.md as the documentation map. Link to the authoritative guide
  rather than duplicating detailed configuration or developer commands.
- Keep AGENTS.md limited to contributor navigation and implementation guardrails.
  Keep local deployment notes, credentials, raw captures and work-session
  diaries out of public documentation.
- Update incoming links when moving material. Preserve required attribution
  and distinguish physical-device evidence from synthetic tests.
