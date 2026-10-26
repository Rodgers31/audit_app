"""Default-off, stdlib-only owner of one web group and one social group.

No worker/SQLAlchemy/SDK imports are allowed here. Host stop-interval acceptance
is an operator prerequisite; a configured local deadline does not certify it.
"""
import ctypes
import json
import math
import os
import signal
import subprocess
import sys
import time


def web_command(environ):
    return ['gunicorn', 'main:app', '--worker-class', 'uvicorn.workers.UvicornWorker',
            '--workers', '1', '--forwarded-allow-ips', '',
            '--bind', '0.0.0.0:' + (environ.get('PORT') or '8000'),
            '--access-logfile', '-', '--error-logfile', '-', '--log-level', 'info',
            '--timeout', '120', '--keep-alive', '5', '--max-requests', '1000', '--max-requests-jitter', '100']


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), separators=(',', ':')), flush=True)


def settings(environ):
    enabled = environ.get('SOCIAL_WORKER_SUPERVISOR_ENABLED', 'false')
    if enabled not in ('true', 'false'):
        raise ValueError()
    if enabled == 'false':
        return None
    if (environ.get('SOCIAL_NATIVE_ENABLED') != 'true'
            or environ.get('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED') != 'true'
            or not environ.get('SOCIAL_WORKER_DATABASE_URL')
            or not environ.get('SOCIAL_WORKER_ROLE')):
        raise ValueError()
    seconds = float(environ['SOCIAL_WORKER_SHUTDOWN_SECONDS'])
    if not math.isfinite(seconds) or not 1 <= seconds <= 300:
        raise ValueError()
    return seconds


def worker_command(environ, receipt_fd):
    return [sys.executable, '-m', 'social.worker', '--native-meta',
            '--database-url-env', 'SOCIAL_WORKER_DATABASE_URL',
            '--worker-role', environ['SOCIAL_WORKER_ROLE'],
            '--database-schema', environ.get('SOCIAL_WORKER_DATABASE_SCHEMA', 'public'),
            '--deployment-version', environ.get('RENDER_GIT_COMMIT', 'container'),
            '--supervisor-receipt-fd', str(receipt_fd)]


def _subreaper():
    if sys.platform == 'linux':
        # Reap orphaned Gunicorn descendants even when this isn't container PID1.
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise RuntimeError('Subreaper unavailable')


def _signal(child, sig):
    try:
        os.killpg(child.pid, sig)
    except ProcessLookupError:
        pass  # The owned group has already disappeared.
    except PermissionError:
        emit('owned_group_signal_failed', group_id=child.pid, error_code='GROUP_UNAVAILABLE')


