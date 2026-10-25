"""Execute the actual admission shell; refuse unreviewed source before writers."""
import os
import re
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SEED = yaml.load((ROOT/'.github/workflows/seed.yml').read_text(), Loader=yaml.BaseLoader)
MANUAL = yaml.load((ROOT/'.github/workflows/ingestion-preflight.yml').read_text(), Loader=yaml.BaseLoader)
SHA = 'a'*40


def guard(workflow, job, env):
    script = workflow['jobs'][job]['steps'][0]['run']
    return subprocess.run(['bash', '-eu', '-c', script], env={'PATH':os.environ['PATH'], **env},
                          text=True, capture_output=True, timeout=2)


@pytest.mark.parametrize('change', [{}, {'APPROVED_SHA':''}, {'APPROVED_SHA':'g'*40},
    {'APPROVED_SHA':'b'*40}, {'REPOSITORY':'other/repo'}, {'DISPATCH_REF':'refs/heads/other'}])
def test_actual_seed_admission_guard(change):
    env = {'APPROVED_SHA':SHA, 'DISPATCH_SHA':SHA,
           'REPOSITORY':'Rodgers31/audit_app', 'DISPATCH_REF':'refs/heads/main',
           'DISPATCH_EVENT':'workflow_dispatch', 'NIGHTLY_ENABLED':''}
    result = guard(SEED, 'migrate', {**env, **change})
    assert (result.returncode == 0) == (change == {})


@pytest.mark.parametrize('ref', ['refs/heads/main', 'refs/heads/codex/github-database-qualification'])
def test_manual_qualification_accepts_only_reviewed_source(ref):
    env = {'APPROVED_SHA':SHA, 'DISPATCH_SHA':SHA, 'REPOSITORY':'Rodgers31/audit_app',
           'DISPATCH_REF':ref,
           'DEFINITION_REF':'Rodgers31/audit_app/.github/workflows/ingestion-preflight.yml@'+ref}
    assert guard(MANUAL, 'qualify_github_writer', env).returncode == 0
    for change in ({'APPROVED_SHA':''}, {'APPROVED_SHA':'b'*40}, {'DISPATCH_REF':'refs/pull/1/merge'},
                   {'DEFINITION_REF':'other'}, {'REPOSITORY':'other/repo'}):
        assert guard(MANUAL, 'qualify_github_writer', {**env, **change}).returncode != 0


def test_native_writers_depend_on_the_qualified_schema_job():
    jobs = SEED['jobs']
    assert 'migrate' in jobs['seed']['needs']
    assert set(jobs['bootstrap']['needs']) == {'migrate','seed'}
    commands = '\n'.join(step.get('run','') for step in jobs['migrate']['steps'])
    assert 'alembic upgrade' not in commands
    assert 'alembic stamp' not in commands
    assert 'github_database_qualify.py --seed' in commands
    assert "test \"$(alembic heads)\" = 'a756b20a0001 (head)'" in commands
    assert SEED['concurrency'] == {'group':'seed-production-database','cancel-in-progress':'false'}
    assert set(jobs['validate']['needs']) == {'migrate','seed'}
    assert "needs.migrate.result == 'success'" in jobs['validate']['if']
    for name in ('migrate','seed','bootstrap','validate'):
        assert jobs[name]['env']['AUDIT_GITHUB_DATABASE_TLS'] == '1'
        commands = '\n'.join(step.get('run','') for step in jobs[name]['steps'])
        assert commands.index('--prepare-writer-tls') < commands.index('--seed')
    summary = next(step for step in jobs['seed']['steps'] if step.get('name') == 'Check ingestion job results')
    assert "steps.database.outcome == 'success'" in summary['if']


def test_manual_inspection_has_no_secrets_before_the_fixed_driver_install():
    steps = MANUAL['jobs']['qualify_github_writer']['steps']
    assert all('secrets.' not in str(step) for step in steps[:-1])
    assert '--require-hashes --only-binary=:all:' in steps[-2]['run']
    assert steps[-1]['run'] == 'python -I scripts/verification/github_database_qualify.py --all'
    assert not any('upload-artifact' in str(s) or 'actions/cache' in str(s) for s in steps)


def test_repository_admission_variable_uses_a_github_supported_name():
    expression = MANUAL['jobs']['qualify_github_writer']['steps'][0]['env']['APPROVED_SHA']
    name = re.fullmatch(r'\$\{\{ vars\.([A-Z0-9_]+) \}\}', expression).group(1)
    # GitHub's repository-variable API rejects these reserved namespaces.
    assert not name.startswith(('GITHUB_', 'RUNNER_'))


@pytest.mark.parametrize('event,nightly,accepted', [
    ('workflow_dispatch','',True), ('workflow_dispatch','false',True),
    ('schedule','',False), ('schedule','false',False), ('schedule','0',False),
    ('schedule','TRUE',False), ('schedule','true',True), ('pull_request','true',False)])
def test_manual_canary_does_not_arm_scheduled_writes(event, nightly, accepted):
    env = {'APPROVED_SHA':SHA,'DISPATCH_SHA':SHA,'REPOSITORY':'Rodgers31/audit_app',
           'DISPATCH_REF':'refs/heads/main','DISPATCH_EVENT':event,'NIGHTLY_ENABLED':nightly}
    assert (guard(SEED,'migrate',env).returncode == 0) is accepted
