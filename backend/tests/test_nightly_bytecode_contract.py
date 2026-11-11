"""Exercise actual nightly/isolated Python flags on owned importable modules.

DB/DNS transports below are inert; their real child argv and interpreter flags
execute without reaching a provider or database. No installed package is edited.
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
QUALIFIERS = [shlex.split(line.strip()) for job in WORKFLOW['jobs'].values()
              for step in job.get('steps', []) for line in step.get('run', '').splitlines()
              if line.strip().startswith('python -I ') and 'scripts/verification/github_database_qualify.py' in line]


def import_probe(tmp_path, flags, *, env=None, run=subprocess.run):
    module = tmp_path / 'owned_bytecode_probe.py'
    module.write_text('VALUE = 19\n')
    program = ('import sys,json; sys.path.insert(0,' + repr(str(tmp_path)) + '); '
               'import owned_bytecode_probe; '
               'print(json.dumps({"value":owned_bytecode_probe.VALUE,"isolated":sys.flags.isolated,'
               '"no_bytecode":sys.dont_write_bytecode}))')
    result = run([sys.executable, *flags, '-c', program], env=env,
                 capture_output=True, text=True, timeout=10, check=True)
    observed = json.loads(result.stdout)
    assert observed['value'] == 19
    assert observed['no_bytecode'] is True
    assert not list(tmp_path.rglob('*.pyc'))
    return observed


def test_nightly_ordinary_children_preserve_no_bytecode_policy(tmp_path):
    assert len(QUALIFIERS) == 8
    env = {'PATH': os.defpath}
    value = WORKFLOW.get('env', {}).get('PYTHONDONTWRITEBYTECODE')
    if value is not None:
        env['PYTHONDONTWRITEBYTECODE'] = str(value)
    import_probe(tmp_path, [], env=env)


@pytest.mark.parametrize('command', QUALIFIERS)
def test_every_actual_isolated_workflow_qualifier_refuses_bytecode(tmp_path, command):
    script = command.index('scripts/verification/github_database_qualify.py')
    observed = import_probe(tmp_path, command[1:script], env={'PYTHONDONTWRITEBYTECODE': '1'})
    assert observed['isolated'] == 1


def test_database_qualifier_nested_child_preserves_isolation_without_bytecode(tmp_path, monkeypatch):
    path = ROOT / 'scripts/verification/github_database_qualify.py'
    spec = importlib.util.spec_from_file_location('owned_database_qualifier_bytecode', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual_run = subprocess.run
    seen = []

    def child(command, **kwargs):
        seen.append(command)
        script = command.index(str(path.resolve()))
        probe = tmp_path / str(len(seen)); probe.mkdir()
        observed = import_probe(probe, command[1:script], env=kwargs['env'], run=actual_run)
        assert observed['isolated'] == 1
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(revision=module.REVISION,
            database_bytes=1, catalog_reads=4, read_only=True, tls_verified=True)))

    monkeypatch.setattr(module.subprocess, 'run', child)
    assert module.main(['--all']) == 0
    assert len(seen) == len(module.SECRETS)


def test_issuer_dns_child_preserves_empty_environment_and_no_bytecode(tmp_path, monkeypatch):
    from seeding import issuer_transport
    actual_run = subprocess.run
    seen = []

    def dns(command, **kwargs):
        seen.append(command)
        assert kwargs['env'] == {}
        observed = import_probe(tmp_path, command[1:command.index('-c')], env={}, run=actual_run)
        assert observed['isolated'] == 1
        assert 0 < kwargs['timeout'] <= 2
        return SimpleNamespace(stdout='["8.8.8.8"]')

    monkeypatch.setattr(issuer_transport.subprocess, 'run', dns)
    assert issuer_transport._public_addresses('letsencrypt.org', time.monotonic() + 5) == ['8.8.8.8']
    assert len(seen) == 1
