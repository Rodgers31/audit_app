"""Execute the seed workflow's plan and runner against inert CLI arguments."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def workflow():
    data = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    return data, data.get('on', data.get(True))


def test_sunday_has_one_all_domain_schedule():
    _, trigger = workflow()
    daily = next(c['cron'] for c in trigger['schedule'] if c['cron'].split()[1] == '2')
    assert daily.split()[4] == '1-6', 'Sunday currently requests duplicate all-domain work'


def test_workflow_selects_bounded_native_handlers():
    spec = importlib.util.find_spec('seeding.source_plan')
    assert spec is not None, 'No executable whitelisted source plan exists'
    from seeding.source_plan import build_plan
    p = build_plan(event='schedule', schedule='0 3 * * 0', domain='', dry_run='false',
                   cra='true', opendata='true', discovery='false')
    assert {'cra', 'opendata'} <= set(p.domains)
    assert p.bootstrap is True and p.argv[-1] == '--no-dry-run'


def test_optins_are_forwarded_to_runtime():
    data, _ = workflow()
    for key in ('SEED_CRA_INGESTION_ENABLED', 'SEED_OPENDATA_INGESTION_ENABLED', 'SEED_KNBS_RELEASE_DISCOVERY_ENABLED'):
        assert key in data['env'], f'{key} not forwarded by seed.yml'


def test_untrusted_dispatch_is_not_executable_shell(tmp_path):
    data, _ = workflow()
    seed = data['jobs']['seed']
    step = next(s for s in seed['steps'] if s.get('name') in ('Seed specific domain', 'Seed planned domains'))
    # Replay exactly the legacy interpolation vulnerability with an inert command.
    marker = tmp_path / 'unexpected-shell'
    script = step['run'].replace('${{ github.event.inputs.domain }}', f'population; touch {marker}; #')
    script = script.replace("${{ github.event.inputs.dry_run == 'true' && '--dry-run' || '' }}", '')
    script = script.replace('cd backend', f'cd {tmp_path}')
    env = {'PATH': str(Path(sys.executable).parent) + ':/opt/homebrew/bin:/usr/bin:/bin',
           'PYTHONPATH': str(ROOT / 'backend'), 'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'SEED_PLAN_EVENT': 'workflow_dispatch', 'SEED_PLAN_DOMAIN': f'population; touch {marker}; #',
           'SEED_CRA_INGESTION_ENABLED':'false', 'SEED_OPENDATA_INGESTION_ENABLED':'false',
           'SEED_KNBS_RELEASE_DISCOVERY_ENABLED':'false'}
    result = subprocess.run(['/bin/bash', '-e', '-c', script], env=env, capture_output=True, text=True)
    assert result.returncode == 2 and 'Source plan refused: Unknown source plan domain' in result.stderr, result
    assert not marker.exists(), 'Dispatch input executed shell code'


@pytest.mark.parametrize('flag', ['true', 'false', '', 'TRUE', '1', 'yes', ' false '])
def test_plan_validates_flags_without_cli_execution(flag):
    from seeding.source_plan import build_plan
    kwargs = dict(event='workflow_dispatch', schedule='', domain='', dry_run='false', cra=flag, opendata='false', discovery='false')
    if flag in ('true', 'false'):
        assert ('cra' in build_plan(**kwargs).domains) == (flag == 'true')
    else:
        with pytest.raises(ValueError): build_plan(**kwargs)


@pytest.mark.parametrize('domain', ['unknown', '--all', 'cra;touch marker', 'population\nanything', None, True])
def test_direct_plan_refuses_malformed_domain(domain):
    from seeding.source_plan import build_plan
    with pytest.raises(ValueError):
        build_plan(event='workflow_dispatch', schedule='', domain=domain, dry_run='false', cra='false', opendata='false', discovery='false')


def test_daily_retains_legacy_scope_weekly_adds_only_optins():
    from seeding.source_plan import build_plan, DAILY, WEEKLY, LEGACY_DOMAINS
    from seeding.registries import REGISTRY, load_builtin_domains
    p = build_plan(event='schedule', schedule=DAILY, domain='', dry_run='false', cra='true', opendata='true', discovery='true')
    assert p.domains == LEGACY_DOMAINS and p.bootstrap is False and len(p.domains) == 15
    load_builtin_domains()
    # Actual native handler resolution, not source string presence.
    from seeding.domains import cra, opendata
    assert REGISTRY.get('cra') is cra.run and REGISTRY.get('opendata') is opendata.run
    p = build_plan(event='workflow_dispatch', schedule='', domain='opendata', dry_run='true', cra='false', opendata='true', discovery='true')
    assert p.domains == ('opendata',) and p.argv[-3:] == ['--domain', 'opendata', '--dry-run']


def test_dispatch_executes_argument_vector(monkeypatch):
    from seeding import source_plan as p
    seen = []
    env = {'SEED_PLAN_EVENT':'workflow_dispatch', 'SEED_PLAN_DOMAIN':'opendata', 'SEED_PLAN_DRY_RUN':'true',
           'SEED_OPENDATA_INGESTION_ENABLED':'true'}
    for k, v in env.items(): monkeypatch.setenv(k,v)
    monkeypatch.setattr(sys, 'argv', ['source_plan', '--execute'])
    def run(argv, **kwargs):
        seen.append((argv, kwargs))
        return type('Result', (), {'returncode':17})()
    monkeypatch.setattr(p.subprocess, 'run', run)
    assert p.main() == 17
    assert seen[0][0][-3:] == ['--domain','opendata','--dry-run'] and seen[0][1] == {'check':False}
