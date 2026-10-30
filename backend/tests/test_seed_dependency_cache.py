"""Dependency installation must not wait on an unavailable hosted pip cache."""
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize('job', ['source_plan', 'migrate', 'bootstrap', 'seed', 'validate'])
def test_seed_python_setup_uses_direct_dependency_installation(job):
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / '.github/workflows/seed.yml').read_text())
    steps = workflow['jobs'][job]['steps']
    setup = [step for step in steps if step.get('uses') == 'actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1']
    assert len(setup) == 1
    assert setup[0]['with']['python-version'] == '3.12'
    assert not setup[0]['with'].get('cache')
    assert any('pip install' in step.get('run', '') and '-r backend/requirements.txt' in step['run'] for step in steps)
