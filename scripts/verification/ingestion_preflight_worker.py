"""Fresh isolated interpreter with bounded private pipes and owned process cleanup."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
from subprocess import Popen, PIPE, DEVNULL
import sys
import threading
import time

MAX_INPUT = 131_072


def _members(pgid, end):
    """Bounded PID/PGID-only census; never inspect process arguments/environment."""
    child = subprocess.Popen(
        ["/bin/ps", "-o", "pid=,pgid=", "-g", str(pgid)],
        stdin=DEVNULL,
        stdout=PIPE,
        stderr=DEVNULL,
        env={"PATH": os.defpath},
    )
    selector = selectors.DefaultSelector()
    raw = bytearray()
    try:
        os.set_blocking(child.stdout.fileno(), False)
        selector.register(child.stdout, selectors.EVENT_READ)
        while time.monotonic() < end:
            if not selector.select(min(0.01, max(0, end - time.monotonic()))):
                continue
            chunk = os.read(child.stdout.fileno(), 65_537 - len(raw))
            raw.extend(chunk)
            if len(raw) > 65_536:
                raise ValueError("census limit")
            if not chunk:
                code = child.wait(timeout=max(0, end - time.monotonic()))
                if code not in (0, 1) or (code == 1 and raw.strip()):
                    raise ValueError("census failed")
                members = set()
                for line in raw.splitlines():
                    fields = line.split()
                    if len(fields) != 2 or not all(x.isdigit() for x in fields):
                        raise ValueError("census malformed")
                    pid, group = map(int, fields)
                    if group != pgid or pid <= 0 or pid in members:
                        raise ValueError("census identity")
                    members.add(pid)
                return members
        raise TimeoutError("census timeout")
    finally:
        selector.close()
        # ps has no child processes. Always reap this exact owned helper.
        if child.poll() is None:
            child.kill()
        child.wait(timeout=max(0.001, end - time.monotonic()))
        child.stdout.close()


def _exited(pid):
    # WNOWAIT retains the leader PID even after exit, preventing group-ID reuse
    # until the exact group census/termination has finished.
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)


def bounded(packet, *, seconds, maximum=65_536):
    """Reserve cleanup INSIDE the unchanged whole-run budget; never return late success."""
    cleanup = {
        "started": False,
        "reaped": False,
        "forced": False,
        "exitcode": None,
        "pid": None,
        "group_absent": False,
    }
    outcome = {"payload": None, "error": "WORKER_CONTEXT_REFUSED", "cleanup": cleanup}
    if (
        type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0 < seconds <= 30
        or type(maximum) is not int
        or not 0 < maximum <= 65_536
        or type(packet) is not bytes
        or not 0 < len(packet) <= MAX_INPUT
        or os.name != "posix"
        or not all(
            hasattr(os, name)
            for name in ("waitid", "WNOWAIT", "WEXITED", "WNOHANG", "P_PID")
        )
        or threading.current_thread() is not threading.main_thread()
        or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL
    ):
        return outcome
    end = time.monotonic() + seconds
    work_end = end - min(1.0, seconds / 4)
    process = None
    raw = bytearray()
    selector = selectors.DefaultSelector()
    sent = 0
    eof = False
    try:
        process = Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).absolute())],
            stdin=PIPE,
            stdout=PIPE,
            stderr=DEVNULL,
            bufsize=0,
            start_new_session=True,
            env={
                "PATH": os.defpath,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHON_DOTENV_DISABLED": "1",
                "INGESTION_PREFLIGHT_WORKER_PARENT": str(os.getpid()),
            },
        )
        cleanup["started"] = True
        cleanup["pid"] = process.pid
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, "input")
        selector.register(process.stdout, selectors.EVENT_READ, "output")
        outcome["error"] = "WHOLE_RUN_TIMEOUT"
        while time.monotonic() < work_end:
            for key, _ in selector.select(
                min(0.02, max(0, work_end - time.monotonic()))
            ):
                if key.data == "input":
                    sent += os.write(key.fd, packet[sent : sent + 4096])
                    if sent == len(packet):
                        selector.unregister(process.stdin)
                        process.stdin.close()
                else:
                    chunk = os.read(key.fd, min(4096, maximum + 1 - len(raw)))
                    if not chunk:
                        selector.unregister(process.stdout)
                        eof = True
                    raw.extend(chunk)
                    if len(raw) > maximum:
                        outcome["error"] = "WORKER_OUTPUT_TOO_LARGE"
                        break
            if len(raw) > maximum:
                break
            exited = _exited(process.pid)
            if exited is not None and eof:
                if (
                    exited.si_code == os.CLD_EXITED
                    and exited.si_status == 0
                    and sent == len(packet)
                    and raw
                ):
                    outcome.update(payload=bytes(raw), error=None)
                else:
                    outcome["error"] = "WORKER_FAILED"
                break
    except BaseException:
        outcome.update(payload=None, error="WORKER_INTERRUPTED_OR_FAILED")
    finally:
        selector.close()
        if process is not None:
            try:
                members = _members(process.pid, end)
                exited = _exited(process.pid)
                if process.pid not in members:
                    raise ValueError("held leader missing from census")
                if exited is None or members - {process.pid}:
                    cleanup["forced"] = True
                    # Leader PID remains owned/unreaped even after exit.
                    os.killpg(process.pid, signal.SIGKILL)
                    while time.monotonic() < end:
                        members = _members(process.pid, end)
                        if process.pid not in members:
                            raise ValueError("held leader missing from census")
                        if not (members - {process.pid}):
                            break
                    else:
                        raise TimeoutError("group cleanup unconfirmed")
                process.wait(timeout=max(0, end - time.monotonic()))
                # Reaping the sole remaining leader must leave the group absent.
                # If identity has since been reused, refuse; never signal it.
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    cleanup["group_absent"] = True
            except BaseException:
                outcome.update(payload=None, error="WORKER_CLEANUP_UNCONFIRMED")
                # Still own the unreaped leader on this exceptional path.
                if process.returncode is None:
                    try:
                        _exited(process.pid)  # ECHILD refuses signaling an unowned ID.
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=max(0.001, end - time.monotonic()))
                    except BaseException:
                        pass
            cleanup["reaped"] = process.poll() is not None
            cleanup["exitcode"] = process.returncode
            for channel in (process.stdin, process.stdout):
                if channel is not None:
                    channel.close()
            if not cleanup["reaped"] or not cleanup["group_absent"]:
                outcome.update(payload=None, error="WORKER_CLEANUP_UNCONFIRMED")
            elif cleanup["forced"]:
                outcome.update(
                    payload=None, error=outcome["error"] or "WORKER_FORCED_TERMINATION"
                )
    if time.monotonic() > end:
        outcome.update(payload=None, error=outcome["error"] or "WHOLE_RUN_TIMEOUT")
    return outcome


def _child_main():
    """Private stdin protocol; no credentials in arguments, environment, files or errors."""
    sys.dont_write_bytecode = True
    if os.environ.get("INGESTION_PREFLIGHT_WORKER_PARENT") != str(os.getppid()):
        sys.stdout.write("{}")
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ingestion_preflight as tool

    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        tool.require(0 < len(raw) <= MAX_INPUT, "WORKER_INPUT_REFUSED")
        packet = json.loads(
            raw,
            object_pairs_hook=tool.budget._pairs,
            parse_constant=lambda _: tool.require(False, "NONFINITE_JSON"),
        )
        tool.budget.shape(
            packet, {"version", "execute", "config", "credential", "root"}
        )
        tool.require(
            type(packet["version"]) is int
            and packet["version"] == 1
            and packet["execute"] is True,
            "WORKER_INPUT_REFUSED",
        )
        root = Path(packet["root"])
        tool.require(root == tool.ROOT, "WORKER_ROOT_REFUSED")
        tool.check_config(packet["config"])
        result = tool.report()
        tool._bind(result, packet["config"], root)
        result = tool._connection_run(
            packet["config"], packet["credential"], root, result
        )
        encoded = tool.budget.canonical(result)
        tool.require(0 < len(encoded) <= 65_536, "WORKER_OUTPUT_REFUSED")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except BaseException:
        # The supervisor requires a complete bound report and exit0; '{}' cannot pass.
        sys.stdout.write("{}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_child_main())
