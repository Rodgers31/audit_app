"""Explicit producer selection; normal nightly scope stays frozen."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from seeding.config import SeedingSettings
from seeding.source_plan import LEGACY_DOMAINS, DAILY, WEEKLY, build_plan, environment_plan


def test_existing_daily_plan_is_observable_and_unchanged():
    plan = build_plan(event='schedule', schedule=DAILY, domain='', dry_run='false',
                      cra='false', opendata='false', discovery='false')
    assert plan.domains == LEGACY_DOMAINS
    assert len(plan.domains) == 15


def test_explicit_opt_in_registers_county_borrowing_producer(monkeypatch):
    env = {k: v for k, v in os.environ.items() if not k.startswith('SEED_')}
    env['SEED_COUNTY_BORROWING_INGESTION_ENABLED'] = 'true'
    result = subprocess.run([sys.executable, '-c',
        "from seeding.registries import REGISTRY,load_builtin_domains; load_builtin_domains(); assert callable(REGISTRY.get('county_borrowing')), 'explicit opt-in has no county borrowing producer'"],
        env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr



def test_settings_expose_default_off_county_borrowing():
    assert SeedingSettings(_env_file=None).model_dump().get('county_borrowing_ingestion_enabled') is False


# Exercise the real checked-in workflow contract, without contacting GitHub.
ROOT = Path(__file__).resolve().parents[2]
FLAG = 'SEED_COUNTY_BORROWING_INGESTION_ENABLED'


def test_workflow_exposes_borrowing_but_forwards_literal_default_off():
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    trigger = workflow.get('on', workflow.get(True))
    assert 'county_borrowing' in trigger['workflow_dispatch']['inputs']['domain']['options']
    assert workflow['env'][FLAG] == "${{ vars.SEED_COUNTY_BORROWING_INGESTION_ENABLED || 'false' }}"
    assert [item['cron'] for item in trigger['schedule']] == [DAILY, WEEKLY]
    assert workflow['concurrency'] == {'group': 'seed-production-database', 'cancel-in-progress': False}


@pytest.mark.parametrize('flag', [None, 'false'])
@pytest.mark.parametrize('schedule', [DAILY, WEEKLY])
def test_real_environment_plan_preserves_ordinary_nightly_scope(monkeypatch, flag, schedule):
    for key in tuple(os.environ):
        if key.startswith('SEED_'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('SEED_PLAN_EVENT', 'schedule')
    monkeypatch.setenv('SEED_PLAN_SCHEDULE', schedule)
    if flag is not None:
        monkeypatch.setenv(FLAG, flag)
    plan = environment_plan()
    assert plan.domains == LEGACY_DOMAINS and len(plan.domains) == 15
    assert plan.bootstrap is (schedule == WEEKLY)
    assert 'county_borrowing' not in plan.argv


@pytest.mark.parametrize('flag', [None, 'false'])
def test_manual_borrowing_requires_explicit_admission_before_execution(monkeypatch, flag):
    for key in tuple(os.environ):
        if key.startswith('SEED_'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('SEED_PLAN_EVENT', 'workflow_dispatch')
    monkeypatch.setenv('SEED_PLAN_DOMAIN', 'county_borrowing')
    monkeypatch.setenv('SEED_PLAN_DRY_RUN', 'true')
    if flag is not None:
        monkeypatch.setenv(FLAG, flag)
    with pytest.raises(ValueError, match='explicit opt-in'):
        environment_plan()


def test_enabled_manual_plan_uses_native_argv_and_weekly_adds_only_borrowing():
    args = dict(domain='', dry_run='false', cra='false', opendata='false', discovery='false',
                county_borrowing='true')
    assert build_plan(event='schedule', schedule=DAILY, **args).domains == LEGACY_DOMAINS
    assert build_plan(event='schedule', schedule=WEEKLY, **args).domains == ('county_borrowing', *LEGACY_DOMAINS)
    args.update(domain='county_borrowing', dry_run='true')
    plan = build_plan(event='workflow_dispatch', schedule='', **args)
    assert plan.argv == [sys.executable, '-m', 'seeding.cli', 'seed', '--domain',
                         'county_borrowing', '--dry-run']


@pytest.mark.parametrize('launcher', ['backend_cwd', 'owned_backend', 'owned_legacy'])
def test_new_producer_helper_and_real_cli_import_under_supported_launchers(launcher):
    # Fresh interpreters expose masked/stub imports that a warm pytest process
    # can hide. The owned cases use the repository's existing binding mechanism.
    script = '''
from pathlib import Path
import importlib.util, json, sys
root = Path(sys.argv[1])
mode = sys.argv[2]
if mode.startswith('owned_'):
    spec = importlib.util.spec_from_file_location('launcher', root / '.github/scripts/run_backend_tests.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    sys.path.insert(0, str(root / 'backend'))
    launcher.bind_package('seeding', root / 'backend/seeding')
    launcher.bind_package('etl', root / ('etl' if mode == 'owned_legacy' else 'backend/etl'))
from seeding import county_borrowing_contract
from seeding import cli, registries
from services.county_borrowing_coverage import county_borrowing_coverage
registries.load_builtin_domains()
from seeding.domains import county_borrowing
assert registries.REGISTRY.get('county_borrowing') is county_borrowing.run
assert callable(county_borrowing_coverage)
assert cli.__file__.startswith(str(root / 'backend/seeding'))
assert county_borrowing_contract.__file__.startswith(str(root / 'backend/seeding'))
print(json.dumps({'launcher': mode, 'producer': county_borrowing.__file__, 'helper': county_borrowing_coverage.__module__}))
'''
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('SEED_') and key not in ('PYTHONPATH', 'GITHUB_OUTPUT')}
    env.update(PYTHON_DOTENV_DISABLED='1', AUTO_SEEDER_ENABLED='false')
    env[FLAG] = 'true'
    result = subprocess.run([sys.executable, '-c', script, str(ROOT), launcher],
                            cwd=ROOT / 'backend' if launcher == 'backend_cwd' else ROOT,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['launcher'] == launcher


@pytest.mark.parametrize('approved,dispatch,event,nightly,allowed', [
    ('a'*40,'a'*40,'workflow_dispatch','false',True),
    ('','a'*40,'workflow_dispatch','false',False),
    ('b'*40,'a'*40,'workflow_dispatch','false',False),
    ('a'*40,'a'*40,'schedule','false',False),
    ('a'*40,'a'*40,'schedule','true',True),
])
def test_existing_write_revision_gate_remains_required(approved,dispatch,event,nightly,allowed):
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    gate = next(step for step in workflow['jobs']['migrate']['steps']
                if step.get('name') == 'Refuse writes outside the explicitly accepted source revision')
    # The exact local shell gate has no network or side effect. It checks only
    # inert synthetic revisions, never a production admission variable.
    env = {'PATH':'/usr/bin:/bin','REPOSITORY':'Rodgers31/audit_app','DISPATCH_REF':'refs/heads/main',
           'APPROVED_SHA':approved,'DISPATCH_SHA':dispatch,'DISPATCH_EVENT':event,'NIGHTLY_ENABLED':nightly}
    result = subprocess.run(['/bin/bash','-c',gate['run']],env=env,capture_output=True,text=True)
    assert (result.returncode == 0) is allowed
