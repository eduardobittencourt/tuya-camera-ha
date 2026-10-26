const {test} = require('node:test');
const assert = require('node:assert/strict');
const {eligible, goOnly, validateManifest, dispatchChecks, publish, releaseGate} =
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

test('stale build results cannot write to a changed or closed PR', async () => {
  for (const change of [p => p.head.sha = 'new', p => p.state = 'closed']) {
    const current = pr();
    change(current);
    const github = {rest: {pulls: {get: async () => ({data: current})}}};
    await publish({github, context, core: {info() {}}}, candidate, checksums);
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
