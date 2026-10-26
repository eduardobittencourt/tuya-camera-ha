const {test} = require('node:test');
const assert = require('node:assert/strict');
const {eligible, goOnly, validateManifest, dispatchChecks, dispatchChecksumBuild,
  checksumCandidate, manage, publish, releaseGate} =
  require('../scripts/dependency_automation.cjs');

const repository = 'owner/camera';
function pr() {
  return {state: 'open', draft: false, user: {login: 'dependabot[bot]'},
    head: {repo: {full_name: repository}, ref: 'dependabot/go_modules/update', sha: 'old'},
    base: {ref: 'main'}};
}
const context = {repo: {owner: 'owner', repo: 'camera'}, sha: 'release-sha'};
const candidate = {number: 10, sha: 'old'};
const checksums = {version: '0.3.4', sha256: {
  'tuya-camera-bridge-linux-amd64': 'a'.repeat(64),
  'tuya-camera-bridge-linux-arm64': 'b'.repeat(64),
}};

test('only open same-repository Dependabot PRs targeting main are eligible', () => {
  assert.equal(eligible(pr(), repository), true);
  for (const change of [p => p.user.login = 'someone', p => p.draft = true,
    p => p.state = 'closed', p => p.base.ref = 'other', p => p.head.ref = 'feature',
    p => p.head.repo = null, p => p.head.repo.full_name = 'fork/camera']) {
    const value = pr();
    change(value);
    assert.equal(eligible(value, repository), false);
  }
});

test('checksum builds reject code, workflow, renamed and deleted files', () => {
  const module = {filename: 'bridge/go.mod', status: 'modified'};
  assert.equal(goOnly([module, {filename: 'bridge/go.sum', status: 'modified'}]), true);
  assert.equal(goOnly([{filename: 'bridge/go.sum', status: 'modified'}]), false);
  for (const filename of ['scripts/package_release.py', '.github/workflows/ci.yml', 'bridge/main.go']) {
    assert.equal(goOnly([module, {filename, status: 'modified'}]), false);
  }
  for (const status of ['removed', 'renamed', 'added']) {
    assert.equal(goOnly([{...module, status}]), false);
  }
});

test('only exact version and two SHA-256 pins can enter the privileged commit', () => {
  assert.equal(JSON.parse(validateManifest(checksums, '0.3.4')).version, '0.3.4');
  for (const value of [null, {...checksums, version: 'other'}, {...checksums, script: 'bad'},
    {...checksums, sha256: {}}, {...checksums, sha256: {...checksums.sha256, extra: 'a'.repeat(64)}},
    {...checksums, sha256: {...checksums.sha256, 'tuya-camera-bridge-linux-amd64': 'bad'}}]) {
    assert.throws(() => validateManifest(value, '0.3.4'));
  }
});

test('dispatches only missing workflows and pins lookup to the current head', async () => {
  const calls = [];
  const github = {rest: {actions: {
    listWorkflowRuns: async args => {
      assert.equal(args.head_sha, 'sha');
      return {data: {total_count: args.workflow_id === 'ci.yml' ? 1 : 0}};
    },
    createWorkflowDispatch: async args => calls.push(args),
  }}};
  await dispatchChecks(github, context.repo, 'dependabot/update', true, 'sha');
  assert.deepEqual(calls.map(c => [c.workflow_id, c.ref]), [['validate.yml', 'dependabot/update']]);
});

test('checksum builds dispatch on the PR branch and do not duplicate existing runs', async () => {
  const calls = [];
  let count = 0;
  const github = {rest: {actions: {
    listWorkflowRuns: async args => {
      assert.equal(args.head_sha, 'old');
      return {data: {total_count: count}};
    },
    createWorkflowDispatch: async args => calls.push(args),
  }}};
  await dispatchChecksumBuild(github, context.repo, pr());
  count = 1;
  await dispatchChecksumBuild(github, context.repo, pr());
  assert.deepEqual(calls.map(c => [c.workflow_id, c.ref]),
    [['dependency-checksums.yml', 'dependabot/go_modules/update']]);
});

test('checksum retries only dispatch completed failures when retry is allowed', async () => {
  for (const latest of [{status: 'completed', conclusion: 'failure'},
    {status: 'completed', conclusion: 'cancelled'}, {status: 'completed', conclusion: 'success'},
    {status: 'in_progress', conclusion: null}, {status: 'queued', conclusion: null}]) {
    const calls = [];
    const github = {rest: {actions: {
      listWorkflowRuns: async () => ({data: {total_count: 1, workflow_runs: [latest]}}),
      createWorkflowDispatch: async args => calls.push(args),
    }}};
    await dispatchChecksumBuild(github, context.repo, pr());
    assert.equal(calls.length, 0);
    await dispatchChecksumBuild(github, context.repo, pr(), true);
    assert.equal(calls.length, latest.status === 'completed' && latest.conclusion !== 'success' ? 1 : 0);
  }
});

