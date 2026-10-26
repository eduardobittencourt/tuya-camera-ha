// Require successful CI on the exact commit selected for a draft release.
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


module.exports = {releaseGate};
