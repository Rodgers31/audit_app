'use strict';

const schedules = new Set(['0 2 * * 1-6', '0 3 * * 0']);

module.exports = async function dispatchApprovedNightly(github, context, approved) {
  const { owner, repo } = context.repo;
  const schedule = context.payload.schedule;
  if (owner !== 'Rodgers31' || repo !== 'audit_app' ||
      context.ref !== 'refs/heads/main' || context.eventName !== 'schedule' ||
      !schedules.has(schedule)) {
    throw new Error('Unexpected nightly schedule context');
  }
  if (!/^[0-9a-f]{40}$/.test(approved)) {
    throw new Error('The approved release SHA is missing or malformed');
  }

  const tag = 'ingestion-release-' + approved;
  const { data: release } = await github.rest.git.getRef({ owner, repo, ref: 'tags/' + tag });
  if (release.ref !== 'refs/tags/' + tag ||
      release.object.type !== 'commit' || release.object.sha !== approved) {
    throw new Error('The release tag does not point directly at the approved release');
  }

  const response = await github.request('POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches', {
    owner,
    repo,
    workflow_id: 'seed.yml',
    ref: tag,
    inputs: { approved_schedule: schedule },
    return_run_details: true,
    headers: { 'x-github-api-version': '2022-11-28' },
  });
  const runId = response.data?.workflow_run_id;
  if (response.status !== 200 || !Number.isSafeInteger(runId) || runId <= 0) {
    throw new Error('GitHub did not return a writer run ID. Check Actions before dispatching again.');
  }

  const { data: run } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: runId });
  if (run.id !== runId || run.head_sha !== approved || run.event !== 'workflow_dispatch') {
    throw new Error('GitHub did not confirm the exact approved writer revision for run ' + runId);
  }
  return runId;
};