test('privileged publication rejects foreign, failed, forged and stale build runs', async () => {
  const original = {id: 789, status: 'completed', conclusion: 'success', head_repository: {full_name: repository},
    event: 'workflow_dispatch', workflow_id: 123, head_sha: 'old', head_branch: pr().head.ref};
  const files = [{filename: 'bridge/go.mod', status: 'modified'}];
  let run = original;
  const github = {rest: {actions: {
    getWorkflow: async () => ({data: {id: 123}}),
    listWorkflowRuns: async args => {
      assert.equal(args.head_sha, 'old');
      assert.equal(args.status, 'success');
      return {data: {workflow_runs: [run]}};
    },
  }}};
  const current = {...pr(), number: 10};
  // No workflow_run payload: the successful build is recovered from GitHub.
  assert.deepEqual(await checksumCandidate(github, context, current, files), {...candidate, run_id: 789});
  for (const change of [run => run.conclusion = 'failure', run => run.workflow_id = 456,
    run => run.head_sha = 'stale', run => run.head_branch = 'other', run => run.event = 'push',
    run => run.head_repository = {full_name: 'fork/camera'}]) {
    run = {...original};
    change(run);
    assert.equal(await checksumCandidate(github, context, current, files), null);
  }
  run = original;
  files.push({filename: 'scripts/package_release.py', status: 'modified'});
  assert.equal(await checksumCandidate(github, context, current, files), null);
});

test('stale build results cannot write to a changed or closed PR', async () => {
  for (const change of [p => p.head.sha = 'new', p => p.state = 'closed']) {
    const current = pr();
    change(current);
    const github = {rest: {pulls: {get: async () => ({data: current})}}};
    await publish({github, context, core: {info() {}}}, candidate, checksums);
  }
});

function managementFixture(problem, state = 'blocked') {
  const calls = {merged: [], warnings: [], branches: 0, graphql: 0, outputs: {}};
  const github = {rest: {
    repos: {
      getBranch: async () => {calls.branches++; return {data: {commit: {sha: 'main'}}};},
      compareCommitsWithBasehead: async args => {
        assert.equal(args.basehead, 'main...old');
        return {data: {behind_by: 0}};
      },
    },
    pulls: {
      list() {}, listFiles() {},
      get: async ({pull_number}) => {
        if (pull_number === 1 && problem?.status === 404) throw problem;
        return {data: {...pr(), number: pull_number, node_id: String(pull_number),
          mergeable_state: pull_number === 1 ? state : 'clean'}};
      },
      merge: async ({pull_number}) => calls.merged.push(pull_number),
    },
    actions: {listWorkflowRuns: async () => ({data: {total_count: 1}})},
  },
  graphql: async () => {calls.graphql++; if (problem) throw problem;},
  paginate: async fn => fn === github.rest.pulls.list
    ? [1, 2].map(number => ({number, user: {login: 'dependabot[bot]'}}))
    : [{filename: 'pyproject.toml', status: 'modified'}]};
  const core = {setOutput: (name, value) => calls.outputs[name] = value,
    info() {}, warning: message => calls.warnings.push(message)};
  return {options: {github, context, core}, calls};
}

test('a rejected auto-merge does not block later PRs or final main checks', async () => {
  for (const type of ['UNPROCESSABLE', 'NOT_FOUND', 'CONFLICT']) {
    const error = Object.assign(new Error('rejected'), {
      name: 'GraphqlResponseError', errors: [{type}],
    });
    const {options, calls} = managementFixture(error);
    await manage(options);
    assert.deepEqual(calls.merged, [2]);
    assert.equal(calls.warnings.length, 1);
    assert.equal(calls.branches, 2);
  }
});

test('maintenance recovers a publishable build after an unrelated event replaces its notification', async () => {
  const {options, calls} = managementFixture(null);
  const {github} = options;
  const current = {...pr(), number: 10, auto_merge: {}};
  github.rest.pulls.get = async () => ({data: current});
  github.paginate = async fn => fn === github.rest.pulls.list
    ? [{number: 10, user: current.user}] : [{filename: 'bridge/go.mod', status: 'modified'}];
  github.rest.actions.getWorkflow = async () => ({data: {id: 123}});
  github.rest.actions.listWorkflowRuns = async args => ({data: {
    total_count: 1,
    workflow_runs: args.workflow_id === 'dependency-checksums.yml' ? [{id: 789, workflow_id: 123,
      status: 'completed', conclusion: 'success', event: 'workflow_dispatch',
      head_repository: {full_name: repository}, head_sha: 'old', head_branch: current.head.ref}] : [],
  }});
  await manage({...options, context: {...context, eventName: 'schedule'}});
  assert.deepEqual(JSON.parse(calls.outputs.checksum_candidates), [{number: 10, sha: 'old', run_id: 789}]);
});

