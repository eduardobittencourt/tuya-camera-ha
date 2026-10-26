// Loaded only from the trusted default branch by the privileged jobs.
const CHECKSUM_PATH = 'custom_components/tuya_camera_bridge/bridge_checksums.json';
const WORKFLOWS = ['ci.yml', 'validate.yml'];
const GO_FILES = new Set(['bridge/go.mod', 'bridge/go.sum', CHECKSUM_PATH]);

function eligible(pr, repository) {
  return pr.state === 'open' && !pr.draft && pr.user.login === 'dependabot[bot]'
    && pr.head.repo?.full_name === repository && pr.base.ref === 'main'
    && pr.head.ref.startsWith('dependabot/');
}

function goOnly(files) {
  return files.some(f => f.filename === 'bridge/go.mod')
    && files.every(f => GO_FILES.has(f.filename) && f.status === 'modified');
}

function recoverable(error) {
  return [404, 405, 409, 422].includes(error.status)
    || (error.name === 'GraphqlResponseError' && error.errors?.length > 0
      && error.errors.every(item => ['UNPROCESSABLE', 'NOT_FOUND', 'CONFLICT'].includes(item.type)));
}

function validateManifest(value, version) {
  const names = ['tuya-camera-bridge-linux-amd64', 'tuya-camera-bridge-linux-arm64'];
  if (!value || Object.keys(value).sort().join(',') !== 'sha256,version'
      || value.version !== version || !value.sha256
      || Object.keys(value.sha256).sort().join(',') !== names.join(',')
      || !names.every(name => /^[a-f0-9]{64}$/.test(value.sha256[name]))) {
    throw new Error('Invalid generated bridge checksum manifest');
  }
  return JSON.stringify(value, null, 2) + '\n';
}

async function dispatchChecks(github, repo, branch, onlyMissing = false, sha = '') {
  for (const workflow_id of WORKFLOWS) {
    if (onlyMissing) {
      const {data} = await github.rest.actions.listWorkflowRuns({
        ...repo, workflow_id, head_sha: sha, per_page: 1,
      });
      if (data.total_count) continue;
    }
    // GITHUB_TOKEN pushes do not automatically run CI; dispatch explicitly.
    await github.rest.actions.createWorkflowDispatch({...repo, workflow_id, ref: branch});
  }
}

async function dispatchChecksumBuild(github, repo, pr, retryFailed = false) {
  const workflow_id = 'dependency-checksums.yml';
  const {data} = await github.rest.actions.listWorkflowRuns({
    ...repo, workflow_id, head_sha: pr.head.sha, per_page: 1,
  });
  const latest = data.workflow_runs?.[0];
  if (!data.total_count || (retryFailed && latest?.status === 'completed' && latest.conclusion !== 'success')) {
    // Runs in the PR branch's security/cache context, never the default branch's.
    await github.rest.actions.createWorkflowDispatch({...repo, workflow_id, ref: pr.head.ref});
  }
}

async function checksumCandidate(github, context, pr, files) {
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  if (!eligible(pr, repository) || !goOnly(files)) return null;
  // Discover results by immutable head, even if a concurrency queue replaced
  // the workflow_run notification with an unrelated maintenance trigger.
  const {data} = await github.rest.actions.listWorkflowRuns({
    ...context.repo, workflow_id: 'dependency-checksums.yml',
    head_sha: pr.head.sha, status: 'success', per_page: 1,
  });
  const run = data.workflow_runs[0];
  if (!run || run.conclusion !== 'success' || run.head_repository?.full_name !== repository
      || run.status !== 'completed' || run.head_sha !== pr.head.sha || run.head_branch !== pr.head.ref
      || !['pull_request', 'workflow_dispatch'].includes(run.event)) return null;
  const {data: workflow} = await github.rest.actions.getWorkflow({
    ...context.repo, workflow_id: 'dependency-checksums.yml',
  });
  if (run.workflow_id !== workflow.id) return null;
  return {number: pr.number, sha: run.head_sha, run_id: run.id};
}

async function needsChecksums(github, repo, pr, files) {
  if (!goOnly(files)) return false;
  if (!files.some(f => f.filename === CHECKSUM_PATH)) return true;
  const {data} = await github.rest.actions.listWorkflowRuns({
    ...repo, workflow_id: 'ci.yml', head_sha: pr.head.sha, per_page: 1,
  });
  const run = data.workflow_runs[0];
  if (run?.conclusion !== 'failure') return false;
  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
    ...repo, run_id: run.id, per_page: 100,
  });
  return jobs.some(job => job.name === 'go' && job.steps.some(step =>
    step.name === 'Run python3 scripts/package_release.py --verify' && step.conclusion === 'failure'));
}

