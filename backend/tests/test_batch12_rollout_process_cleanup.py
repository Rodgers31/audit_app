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
