"""Low-footprint Linux host bound for exactly one qualification worker.

No API imports, arbitrary command, storage client or admission override. The
existing cgroup remains the kernel bound; sample for 64MiB of API headroom and
stop only this owned process group when the shared host crosses the ceiling.
"""
import json
import os
from pathlib import Path
import selectors
import resource
import signal
import subprocess
import sys
import time

from admin_etl_qualification import WORKER_SECONDS, qualification

MIB = 1024 * 1024
HOST_MAX = 512 * MIB
RESERVE = 64 * MIB
ADMISSION_MAX = 320 * MIB
MAX_OUTPUT = 4096
DB_ENV = ("DATABASE_URL", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME", "DB_SSLMODE")
POLICY_ENV = ("ADMIN_ETL_DISPATCH_ENABLED", "ADMIN_ETL_DISPATCH_SOURCES",
              "ADMIN_ETL_QUALIFICATION_POLICY", "SEED_OPENDATA_INGESTION_ENABLED",
              "SEED_KNBS_RELEASE_DISCOVERY_ENABLED", "SOCIAL_GENERATION_HOOK_ENABLED")


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (60, 61))
    resource.setrlimit(resource.RLIMIT_DATA, (128 * MIB, 128 * MIB))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def receipt_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate receipt field")
        value[key] = item
    return value


def memory_usage():
    # Render exposes the service cgroup here. Unknown/unlimited/other-tier
    # layouts refuse rather than substituting unrelated host RAM statistics.
    root = Path("/sys/fs/cgroup")
    limit = (root / "memory.max").read_text().strip()
    value = (root / "memory.current").read_text().strip()
    if not limit.isdecimal() or not value.isdecimal():
        raise ValueError("Cgroup memory evidence unavailable")
    maximum, current = int(limit), int(value)
    if maximum != HOST_MAX or not 0 < current <= maximum:
        raise ValueError("Existing host allocation mismatch")
    return current


def group_absent(pid):
    try:
        os.killpg(pid, 0)
        return False
    except ProcessLookupError:
        return True


def exit_observed(child):
    # Keep the leader waitable until the last group signal. Reaping it early
    # would allow its PID/PGID to be reused before a later killpg.
    return os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def group_has_descendants(pid):
    processes = [p for p in Path('/proc').iterdir() if p.name.isdecimal()]
    if len(processes) > 8192:
        raise ValueError("Process-group evidence exceeds bound")
    leader_seen = False
    for process in processes:
        try:
            fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
        except FileNotFoundError:
            continue
        group = int(fields[2])
        identity = int(process.name)
        leader_seen |= identity == pid
        if group == pid and identity != pid:
            return True
    if not leader_seen:
        raise ValueError("Owned leader identity unavailable")
    return False


def stop_group(child):
    if child.returncode is not None:
        return group_absent(child.pid)  # Observation only after reaping.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try: os.killpg(child.pid, sig)
        except ProcessLookupError: pass
        if sig == signal.SIGTERM:
            end = time.monotonic() + 3
            while not exit_observed(child) and time.monotonic() < end:
                time.sleep(.02)
    # Every signal above targeted the still-owned, unreaped leader's group.
    child.wait(timeout=2)
    return group_absent(child.pid)


