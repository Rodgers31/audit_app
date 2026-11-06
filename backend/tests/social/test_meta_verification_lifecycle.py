"""Independent kernel lifecycle and setup guards; no DB/provider operations."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from social.connections import verification_execution as execution
from social.connections import verification_process as process


FIXTURES = Path(__file__).with_name('meta_lifecycle_fixture')


@pytest.fixture
def kernel(monkeypatch):
    """Pure installation controls never modify the pytest process's signals."""
    clock = {'now': 1000.0}
    state = {'set_result': 0, 'get_result': 0, 'signal': signal.SIGKILL,
        'parents': [1234, 1234], 'fail_mask': False, 'fail_timer': False,
        'expire': False, 'calls': []}

    def prctl(option, *args):
        state['calls'].append(('prctl', option))
        clock['now'] += 21 if state['expire'] else .1
        if option == 1:
            return state['set_result']
        ctypes.cast(args[0], ctypes.POINTER(ctypes.c_int))[0] = state['signal']
        return state['get_result']

    def mask(*args):
        state['calls'].append(('mask', args))
        if state['fail_mask']:
            raise OSError('owned setup failure')

    def timer(*args):
        state['calls'].append(('timer', args))
        if state['fail_timer']:
            raise OSError('owned setup failure')

    monkeypatch.setattr(process, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(process, 'os', SimpleNamespace(getppid=lambda: state['parents'].pop(0)))
    monkeypatch.setattr(ctypes, 'CDLL', lambda *args, **kwargs: SimpleNamespace(prctl=prctl))
    monkeypatch.setattr(time, 'monotonic', lambda: clock['now'])
    fake_signal = SimpleNamespace(SIGKILL=9, SIGALRM=14, SIG_DFL=0, SIG_UNBLOCK=1,
        ITIMER_REAL=0, signal=lambda *args: state['calls'].append(('signal', args)),
        pthread_sigmask=mask, setitimer=timer)
    monkeypatch.setitem(sys.modules, 'signal', fake_signal)
    return state


@pytest.mark.parametrize('owner', [True, False, 0, -1, 2147483648, '1234', None])
def test_lifecycle_owner_type_and_bounds_refuse_before_kernel_install(owner, kernel):
    with pytest.raises(ValueError):
        process.arm_lifecycle({'owner_pid': owner, 'deadline': 1005.0})
    assert not kernel['calls']


@pytest.mark.parametrize('deadline', [True, False, float('nan'), float('inf'),
    -1, 0, 'soon', None, 999.0, 1021.0])
def test_lifecycle_deadline_is_finite_positive_and_cannot_widen(deadline, kernel):
    with pytest.raises(ValueError):
        process.arm_lifecycle({'owner_pid': 1234, 'deadline': deadline})
    assert not kernel['calls']


@pytest.mark.parametrize('failure', ['set', 'get', 'readback', 'parent_changed', 'mask', 'timer', 'expired'])
def test_lifecycle_installation_failure_never_reports_ready(failure, kernel):
    if failure == 'set': kernel['set_result'] = -1
    elif failure == 'get': kernel['get_result'] = -1
    elif failure == 'readback': kernel['signal'] = signal.SIGTERM
    elif failure == 'parent_changed': kernel['parents'] = [1234, 4321]
    elif failure == 'mask': kernel['fail_mask'] = True
    elif failure == 'timer': kernel['fail_timer'] = True
    elif failure == 'expired': kernel['expire'] = True
    with pytest.raises((ValueError, OSError)):
        process.arm_lifecycle({'owner_pid': 1234, 'deadline': 1005.0})
    assert not any(kind == 'timer' for kind, _ in kernel['calls']) or failure == 'timer'


def test_lifecycle_timer_is_default_unblocked_and_uses_remaining_setup_budget(kernel):
    process.arm_lifecycle({'owner_pid': 1234, 'deadline': 1005.0})
    assert kernel['calls'][:2] == [('prctl', 1), ('prctl', 2)]
    assert ('signal', (14, 0)) in kernel['calls']
    assert ('mask', (1, {14})) in kernel['calls']
    kind, (which, seconds) = kernel['calls'][-1]
    assert kind == 'timer' and which == 0 and 0 < seconds < 5.0


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux parent-death and subreaper contract')
@pytest.mark.parametrize('phase,action', [('dns', 'kill'), ('dns', 'stop'), ('input', 'kill'), ('input', 'stop')])
def test_actual_main_closes_after_owner_loss_or_stall_before_input_and_in_dns(phase, action, tmp_path):
    libc = ctypes.CDLL(None)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    directory = tmp_path / phase
    directory.mkdir()
    entry = directory / 'entry.py'
    app_root = str(Path(execution.__file__).resolve().parents[2])
    entry.write_text('APP_ROOT=' + repr(app_root) + '\nPHASE_DIRECTORY=' + repr(str(directory)) + '\n' +
        (FIXTURES / 'owner_entry.py').read_text())
    parent, identity, reaped = None, None, False
    try:
        parent = subprocess.Popen([sys.executable, '-I', *(['-O'] if sys.flags.optimize else []),
            '-B', str(FIXTURES / 'owner_parent.py')], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                'PYTHON_DOTENV_DISABLED': '1', 'DATABASE_URL': 'postgresql+psycopg2://inert@127.0.0.1:9/inert'})
        parent.stdin.write(json.dumps({'app_root': app_root, 'entrypoint': str(entry),
            'phase': phase, 'seconds': 3}).encode())
        parent.stdin.close()
        setup_end = time.monotonic() + 8
        while not (directory / 'ready.json').exists():
            assert parent.poll() is None and time.monotonic() < setup_end, 'owned parent setup failed'
            time.sleep(.01)
        deadline = json.loads((directory / 'ready.json').read_text())['deadline']
        while not (directory / 'phase.json').exists() and time.monotonic() < deadline - .1:
            assert parent.poll() is None, 'parent failed before intended phase'
            time.sleep(.01)
        identity = json.loads((directory / 'phase.json').read_text())
        assert identity['parent'] == parent.pid and identity['pid'] == identity['pgid']
        if action == 'kill':
            assert deadline - time.monotonic() > .75, 'independent parent-death margin unavailable'
            assert identity['alarm_seconds'] > .75
            killed_at = time.monotonic()
            parent.kill()
            parent.wait(timeout=1)
            death_end = killed_at + .5
            state_path = Path('/proc') / str(identity['pid']) / 'stat'
            state = 'unobserved'
            while time.monotonic() < death_end:
                state = state_path.read_text().rsplit(')', 1)[1].split()[0] if state_path.exists() else None
                if state in (None, 'Z'):
                    break
                time.sleep(.01)
            assert state in (None, 'Z'), 'parent-death signal did not terminate the child'
            assert time.monotonic() - killed_at <= .5
        elif phase != 'input':
            os.kill(parent.pid, signal.SIGSTOP)
        while time.monotonic() < deadline + .25:
            time.sleep(max(0, min(.01, deadline + .25 - time.monotonic())))
        state_path = Path('/proc') / str(identity['pid']) / 'stat'
        state = state_path.read_text().rsplit(')', 1)[1].split()[0] if state_path.exists() else None
        assert state in (None, 'Z'), 'actual child outlived its owner/deadline'
        if phase == 'input':
            assert identity['alarm_seconds'] > 0
            assert identity['parent_death_signal'] == signal.SIGKILL
    finally:
        try:
            if parent is not None and parent.poll() is None:
                parent.kill(); parent.wait(timeout=1)
            if identity is None and (directory / 'spawn.json').exists():
                identity = json.loads((directory / 'spawn.json').read_text())
            if identity is not None:
                assert identity['parent'] == parent.pid and identity['pid'] == identity['pgid']
                try: os.killpg(identity['pgid'], signal.SIGKILL)
                except ProcessLookupError: pass
                until = time.monotonic() + 2
                while time.monotonic() < until:
                    try: pid, _ = os.waitpid(identity['pid'], os.WNOHANG)
                    except ChildProcessError:
                        reaped = not (Path('/proc') / str(identity['pid'])).exists(); break
                    if pid == identity['pid']:
                        reaped = True; break
                    time.sleep(.01)
                assert reaped, 'owned child was not positively reaped'
        finally:
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0