test('failed build completion events do not cause immediate checksum retry loops', async () => {
  for (const eventName of ['workflow_run', 'schedule', 'workflow_dispatch']) {
    const {options} = managementFixture(null);
    const {github} = options;
    const dispatches = [];
    const current = {...pr(), number: 10, auto_merge: {}};
    github.rest.pulls.get = async () => ({data: current});
    github.paginate = async fn => fn === github.rest.pulls.list
      ? [{number: 10, user: current.user}] : [{filename: 'bridge/go.mod', status: 'modified'}];
    github.rest.actions.listWorkflowRuns = async args => ({data: {
      total_count: args.status === 'success' ? 0 : 1,
      workflow_runs: args.status === 'success' ? [] : [{status: 'completed', conclusion: 'failure'}],
    }});
    github.rest.actions.createWorkflowDispatch = async args => dispatches.push(args);
    await manage({...options, context: {...context, eventName}});
    assert.deepEqual(dispatches.map(d => d.workflow_id), eventName === 'workflow_run'
      ? [] : ['dependency-checksums.yml']);
  }
});

test('a PR closed during enumeration does not block later PRs', async () => {
  const {options, calls} = managementFixture({status: 404});
  await manage(options);
  assert.deepEqual(calls.merged, [2]);
  assert.equal(calls.warnings.length, 1);
});

test('unknown or conflicting mergeability does not attempt auto-merge activation', async () => {
  for (const state of ['unknown', 'dirty']) {
    const {options, calls} = managementFixture(null, state);
    await manage(options);
    assert.equal(calls.graphql, 0);
    assert.deepEqual(calls.merged, [2]);
  }
});

test('authentication, schema and unexpected GraphQL failures stay visible', async () => {
  for (const problem of [{status: 401}, {status: 500},
    {name: 'GraphqlResponseError', errors: [{type: 'FORBIDDEN'}]},
    {name: 'GraphqlResponseError', errors: [{message: 'invalid query'}]}]) {
    const {options, calls} = managementFixture(problem);
    await assert.rejects(manage(options));
    assert.deepEqual(calls.merged, []);
  }
});

test('publisher writes only validated pins and uses a fast-forward commit on the built head', async () => {
  const calls = [];
  const github = {rest: {
    pulls: {get: async () => ({data: pr()})},
    repos: {getContent: async args => ({data: {content: Buffer.from(
      args.path.endsWith('/manifest.json') ? '{"version":"0.3.4"}' : '{}',
    ).toString('base64')}})},
    git: {
      getCommit: async () => ({data: {tree: {sha: 'base-tree'}}}),
      createTree: async args => {calls.push(args); return {data: {sha: 'new-tree'}};},
      createCommit: async args => {calls.push(args); return {data: {sha: 'new-commit'}};},
      updateRef: async args => calls.push(args),
    },
    actions: {createWorkflowDispatch: async args => calls.push(args)},
  }};
  await publish({github, context, core: {}}, candidate, checksums);
  assert.equal(calls[0].tree.length, 1);
  assert.equal(calls[0].tree[0].path, 'custom_components/tuya_camera_bridge/bridge_checksums.json');
  assert.deepEqual(calls[1].parents, ['old']);
  assert.equal(calls[2].force, false);
  assert.equal(calls[2].sha, 'new-commit');
  assert.deepEqual(calls.slice(3).map(c => c.workflow_id), ['ci.yml', 'validate.yml']);
});

test('release gate requires all six successful jobs on the exact main commit', async () => {
  for (const problem of ['pending', 'failed', 'missing', 'skipped', 'absent-run', null]) {
    const github = {rest: {actions: {
      listWorkflowRuns: async args => {
        assert.equal(args.head_sha, context.sha);
        assert.equal(args.branch, 'main');
        return {data: {workflow_runs: problem === 'absent-run' ? [] : [{id: args.workflow_id,
          status: problem === 'pending' ? 'in_progress' : 'completed',
          conclusion: problem === 'failed' ? 'failure' : 'success'}]}};
      },
      listJobsForWorkflowRun() {},
    }}, paginate: async (_, args) => {
      const names = args.run_id === 'ci.yml' ? ['secrets', 'python', 'go', 'media'] : ['hacs', 'hassfest'];
      return names.filter(name => !(problem === 'missing' && name === 'media'))
        .map(name => ({name, conclusion: problem === 'skipped' && name === 'go' ? 'skipped' : 'success'}));
    }};
    if (problem) await assert.rejects(releaseGate({github, context}));
    else await releaseGate({github, context});
  }
});
