"""The owned Popen handle must reap its exited root before group checks."""
import json
import subprocess

from test_batch12_rollout_worker import process, wait_for


def test_exited_owned_root_is_reaped_before_command_identity_checks(tmp_path):
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
    with process(tmp_path, env, 'this') as (child, path):
        wait_for(lambda: subprocess.check_output(
            ['ps', '-p', str(child.pid), '-o', 'stat='], text=True).strip(),
            lambda state: state.startswith('Z'))
    assert child.returncode == 0
    receipt = path.with_suffix('.receipt.json')
    assert receipt.is_file()
    value = json.loads(receipt.read_text())
    assert value['remaining_group_members'] == [] and value['pid'] == child.pid


def test_owned_root_exit_between_poll_and_census_is_reaped(tmp_path, monkeypatch):
    import test_batch12_rollout_worker as worker
    release = tmp_path / 'release-owned-child'
    original_census = worker.group_members
    calls = []
    def racing_census(pid):
        calls.append(pid)
        if len(calls) == 1:
            # The child cannot exit until the first cleanup poll has returned.
            release.write_text('release')
            wait_for(lambda: subprocess.check_output(
                ['ps', '-p', str(pid), '-o', 'stat='], text=True).strip(),
                lambda state: state.startswith('Z'))
        return original_census(pid)
    monkeypatch.setattr(worker, 'group_members', racing_census)
    statement = f"from pathlib import Path\nimport time\nwhile not Path({str(release)!r}).exists():\n    time.sleep(0.01)"
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
    with process(tmp_path, env, 'timeit', '-n', '1', '-r', '1', statement) as (child, path):
        assert child.poll() is None and not release.exists()
    assert child.returncode == 0
    assert json.loads(path.with_suffix('.receipt.json').read_text())['remaining_group_members'] == []
