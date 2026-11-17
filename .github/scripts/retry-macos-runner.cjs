'use strict';

// A hosted Mac can be cancelled before GitHub assigns a runner. Retry only
// that infrastructure case; never turn a test failure into a passing check.
module.exports = async function retryMacRunner({ github, context, core }) {
  const { owner, repo } = context.repo;
  const runId = context.payload.workflow_run.id;
  const branch = context.payload.repository.default_branch;
  const report = async (message) => {
    core.info(message);
    await core.summary.addHeading('Mac runner recovery').addRaw(`${message}\n`).write();
  };
  const { data: run } = await github.rest.actions.getWorkflowRun({
    owner, repo, run_id: runId,
  });

  if (run.name !== 'macOS Vision Studio' ||
      run.path !== '.github/workflows/macos-vision.yml' ||
      run.head_repository?.full_name !== `${owner}/${repo}` ||
      run.head_branch !== branch ||
      !['push', 'workflow_dispatch'].includes(run.event)) {
    return report('Skipped: not a same-repository default-branch Mac run.');
  }
  // Cancelling an entire workflow is an operator action: respect it. The
  // hosting incident presents as a failed run with a cancelled, unstarted job.
  if (run.status !== 'completed' || run.conclusion !== 'failure') {
    return report('Skipped: run is active, successful, or explicitly cancelled.');
  }
  if (!Number.isInteger(run.run_attempt) || run.run_attempt >= 3) {
    return report('Retry limit reached (three total attempts). Inspect the original run and rerun manually if appropriate.');
  }
  const { data: head } = await github.rest.repos.getBranch({ owner, repo, branch });
  if (head.commit.sha !== run.head_sha) {
    return report('Skipped: a newer commit supersedes this run.');
  }
  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
    owner, repo, run_id: runId, filter: 'latest', per_page: 100,
  });
  const eligible = jobs.find((job) =>
    /^native-mac \(macos-15(?:-intel)?\)$/.test(job.name) &&
    job.status === 'completed' && job.conclusion === 'cancelled' &&
    job.runner_id === 0 && Array.isArray(job.steps) && job.steps.length === 0);
  if (!eligible) {
    return report('Skipped: no cancelled Mac job with zero steps and no assigned runner. Test failures require a code fix.');
  }
  // One request per completion, bounded by run_attempt even for manual retries.
  await github.request('POST /repos/{owner}/{repo}/actions/jobs/{job_id}/rerun', {
    owner, repo, job_id: eligible.id,
  });
  return report(`Requested retry of job ${eligible.id} in run ${runId} (attempt ${run.run_attempt + 1}/3). Original test and benchmark checks remain authoritative.`);
};
