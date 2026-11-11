"""Writer job profile and workflow refusal regressions with inert inputs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

import pytest
import yaml

from common import Refusal
import native_jobs as native

JOBS = ('migrate', 'bootstrap', 'seed', 'validate')


@pytest.fixture
def source(tmp_path):
    root = native.runtime.ROOT
    paths = [native.NATIVE_LOCK, *(Path(lock) for _, lock, _ in native.ROLES.values()),
             *(native.PROFILES / name for name in ('local-bundle.json', *(f'{j}.local.json' for j in JOBS)))]
    for path in paths:
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, dest)
    return tmp_path


@pytest.mark.parametrize('job', JOBS)
def test_each_job_has_a_distinct_local_profile(source, job):
    bundle, profile = native.load_job(job, source)
    assert bundle['scope'] == 'LOCAL_QUALIFICATION_ONLY'
    assert bundle['distribution'] == 'RETAINED_LOCAL_DOCKER_ARCHIVE'
    assert bundle['runtimes']['production']['packages'] == 86
    assert bundle['runtimes']['qualification']['packages'] == 95
    assert all(profile != native.load_job(other, source)[1] for other in JOBS if job != other)


@pytest.mark.parametrize('kind,reason', [
    ('absent', 'symlink/absent'),
    ('symlink', 'symlink/absent'),
    ('hardlink', 'hardlink'),
    ('swapped', 'profile/job mismatch'),
    ('relabelled', 'local native job profile required'),
])
def test_profile_refusals(source, kind, reason):
    profiles = source / native.PROFILES
    file = profiles / 'migrate.local.json'
    if kind == 'relabelled':
        original = json.loads(file.read_text())
        original['scope'] = 'APPROVED_HOSTED'
        file.write_text(json.dumps(original))
    else:
        file.unlink()
        other = profiles / 'seed.local.json'
        if kind == 'symlink':
            file.symlink_to(other)
        elif kind == 'hardlink':
            file.hardlink_to(other)
        elif kind == 'swapped':
            shutil.copyfile(other, file)
    with pytest.raises(Refusal, match=reason):
        native.load_job('migrate', source)


def edit_bundle(source, change, rebind=True):
    profiles = source / native.PROFILES
    bundle = profiles / 'local-bundle.json'
    data = json.loads(bundle.read_text())
    change(data)
    raw = json.dumps(data).encode()
    bundle.write_bytes(raw)
    if rebind:
        profile = profiles / 'migrate.local.json'
        data = json.loads(profile.read_text())
        data['bundle_sha256'] = hashlib.sha256(raw).hexdigest()
        profile.write_text(json.dumps(data))


@pytest.mark.parametrize('kind,reason', [
    ('digest', 'native bundle digest mismatch'),
    ('distribution', 'retained local native bundle required'),
    ('mutable_tag', 'exact OCI digest required'),
    ('fallback_platform', 'native image platform differs'),
    ('qualification_for_production', 'native runtime role differs'),
    ('qualification_lock_for_production', 'Python lock bytes differ'),
])
def test_bundle_mismatch(source, kind, reason):
    def change(value):
        image = value['image']
        roles = value['runtimes']
        if kind == 'distribution':
            value['distribution'] = 'APPROVED_HOSTED'
        elif kind == 'mutable_tag':
            image['manifest'] = 'auditgava/runtime:latest'
        elif kind == 'fallback_platform':
            image['platform'] = 'linux/arm64'
        elif kind == 'qualification_for_production':
            roles['production'] = roles['qualification']
        elif kind == 'qualification_lock_for_production':
            roles['production']['lock_sha256'] = roles['qualification']['lock_sha256']
        else:
            value['scope'] = 'APPROVED_HOSTED'
    edit_bundle(source, change, rebind=kind != 'digest')
    with pytest.raises(Refusal, match=reason):
        native.load_job('migrate', source)


def test_cpu_requires_each_processor_and_unmodified_flags(source):
    cpu = native.load_job('migrate', source)[0]['cpu']
    exact = '\n'.join(f'{key}\t: {value}' for key, value in cpu.items())
    native.verify_cpu(cpu, exact + '\n\n' + exact)
    altered = exact.replace(' avx2 ', ' ')
    assert altered != exact
    with pytest.raises(Refusal, match='unqualified CPU'):
        native.verify_cpu(cpu, exact + '\n\n' + altered)


@pytest.mark.parametrize('job', JOBS)
@pytest.mark.parametrize('profile_kind', ('valid', 'missing', 'linked_parent'))
def test_actual_hosted_workflow_refuses_before_db(source, job, profile_kind):
    root = native.runtime.ROOT
    workflow = yaml.safe_load((root / '.github/workflows/seed.yml').read_text())
    writer = workflow['jobs'][job]
    steps = writer['steps']
    index, step = next((i, step) for i, step in enumerate(steps)
                       if step.get('name') == 'Require hosted native writer admission')
    scopes = (workflow, writer, *steps[:index + 1])
    assert not any('secrets.' in str(value) for scope in scopes for value in scope.get('env', {}).values())
    assert all(s.get('with', {}).get('persist-credentials') is False
               for s in steps[:index] if s.get('uses', '').startswith('actions/checkout@'))
    assert not any('setup-python' in s.get('uses', '') or 'apt-get' in s.get('run', '')
                   or 'runtime.py acquire' in s.get('run', '') for s in steps)
    assert '--job ' + job in step['run']
    helpers = Path('tools/nightly_acceptance_20261105')
    for module in ('native_jobs', 'common', 'native_corpus', 'native_environment', 'runtime'):
        path = helpers / f'{module}.py'
        shutil.copyfile(root / path, source / path)
    native_dir = source / native.PROFILES
    if profile_kind == 'missing':
        (native_dir / f'{job}.local.json').unlink()
    elif profile_kind == 'linked_parent':
        elsewhere = source / 'elsewhere'
        native_dir.rename(elsewhere)
        native_dir.symlink_to(elsewhere, target_is_directory=True)
    output = source / 'path'
    output.touch()
    env = {'GITHUB_JOB': job, 'DATABASE_URL': 'inert', 'PATH': '/usr/bin:/bin',
           'GITHUB_PATH': str(output), 'RUNNER_TEMP': str(source / 'scratch'),
           'MARKER': os.fspath(source / 'would-contact-database')}
    # The pinned local Debian image's interpreter is installed under /usr/local.
    # The separate Actions runner uses the system Python at /usr/bin/python3.
    command = step['run']
    if not Path('/usr/bin/python3').is_file():
        command = command.replace('/usr/bin/python3', sys.executable, 1)
    result = subprocess.run(['/bin/bash', '-e', '-c', command + '\nprintf bad > "$MARKER"'],
                            cwd=source, env=env, text=True, capture_output=True, timeout=10)
    reason = 'hosted native writer held' if profile_kind == 'valid' else 'original evidence symlink/absent'
    assert result.returncode == 1 and reason in result.stderr, result
    assert not Path(env['MARKER']).exists()
    assert output.read_text() == '' and not Path(env['RUNNER_TEMP']).exists()
    if job == 'seed':
        for step_id in ('pdf_cache_state', 'save_pdfs'):
            cache = next(s for s in steps if s.get('id') == step_id)
            assert "steps.dependencies.outcome == 'success'" in cache['if']


def test_hosted_preflight_refuses_wrong_runner_context(monkeypatch):
    monkeypatch.setenv('GITHUB_JOB', 'seed')
    with pytest.raises(Refusal, match='runner/job mismatch'):
        native.hosted_preflight('migrate')


@pytest.mark.parametrize('stdout', [
    'a756b20a0001 (head)\nabcdef123456 (head)\n',
    'unexpected a756b20a0001 (head) in status\n',
])
def test_migrate_probe_requires_the_sole_admitted_head(stdout):
    native.verify_probe_output('migrate', 'a756b20a0001 (head)\n', 'a756b20a0001 (head)')
    with pytest.raises(Refusal, match='offline job probe output differs'):
        native.verify_probe_output('migrate', stdout, 'a756b20a0001 (head)')


def test_nested_layer_refuses_as_invalid_digest(source):
    edit_bundle(source, lambda bundle: bundle['image']['layers'].append({'digest': 'sha256:' + '0' * 64}))
    with pytest.raises(Refusal, match='exact OCI digest required'):
        native.load_job('migrate', source)
