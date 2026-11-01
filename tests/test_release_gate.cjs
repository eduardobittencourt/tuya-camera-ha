const {test} = require('node:test');
const assert = require('node:assert/strict');
const {releaseGate} = require('../scripts/release_gate.cjs');
const context = {repo: {owner: 'owner', repo: 'camera'}, sha: 'release-sha'};

test('release gate requires all seven successful jobs on the exact main commit', async () => {
  for (const problem of ['pending', 'failed', 'missing', 'skipped', 'absent-run', 'missing-sonar', 'failed-sonar', null]) {
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
      const names = args.run_id === 'ci.yml' ? ['secrets', 'python', 'package', 'media', 'SonarQube scan'] : ['hacs', 'hassfest'];
      return names.filter(name => !(problem === 'missing' && name === 'media') && !(problem === 'missing-sonar' && name === 'SonarQube scan'))
        .map(name => ({name, conclusion: problem === 'skipped' && name === 'package' ? 'skipped' : problem === 'failed-sonar' && name === 'SonarQube scan' ? 'failure' : 'success'}));
    }};
    if (problem) await assert.rejects(releaseGate({github, context}));
    else await releaseGate({github, context});
  }
});