def supervise(retire=None):
    from uuid import UUID
    if sys.platform != 'linux':
        raise ValueError("Linux process and cgroup evidence required")
    if retire is None:
        policy = qualification()
        if policy is None or os.environ.get("ADMIN_ETL_DISPATCH_ENABLED") != "true":
            raise ValueError("Explicit qualification admission required")
        expected_generation = policy.generation
    else:
        if (not isinstance(retire, UUID) or retire.version != 4
                or os.environ.get("ADMIN_ETL_DISPATCH_ENABLED") != "false"):
            raise ValueError("Inactive readiness reconciliation required")
        expected_generation = retire
    initial = memory_usage()
    if initial > ADMISSION_MAX:
        raise ValueError("Insufficient API memory reserve")
    env = {k: os.environ[k] for k in DB_ENV + POLICY_ENV + ("AUTO_SEEDER_ENABLED",) if k in os.environ}
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1",
               ADMIN_ETL_QUALIFICATION_PARENT=str(os.getpid()),
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               NUMEXPR_NUM_THREADS="1", MALLOC_ARENA_MAX="2")
    child = None
    peak, output = initial, bytearray()
    reason, closed, child_result = None, False, None
    started = time.monotonic()
    interrupted = False

    def request_stop(signum, frame):
        nonlocal interrupted
        interrupted = True

    prior = {s: signal.signal(s, request_stop) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        child = subprocess.Popen([sys.executable, "-B", "-m", "admin_etl_qualification_worker",
                *(["--retire-readiness", str(retire)] if retire is not None else [])],
            cwd=Path(__file__).resolve().parent, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            preexec_fn=child_limits)
        with selectors.DefaultSelector() as reader:
            reader.register(child.stdout, selectors.EVENT_READ)
            while True:
                peak = max(peak, memory_usage())
                if interrupted or time.monotonic() - started >= WORKER_SECONDS - 5 or peak > HOST_MAX - RESERVE:
                    reason = "INTERRUPTED" if interrupted else "WHOLE_RUN_OR_MEMORY_BOUND"
                    break
                for key, _ in reader.select(timeout=.1):
                    data = os.read(key.fileobj.fileno(), MAX_OUTPUT + 1)
                    output.extend(data)
                    if len(output) > MAX_OUTPUT:
                        reason = "WORKER_OUTPUT_BOUND"
                        break
                    if not data:
                        reader.unregister(key.fileobj)
                if reason or exit_observed(child) and not reader.get_map():
                    break
        # A clean leader exit is insufficient if its descendants are still
        # running. We still stop/reap our group, but forced closure cannot turn
        # an incomplete process tree into successful execution evidence.
        if reason is None and group_has_descendants(child.pid):
            reason = "WORKER_GROUP_RETAINED"
        closed = stop_group(child)
        if reason is None:
            try:
                value = json.loads(output, object_pairs_hook=receipt_object)
                if (type(value) is not dict or set(value) != {
                        "status", "generation", "command_id", "readiness_closed"}
                        or value["generation"] != str(expected_generation)
                        or value["status"] not in (("readiness_retired",) if retire is not None else
                            ("completed", "failed", "no_intent", "execution_unverified"))
                        or value["readiness_closed"] is not True):
                    raise ValueError()
                from uuid import UUID
                if value["command_id"] is not None:
                    if type(value["command_id"]) is not str:
                        raise ValueError()
                    identity = UUID(value["command_id"])
                    if str(identity) != value["command_id"] or identity.version != 4:
                        raise ValueError()
                child_result = value
            except (ValueError, TypeError, KeyError):
                reason = "WORKER_RECEIPT_UNVERIFIED"
        expected_status = "completed" if retire is None else "readiness_retired"
        intent_matches = (child_result is not None and
                          (child_result["command_id"] is not None if retire is None else
                           child_result["command_id"] is None))
        success = (closed and reason is None and child.returncode == 0 and
                   child_result["status"] == expected_status and intent_matches)
        return dict(status=("completed" if retire is None else "readiness_retired") if success else "not_verified", reason=reason,
                    worker=child_result, reaped=True, group_absent=closed,
                    sampled_api_headroom_bytes=RESERVE, sampled_cgroup_peak_bytes=peak,
                    elapsed_seconds=round(time.monotonic() - started, 3)), 0 if success else 1
    finally:
        if child is not None:
            if not closed:
                stop_group(child)
            child.stdout.close()
        for sig, handler in prior.items():
            signal.signal(sig, handler)


def main():
    try:
        if sys.platform != "linux":
            raise ValueError()
        from uuid import UUID
        if len(sys.argv) == 1:
            retire = None
        elif len(sys.argv) == 3 and sys.argv[1] == "--retire-readiness":
            retire = UUID(sys.argv[2])
            if str(retire) != sys.argv[2]:
                raise ValueError()
        else:
            raise ValueError()
        result, code = supervise(retire)
    except BaseException:
        result, code = dict(status="not_verified", reason="HOST_OR_ADMISSION_REFUSED"), 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
