"""Dependency installation must keep its reviewed runtime and avoid a hosted pip cache."""
from pathlib import Path

import pytest
import yaml


def steps(job):
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / '.github/workflows/seed.yml').read_text())
    return workflow['jobs'][job]['steps']


def test_source_plan_uses_the_reviewed_runtime_without_a_hosted_pip_cache():
    plan = steps('source_plan')
    setup, = [step for step in plan if step.get('uses', '').startswith('actions/setup-python@')]
    assert setup['with']['python-version'] == '3.12.16'
    assert not setup['with'].get('cache')
    install, = [step['run'] for step in plan if step.get('name') == 'Install reviewed ingestion runtime']
    assert all(f'runtime.py {action}' in install for action in ('acquire', 'wheels', 'install', 'verify'))


@pytest.mark.parametrize('job', ['migrate', 'bootstrap', 'seed', 'validate'])
def test_writer_has_no_host_runtime_install_or_fallback(job):
    writer = steps(job)
    assert not any('setup-python' in step.get('uses', '') or 'runtime.py acquire' in step.get('run', '')
                   or 'apt-get' in step.get('run', '') for step in writer)
    gate, = [step for step in writer if step.get('name') == 'Require hosted native writer admission']
    assert f'hosted-preflight --job {job}' in gate['run']
