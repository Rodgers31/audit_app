"""Exercise the actual workflow write gate, planner and GitHub API calls offline."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from seeding.source_plan import DAILY, WEEKLY, build_plan, environment_plan

ROOT = Path(__file__).resolve().parents[2]
APPROVED = 'a' * 40
TAG = f'refs/tags/ingestion-release-{APPROVED}'
MAIN = 'refs/heads/main'


@pytest.mark.parametrize(('ref', 'event', 'actor', 'cron', 'routing', 'enabled', 'sha', 'expected'), [
    (TAG, 'workflow_dispatch', 'github-actions[bot]', DAILY, 'true', 'true', APPROVED, True),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', WEEKLY, 'true', 'true', APPROVED, True),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', DAILY, 'true', 'true', 'b' * 40, False),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', DAILY, 'true', 'false', APPROVED, False),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', DAILY, 'false', 'true', APPROVED, False),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', 'invalid', 'true', 'true', APPROVED, False),
    (TAG, 'workflow_dispatch', 'github-actions[bot]', '', 'true', 'true', APPROVED, False),
    (TAG, 'workflow_dispatch', 'owner', DAILY, 'true', 'true', APPROVED, False),
    (MAIN, 'workflow_dispatch', 'owner', WEEKLY, 'true', 'true', APPROVED, False),
    (MAIN, 'workflow_dispatch', 'owner', '', 'true', 'false', APPROVED, True),
    (MAIN, 'schedule', 'owner', '', 'false', 'true', APPROVED, True),
    (MAIN, 'schedule', 'owner', '', 'false', 'true', 'b' * 40, False),
    (MAIN, 'schedule', 'owner', '', 'true', 'true', APPROVED, False),
])
def test_write_gate(ref, event, actor, cron, routing, enabled, sha, expected):
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    command = workflow['jobs']['migrate']['steps'][0]['run']
    env = {
        'REPOSITORY': 'Rodgers31/audit_app', 'APPROVED_SHA': APPROVED,
        'DISPATCH_REF': ref, 'DISPATCH_SHA': sha, 'DISPATCH_EVENT': event,
        'DISPATCH_ACTOR': actor, 'NIGHTLY_ENABLED': enabled,
        'APPROVED_SCHEDULE_ROUTING': routing, 'SEED_PLAN_ROUTED_CRON': cron,
        'ROUTED_VALIDATION': 'true',
    }
    result = subprocess.run(['bash', '-e', '-c', command], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is expected, result.stdout + result.stderr


@pytest.mark.parametrize('cron', [DAILY, WEEKLY])
def test_routed_plan_preserves_daily_and_weekly_opt_in_semantics(monkeypatch, cron):
    for key in ('SEED_PLAN_DRY_RUN', 'SEED_PLAN_BOOTSTRAP', 'SEED_PLAN_AUDITS_REVIEW',
                'SEED_PLAN_AUDITS_SOURCE_ACCEPTANCE', 'SEED_PLAN_REACQUIRE_PENDING_BILLS_PDF',
                'SEED_CRA_INGESTION_ENABLED', 'SEED_OPENDATA_INGESTION_ENABLED',
                'SEED_KNBS_RELEASE_DISCOVERY_ENABLED', 'SEED_PLAN_SCHEDULE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('SEED_PLAN_EVENT', 'workflow_dispatch')
    monkeypatch.setenv('SEED_PLAN_ROUTED_CRON', cron)
    monkeypatch.setenv('SEED_PLAN_DOMAIN', 'all')
    monkeypatch.setenv('SEED_COUNTY_BORROWING_INGESTION_ENABLED', 'true')
    expected = build_plan(event='schedule', schedule=cron, domain='', dry_run='false',
                          cra='false', opendata='false', discovery='false', county_borrowing='true')
    assert environment_plan() == expected
    monkeypatch.setenv('SEED_PLAN_DOMAIN', 'audits')
    with pytest.raises(ValueError, match='Unsupported scheduled source plan'):
        environment_plan()


def test_scheduler_dispatches_the_verified_tag_even_when_main_has_advanced():
    script = ROOT / '.github/scripts/dispatch-approved-nightly.cjs'
    result = subprocess.run(['node', '-e', """
const assert = require('node:assert/strict');
const dispatch = require(process.argv[1]);
const pin = 'a'.repeat(40);
const tag = 'ingestion-release-' + pin;
let posts = 0;
let reads = 0;
const context = { eventName: 'schedule', ref: 'refs/heads/main',
  sha: 'b'.repeat(40), runId: 123, repo: { owner: 'Rodgers31', repo: 'audit_app' },
  payload: { schedule: '0 3 * * 0' } };
const child = { id: 456, event: 'workflow_dispatch', head_sha: pin };
const github = { rest: {
  git: { getRef: async ({ref}) => {
    assert.equal(ref, 'tags/' + tag);
    return { data: {ref: 'refs/tags/' + tag, object: {type: 'commit', sha: pin}} };
  }},
  actions: { getWorkflowRun: async ({run_id}) => {
    assert.equal(run_id, child.id);
    reads++;
    return { data: child };
  }},
}, request: async (method, params) => {
    posts++;
    assert.equal(method, 'POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches');
    assert.equal(params.workflow_id, 'seed.yml');
    assert.equal(params.ref, tag);
    assert.deepEqual(params.inputs, {approved_schedule: '0 3 * * 0'});
    assert.equal(params.return_run_details, true);
    return { status: 200, data: {workflow_run_id: child.id} };
}};
(async () => {
  assert.equal(await dispatch(github, context, pin), child.id);
  assert.equal(posts, 1);
  assert.equal(reads, 1);
  github.rest.git.getRef = async () => ({data: {
    ref: 'refs/tags/' + tag, object: {type: 'commit', sha: context.sha} }});
  await assert.rejects(dispatch(github, context, pin), /release tag/);
  await assert.rejects(dispatch(github, context, 'wrong'), /approved release/);
  await assert.rejects(dispatch(github, {...context, eventName: 'workflow_dispatch'}, pin), /schedule context/);
  assert.equal(posts, 1);
  console.log(JSON.stringify({posts, reads}));
})().catch(error => { console.error(error); process.exitCode = 1; });
""", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'posts': 1, 'reads': 1}
