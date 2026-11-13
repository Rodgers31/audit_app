"""Run the actual workflow shell step in a clean runner directory."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('fail', ['', 'acquire', 'wheels', 'install', 'verify'])
def test_source_plan_provisions_a_private_runtime_before_publishing_path(tmp_path, fail):
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    script = next(step['run'] for step in workflow['jobs']['source_plan']['steps']
                  if step.get('name') == 'Install reviewed ingestion runtime')
    runner = tmp_path / 'runner temp'
    runner.mkdir()
    commands = tmp_path / 'commands'
    commands.mkdir()
    python = commands / 'python'
    # Stub only the wheel operations. Retain the real clean-directory precondition,
    # offline verification order, and shell exit behavior used by GitHub.
    python.write_text(f'#!{sys.executable}\n' + """
import os, pathlib, stat, sys
action = sys.argv[3]
with open(os.environ['CALLS'], 'a') as log:
    print(action, file=log)
if action == os.environ['FAIL']:
    sys.exit(42)
if action == 'acquire':
    wheels = pathlib.Path(sys.argv[5])
    wheels.mkdir(mode=0o700)  # The real acquire() requires an existing parent.
    if stat.S_IMODE(wheels.parent.stat().st_mode) != 0o700:
        sys.exit('scratch parent is not private')
elif action == 'install':
    destination = pathlib.Path(sys.argv[7]) / 'bin'
    destination.mkdir(parents=True)
    (destination / 'python').symlink_to(pathlib.Path(__file__).resolve())
""")
    python.chmod(0o700)
    path_file, calls = tmp_path / 'path', tmp_path / 'calls'
    result = subprocess.run(
        ['/bin/bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', script],
        cwd=ROOT, env={'PATH': f'{commands}{os.pathsep}{os.defpath}', 'GITHUB_JOB': 'source_plan',
                       'RUNNER_TEMP': str(runner), 'GITHUB_PATH': str(path_file),
                       'CALLS': str(calls), 'FAIL': fail},
        capture_output=True, text=True, timeout=10,
    )
    order = ['acquire', 'wheels', 'install', 'verify']
    if fail:
        assert result.returncode == 42, result.stderr
        assert not path_file.exists()
        assert calls.read_text().splitlines() == order[:order.index(fail) + 1]
    else:
        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines() == order
        binary_dir = Path(path_file.read_text().rstrip('\n'))
        assert binary_dir.is_relative_to(runner)
        assert binary_dir.name == 'bin' and (binary_dir / 'python').is_file()


def test_source_plan_refuses_symlink_runner_temp_before_creating_scratch(tmp_path):
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    script = next(step['run'] for step in workflow['jobs']['source_plan']['steps']
                  if step.get('name') == 'Install reviewed ingestion runtime')
    other = tmp_path / 'other'
    other.mkdir()
    runner = tmp_path / 'runner'
    runner.symlink_to(other, target_is_directory=True)
    path_file = tmp_path / 'path'
    result = subprocess.run(
        ['/bin/bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', script],
        cwd=ROOT, env={'PATH': os.defpath, 'RUNNER_TEMP': str(runner), 'GITHUB_PATH': str(path_file)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert not list(other.iterdir())
    assert not path_file.exists()
