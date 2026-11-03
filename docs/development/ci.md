# CI and analysis

[Documentation index](../README.md)

`.github/workflows/ci.yml` defines secret scanning, Python tests, package checks,
synthetic media and Sonar analysis. `.github/workflows/validate.yml` runs HACS and
hassfest. Exact tool pins and commands live in the workflows and requirements
files. Use [testing](testing.md) for local reproduction.

Sonar combines the Python and media coverage artifacts from the same workflow
run, imports JavaScript LCOV for the release gate and reads the project version
from the component manifest. Required reports must be nonempty. Vendored code
has separate license and coverage boundaries; do not exclude runtime modules to
improve metrics. Settings live in `sonar-project.properties` and `.coderabbit.yaml`.

Analysis credentials belong in GitHub secrets. Dependabot uses its own secret
namespace. Fork PRs must have a safe test path without scanner credentials;
never run untrusted PR code with secrets through `pull_request_target`.

Dependabot's auto-merge workflow enables squash auto-merge without checking out
PR code. It does not bypass checks, resolve findings or publish releases.
Repository settings are authoritative for required checks and reviews.
The [release gate](releasing.md) checks the intended release commit.

The required Sonar status check is `SonarQube scan`, provided by GitHub Actions
(app ID `15368`). The scanner runs with `sonar.qualitygate.wait=true`, so this
job fails if analysis fails or the quality gate is rejected. Keep the required
check name aligned with the workflow job; the separate SonarCloud GitHub App
check, `SonarCloud Code Analysis`, is not required by this CI setup. Fork PRs
run the test jobs while `SonarQube scan` is skipped; scanner credentials are
never provided to fork PRs.