async function manage({github, context, core}) {
  const repo = context.repo;
  const repository = `${repo.owner}/${repo.repo}`;
  const {data: main} = await github.rest.repos.getBranch({...repo, branch: 'main'});
  // Auto-merges made with GITHUB_TOKEN may not emit workflow-triggering pushes.
  await dispatchChecks(github, repo, 'main', true, main.commit.sha);
  const prs = await github.paginate(github.rest.pulls.list, {
    ...repo, state: 'open', base: 'main', sort: 'created', direction: 'asc', per_page: 100,
  });
  const candidates = [];
  for (const entry of prs) {
    if (entry.user.login !== 'dependabot[bot]') continue;
    try {
      const {data: pr} = await github.rest.pulls.get({...repo, pull_number: entry.number});
      if (!eligible(pr, repository)) continue;
      if (!pr.auto_merge && !['unknown', 'dirty'].includes(pr.mergeable_state)) {
        if (pr.mergeable_state === 'clean') {
          // GitHub only offers auto-merge while requirements are outstanding.
          // The normal merge endpoint still enforces every repository rule.
          await github.rest.pulls.merge({
            ...repo, pull_number: pr.number, sha: pr.head.sha, merge_method: 'squash',
          });
          core.info(`Merged ready PR #${pr.number}.`);
          continue;
        } else {
          await github.graphql(`mutation($id:ID!) {
            enablePullRequestAutoMerge(input:{pullRequestId:$id,mergeMethod:SQUASH}) {
              pullRequest { number }
            }
          }`, {id: pr.node_id});
        }
      }
      const {data: comparison} = await github.rest.repos.compareCommitsWithBasehead({
        ...repo, basehead: `${pr.base.sha}...${pr.head.sha}`,
      });
      if (comparison.behind_by > 0) {
        await github.rest.pulls.updateBranch({
          ...repo, pull_number: pr.number, expected_head_sha: pr.head.sha,
        });
        await dispatchChecks(github, repo, pr.head.ref);
        core.info(`Updated PR #${pr.number}; checks will run again.`);
        continue;
      }
      const files = await github.paginate(github.rest.pulls.listFiles, {
        ...repo, pull_number: pr.number, per_page: 100,
      });
      // Recheck the immutable head after the paginated file list.
      const {data: current} = await github.rest.pulls.get({...repo, pull_number: pr.number});
      if (current.head.sha !== pr.head.sha) continue;
      if (await needsChecksums(github, repo, pr, files)) {
        const candidate = await checksumCandidate(github, context, pr, files);
        if (candidate) candidates.push(candidate);
        else await dispatchChecksumBuild(github, repo, pr,
          ['schedule', 'workflow_dispatch'].includes(context.eventName));
      } else {
        await dispatchChecks(github, repo, pr.head.ref, true, pr.head.sha);
      }
    } catch (error) {
      // Conflicts and concurrent merges should not prevent other PRs progressing.
      if (recoverable(error)) {
        core.warning(`PR #${entry.number} changed or cannot progress yet (${error.status ?? error.name}).`);
      } else {
        throw error;
      }
    }
  }
  const {data: latest} = await github.rest.repos.getBranch({...repo, branch: 'main'});
  await dispatchChecks(github, repo, 'main', true, latest.commit.sha);
  core.setOutput('checksum_candidates', JSON.stringify(candidates));
}

async function publish({github, context, core}, candidate, value) {
  const repo = context.repo;
  const {data: pr} = await github.rest.pulls.get({...repo, pull_number: candidate.number});
  if (!eligible(pr, `${repo.owner}/${repo.repo}`) || pr.head.sha !== candidate.sha) {
    core.info('PR changed during the build; leaving the new head untouched.');
    return;
  }
  const {data: manifest} = await github.rest.repos.getContent({
    ...repo, path: 'custom_components/tuya_camera_bridge/manifest.json', ref: candidate.sha,
  });
  const version = JSON.parse(Buffer.from(manifest.content, 'base64').toString()).version;
  const content = validateManifest(value, version);
  const {data: previous} = await github.rest.repos.getContent({
    ...repo, path: CHECKSUM_PATH, ref: candidate.sha,
  });
  if (Buffer.from(previous.content, 'base64').toString() === content) {
    await dispatchChecks(github, repo, pr.head.ref, true, pr.head.sha);
    return;
  }
  const {data: parent} = await github.rest.git.getCommit({...repo, commit_sha: candidate.sha});
  const {data: tree} = await github.rest.git.createTree({
    ...repo, base_tree: parent.tree.sha,
    tree: [{path: CHECKSUM_PATH, mode: '100644', type: 'blob', content}],
  });
  const {data: commit} = await github.rest.git.createCommit({
    ...repo, message: 'chore(deps): regenerate bridge checksums with Go 1.26.8',
    tree: tree.sha, parents: [candidate.sha],
  });
  // Fast-forward only: a concurrent Dependabot rebase must never be overwritten.
  await github.rest.git.updateRef({
    ...repo, ref: `heads/${pr.head.ref}`, sha: commit.sha, force: false,
  });
  await dispatchChecks(github, repo, pr.head.ref);
}

async function releaseGate({github, context}) {
  const workflows = {'ci.yml': ['secrets', 'python', 'go', 'media'],
    'validate.yml': ['hassfest', 'hacs']};
  for (const [workflow_id, names] of Object.entries(workflows)) {
    const {data} = await github.rest.actions.listWorkflowRuns({
      ...context.repo, workflow_id, head_sha: context.sha, branch: 'main', per_page: 1,
    });
    const run = data.workflow_runs[0];
    if (!run || run.status !== 'completed' || run.conclusion !== 'success') {
      throw new Error(`${workflow_id} must pass on this exact main commit before drafting a release`);
    }
    const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
      ...context.repo, run_id: run.id, per_page: 100,
    });
    if (!names.every(name => jobs.some(job => job.name === name && job.conclusion === 'success'))) {
      throw new Error(`Missing successful release checks in ${workflow_id}`);
    }
  }
}

module.exports = {eligible, goOnly, validateManifest, dispatchChecks, dispatchChecksumBuild,
  checksumCandidate, manage, publish, releaseGate};
