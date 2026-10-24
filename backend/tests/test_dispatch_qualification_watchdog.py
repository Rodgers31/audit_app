"""Real owned subprocesses exercise the watchdog, including failure cleanup."""
import json
import os
from pathlib import Path
import signal
import sys
from uuid import UUID, uuid4

import pytest

import admin_etl_qualification_watchdog as watchdog
from test_dispatch_qualification import policy_environment

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux-only watchdog: executed in the required Linux cohort')


@pytest.fixture
def child_module(tmp_path, monkeypatch, policy_environment):
    # Change only the module location in the harness. Production has a fixed
    # module and working directory; it accepts no arbitrary executable argument.
    monkeypatch.setattr(watchdog, '__file__', str(tmp_path / 'watchdog.py'))
    monkeypatch.setattr(watchdog, 'memory_usage', lambda: 100 * watchdog.MIB)
    if sys.platform != 'linux':
        # The production entry point is Linux-only. Darwin refuses the Linux
        # RLIMIT_DATA profile; its limits are exercised in the Linux cohort.
        monkeypatch.setattr(watchdog, 'child_limits', lambda: None)
        monkeypatch.setattr(watchdog, 'group_has_descendants', lambda pid: False)
    from admin_etl_qualification import qualification
    receipt = dict(status='completed', generation=str(qualification().generation),
                   command_id=str(uuid4()), readiness_closed=True)
    path = tmp_path / 'admin_etl_qualification_worker.py'
    return path, receipt


def test_real_child_success_is_reaped(child_module):
    path, receipt = child_module
    path.write_text('import json\nprint(' + repr(json.dumps(receipt)) + ')\n')
    result, code = watchdog.supervise()
    assert code == 0 and result['status'] == 'completed'
    assert result['worker'] == receipt and result['reaped'] and result['group_absent']


@pytest.mark.parametrize('prefix', ['"status":"failed",', '"readiness_closed":false,'])
def test_duplicate_receipt_keys_are_not_success(child_module, prefix):
    path, receipt = child_module
    path.write_text('print(' + repr('{' + prefix + json.dumps(receipt)[1:]) + ')\n')
    result, code = watchdog.supervise()
    assert code == 1 and result['reason'] == 'WORKER_RECEIPT_UNVERIFIED'
    assert result['group_absent'] and result['reaped']


@pytest.mark.parametrize('change', [
    {'generation': str(uuid4())}, {'command_id': None}, {'command_id': 'malformed'},
    {'readiness_closed': False}, {'readiness_closed': 1}, {'status': 'failed'},
    {'status': 'no_intent'}, {'extra': 1},
])
def test_bad_child_receipt_never_certifies_success(child_module, change):
    path, receipt = child_module
    path.write_text('print(' + repr(json.dumps(receipt | change)) + ')\n')
    result, code = watchdog.supervise()
    assert code == 1 and result['status'] == 'not_verified'
    assert result['reaped'] and result['group_absent']


@pytest.mark.parametrize('program,reason', [
    ('pass', 'WORKER_RECEIPT_UNVERIFIED'),
    ('print("{invalid")', 'WORKER_RECEIPT_UNVERIFIED'),
    ('print("x"*5000)', 'WORKER_OUTPUT_BOUND'),
    ('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)', 'WHOLE_RUN_OR_MEMORY_BOUND'),
    ('import os,signal,time; os.kill(os.getppid(),signal.SIGTERM); time.sleep(20)', 'INTERRUPTED'),
])
def test_actual_failure_paths_reap_owned_process(child_module, monkeypatch, program, reason):
    path, _ = child_module
    path.write_text(program + '\n')
    monkeypatch.setattr(watchdog, 'WORKER_SECONDS', 5.5)
    result, code = watchdog.supervise()
    assert code == 1 and result['reason'] == reason
    assert result['reaped'] and result['group_absent'] and result['elapsed_seconds'] < 6


def test_shared_memory_ceiling_stops_child(child_module, monkeypatch):
    path, _ = child_module
    path.write_text('import time; time.sleep(20)\n')
    samples = iter([100 * watchdog.MIB, 449 * watchdog.MIB])
    monkeypatch.setattr(watchdog, 'memory_usage', lambda: next(samples))
    result, code = watchdog.supervise()
    assert code == 1 and result['reason'] == 'WHOLE_RUN_OR_MEMORY_BOUND'
    assert result['sampled_cgroup_peak_bytes'] == 449 * watchdog.MIB
    assert result['group_absent'] and result['reaped']


def test_no_memory_reserve_does_not_start_child(child_module, monkeypatch):
    path, _ = child_module
    marker = path.parent / 'must-not-exist'
    path.write_text('from pathlib import Path; Path(' + repr(str(marker)) + ').touch()\n')
    monkeypatch.setattr(watchdog, 'memory_usage', lambda: 321 * watchdog.MIB)
    with pytest.raises(ValueError, match='reserve'):
        watchdog.supervise()
    assert not marker.exists()


def test_retirement_needs_explicit_off_and_matching_receipt(child_module, monkeypatch):
    path, receipt = child_module
    generation = uuid4()
    with pytest.raises(ValueError): watchdog.supervise(generation)
    monkeypatch.setenv('ADMIN_ETL_DISPATCH_ENABLED', 'false')
    path.write_text('print(' + repr(json.dumps(receipt | dict(status='readiness_retired',
                    generation=str(generation), command_id=None))) + ')\n')
    result, code = watchdog.supervise(generation)
    assert code == 0 and result['status'] == 'readiness_retired'
    assert result['group_absent'] and result['reaped']
    with pytest.raises(ValueError): watchdog.supervise(UUID(int=0))


@pytest.mark.parametrize('limit,current', [('max','1'), ('0','0'), ('536870912','-1'),
    ('536870912','0'), ('536870912','536870913'), ('1073741824','100'), ('NaN','100')])
def test_unknown_cgroup_refuses(monkeypatch, limit, current):
    monkeypatch.setattr(Path, 'read_text', lambda path: limit if path.name == 'memory.max' else current)
    with pytest.raises(ValueError): watchdog.memory_usage()


def test_exact_existing_allocation_is_measured(monkeypatch):
    monkeypatch.setattr(Path, 'read_text', lambda path: '536870912' if path.name == 'memory.max' else '123456')
    assert watchdog.memory_usage() == 123456