def _group_present(child):
    child.poll()
    if child.returncode is not None:
        while True:
            try:
                pid, _ = os.waitpid(-child.pid, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
    try:
        os.killpg(child.pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Presence cannot be disproved (notably adopted orphans on macOS).
        # Retain uncertainty and still clean up the other owned child.
        return True


def _stop_group(child, deadline):
    _signal(child, signal.SIGTERM)
    while _group_present(child) and time.monotonic() < deadline:
        time.sleep(0.02)
    forced = _group_present(child)
    if forced:
        _signal(child, signal.SIGKILL)
    # wait() reaps only our own child. A finite post-kill reap window never
    # reports closure unless the full owned group has actually disappeared.
    child.wait(timeout=2)
    reap_until = time.monotonic() + 2
    while _group_present(child) and time.monotonic() < reap_until:
        time.sleep(0.02)
    joined = not _group_present(child)
    return joined, forced


def supervise(web_argv, worker_argv_factory, seconds):
    """Test seam supplies inert child programs; production uses fixed commands."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 1 <= seconds <= 300:
        raise ValueError('Finite bounded shutdown seconds required')
    _subreaper()
    stop = False
    handlers = {}
    web, worker = None, None
    read_fd, write_fd = None, None
    worker_reported = False
    result = 0

    def request_stop(signum, frame):
        nonlocal stop
        stop = True

    def report_worker(joined, forced):
        nonlocal worker_reported
        if worker_reported:
            return
        worker_reported = True
        proof = None
        raw = os.read(read_fd, 4097)
        if joined and not forced and worker.returncode == 0 and len(raw) <= 4096:
            try:
                candidate = json.loads(raw)
                if (type(candidate) is dict and set(candidate) == {'version','owner_id','generation','providers_closed','executor_closed','claims_drained'}
                        and type(candidate.get('version')) is int and candidate['version'] == 1
                        and type(candidate.get('owner_id')) is str and len(candidate['owner_id']) == 36
                        and type(candidate.get('generation')) is int and candidate['generation'] > 0
                        and all(candidate.get(key) is True for key in ('providers_closed', 'executor_closed', 'claims_drained'))):
                    from uuid import UUID
                    UUID(candidate['owner_id'])
                    proof = dict(candidate, process_joined=True, worker_exit_code=0)
            except (ValueError, TypeError, KeyError, RecursionError):
                pass  # Missing/malformed receipt cannot establish clean closure.
        emit('social_worker_unavailable', exit_code=worker.returncode, group_joined=joined,
             deadline_kill=forced, release_proof=proof, ownership_retained=True)

    try:
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        for sig in (signal.SIGTERM, signal.SIGINT):
            handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, request_stop)
        web = subprocess.Popen(web_argv, shell=False, start_new_session=True)
        if not stop:
            worker = subprocess.Popen(worker_argv_factory(write_fd), shell=False, start_new_session=True, pass_fds=(write_fd,))
        os.close(write_fd)
        write_fd = None
        emit('social_supervisor_started', web_pid=web.pid, worker_pid=worker.pid if worker else None,
             worker_state='starting', shutdown_seconds=seconds, host_budget_accepted=False)
        while not stop and web.poll() is None:
            if worker is not None and worker.poll() is not None and not worker_reported:
                joined, forced = _stop_group(worker, time.monotonic() + min(seconds, 1))
                report_worker(joined, forced)
            time.sleep(0.02)
        if web.poll() is not None:
            result = 1
        deadline = time.monotonic() + seconds
        shutdown_started = time.monotonic()
        if worker is not None:
            worker_stop_started = time.monotonic()
            joined, forced = _stop_group(worker, deadline)
            emit('social_worker_stop_measured', elapsed_seconds=time.monotonic()-worker_stop_started,
                 group_joined=joined, deadline_kill=forced)
            report_worker(joined, forced)
            if forced or not joined or worker.returncode != 0:
                result = 1
        web_stop_started = time.monotonic()
        joined, forced = _stop_group(web, deadline)
        if not joined or forced:
            result = 1
        emit('social_supervisor_stopped', web_joined=joined, exit_code=result,
             web_stop_seconds=time.monotonic()-web_stop_started,
             total_stop_seconds=time.monotonic()-shutdown_started)
        return result
    finally:
        # A spawn/pipe/wait error also owns cleanup; never orphan the earlier child.
        for child in (worker, web):
            try:
                if child is not None and _group_present(child):
                    _signal(child, signal.SIGKILL)
                    child.wait(timeout=2)
                    if _group_present(child):
                        emit('owned_group_cleanup_unresolved', group_id=child.pid)
            except Exception:
                emit('owned_group_cleanup_failed', group_id=child.pid, error_code='GROUP_UNAVAILABLE')
        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main():
    try:
        seconds = settings(os.environ)
        if seconds is None:
            argv = web_command(os.environ)
            os.execvp(argv[0], argv)
        return supervise(web_command(os.environ), lambda fd: worker_command(os.environ, fd), seconds)
    except Exception:
        emit('social_supervisor_unavailable', error_code='SUPERVISOR_UNAVAILABLE')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
