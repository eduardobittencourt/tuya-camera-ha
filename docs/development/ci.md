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

## SonarQube Cloud setup

Use CI-based analysis with coverage and leave automatic analysis disabled.
The built-in **Sonar way** quality gate and the `previous_version` new-code
period are configured in SonarQube Cloud. CI supplies the integration manifest
version, a full Git history and coverage from the same workflow run. The
scanner's `sonar.qualitygate.wait=true` makes rejected gates fail the job.

Keep the SonarQube Cloud project bound to the correct GitHub repository and
allow the SonarQube Cloud GitHub App to access it. The native app publishes
`SonarCloud Code Analysis` and PR summaries separately from the Actions job.
Validate that check on a real PR before adding it to required status checks;
a successful scanner job alone does not prove that GitHub decoration works.

Fork PRs run tests without the Sonar token. Before merging an external
contribution that needs analysis, review it and bring the change to a branch
in this repository so the ordinary CI scanner can analyze it with coverage.
Before creating that branch, review changes to `sonar-project.properties` and
`.github/workflows/`; re-review each additional change before pushing it to the
analysis branch.
A skipped fork scan must not be treated as a successful Sonar analysis. No
privileged fork-analysis workflow is configured.

PNG files in the integration's brand directory are excluded from textual
analysis to prevent UTF-8 warnings on binary images. Runtime source and
workflow files remain in scope; existing coverage and license boundaries are
unchanged.

References:

- [SonarQube Cloud with GitHub Actions](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/ci-based-analysis/github-actions-for-sonarcloud)
- [GitHub project integration](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/administering-your-projects/devops-platform-integration/github)
