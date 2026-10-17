"""Linux-only owned-child guardian for a bounded local recovery exporter.

Executed as a fresh isolated Python process, never installed in an API process.
Kernel subreaping keeps even setsid descendants owned by this guardian. Only
verified direct children are signalled, through pidfds to prevent PID reuse.
"""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _children():
    raw = Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text()
    result = [int(value) for value in raw.split()]
    if any(pid <= 1 for pid in result):
        raise RuntimeError('RECOVERY_CHILD_UNAVAILABLE')
    return result


def _reap(root):
    status = None
    while True:
        try:
            pid, value = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        if pid == root:
            status = value
    return status


def _kill_owned():
    for pid in _children():
        try:
            descriptor = os.pidfd_open(pid)
        except ProcessLookupError:
            continue
        try:
            # Recheck ownership after opening the stable identity handle.
            lines = Path('/proc/' + str(pid) + '/status').read_text().splitlines()
            parent = next(int(line.split()[1]) for line in lines if line.startswith('PPid:'))
            if parent != os.getpid():
                raise RuntimeError('RECOVERY_CHILD_UNAVAILABLE')
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError):
            pass
        finally:
            os.close(descriptor)


def supervise(command, *, lifetime=40):
    if (sys.platform != 'linux' or not command or not hasattr(os, 'pidfd_open')
            or not hasattr(signal, 'pidfd_send_signal') or type(lifetime) is not int
            or not 1 <= lifetime <= 40):
        return 1
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        return 1
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    root = None
    clean = False
    try:
        _children()  # Refuse unavailable proc ownership before launching a child.
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
            stdout=sys.stdout.buffer, stderr=subprocess.DEVNULL, close_fds=True)
        root = process.pid
        deadline = time.monotonic() + lifetime
        while not stopped and time.monotonic() < deadline:
            status = _reap(root)
            if status is not None:
                # An exited launcher with ANY live adopted descendant refuses.
                clean = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0 and not _children()
                break
            time.sleep(0.02)
    except BaseException:
        clean = False
    finally:
        if root is not None:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    _kill_owned()
                    _reap(root)
                    if not _children():
                        break
                except BaseException:
                    clean = False
                time.sleep(0.02)
            try:
                if _children():
                    clean = False
            except BaseException:
                clean = False
    return 0 if clean and not stopped else 1


if __name__ == '__main__':
    try:
        result = supervise(sys.argv[1:])
    except BaseException:
        result = 1
    raise SystemExit(result)
