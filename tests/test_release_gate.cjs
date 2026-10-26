const {test} = require('node:test');
const assert = require('node:assert/strict');
const {releaseGate} = require('../scripts/release_gate.cjs');
const context = {repo: {owner: 'owner', repo: 'camera'}, sha: 'release-sha'};

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
      const names = args.run_id === 'ci.yml' ? ['secrets', 'python', 'package', 'media'] : ['hacs', 'hassfest'];
      return names.filter(name => !(problem === 'missing' && name === 'media'))
        .map(name => ({name, conclusion: problem === 'skipped' && name === 'package' ? 'skipped' : 'success'}));
    }};
    if (problem) await assert.rejects(releaseGate({github, context}));
    else await releaseGate({github, context});
  }
});
