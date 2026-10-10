"""Current bounded command capture, with source and owned process readback.

The Batch10 recorder remains immutable historical evidence. This version
cannot certify an exited parent that left a process in its owned session.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

SECRET_ENVIRONMENT = ("DATABASE_URL", "JWT_SECRET_KEY", "BATCH9_BOOTSTRAP_POSTGRES_URL")


def require(value, message):
    if not value:
        raise ValueError(message)


def real_path(value):
    path = Path(value).absolute()
    require(".." not in path.parts and path.resolve() == path, "Symlink/traversal source refused")
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(root):
    root = real_path(root)
    def git(*args):
        return subprocess.check_output(["/usr/bin/git", "-C", str(root), *args],
            env={"PATH": "/usr/bin:/bin"}).decode()
    require(Path(git("rev-parse", "--show-toplevel").strip()) == root, "Exact Git source root required")
    paths = sorted(set(git("ls-files", "-c", "--others", "--exclude-standard", "-z").split("\0")) - {""})
    require(bool(paths), "Nonempty source required")
    # Refuse environment inputs before hashing any source bytes. This also
    # protects runtime dotenv files ignored by Git but consumed by the child.
    for directory in (root, root / "backend"):
        for candidate in directory.glob(".env*"):
            require(candidate.name.endswith((".example", ".sample", ".template")), "Runtime dotenv source refused")
    sources = {}
    for name in paths:
        filename = Path(name).name
        require((not filename.startswith(".env") and not filename.endswith(".env"))
            or filename.endswith((".example", ".sample", ".template")),
            "Runtime dotenv source refused")
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe source member")
        path = real_path(root / name)
        require(path.is_relative_to(root) and path.is_file(), "Regular source member required")
        sources[name] = digest(path)
    return dict(head=git("rev-parse", "HEAD").strip(), tree=git("rev-parse", "HEAD^{tree}").strip(),
        status=git("status", "--porcelain").strip(), sources=sources)


def group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Some hosts temporarily return EPERM while a killed group is being
        # reaped. An inaccessible group does not prove absence; keep probing.
        return True


def cleanup_group(proc):
    group = proc.pid  # start_new_session=True makes this exact owned group.
    survivors = group_exists(group)
    signals = []
    if survivors:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                break
            except PermissionError:
                # Preserve refusal and wait for physical absence. Never turn
                # a failed signal into a successful cleanup observation.
                pass
            else:
                signals.append(sig.name)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                proc.poll()  # Reap our immediate child before checking absence.
                if not group_exists(group):
                    break
                time.sleep(0.05)
            if not group_exists(group):
                break
    proc.poll()
    return dict(group=group, survivors_detected=survivors, group_absent=not group_exists(group), signals=signals)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    require(args.timeout > 0, "Positive command deadline required")
    root, output = real_path(args.root), args.output.absolute()
    raw = output.with_suffix(".txt")
    for path in (output, raw):
        require(path.resolve() == path and ".." not in path.parts, "Output symlink/traversal refused")
        require(not path.exists() and not path.is_symlink(), "Fresh exclusive output required")
        require(not path.is_relative_to(root) and not root.is_relative_to(path), "External output required")
    require(output.parent.is_dir(), "Existing external output parent required")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    require(command and Path(command[0]).is_absolute(), "Real absolute command required")
    before = identity(root)
    generator = digest(Path(__file__))
    started = datetime.now(timezone.utc).isoformat()
    env = {key: os.environ[key] for key in ("PATH", "DATABASE_URL", "PYTHONPATH", "JWT_SECRET_KEY",
        "BATCH9_BOOTSTRAP_POSTGRES_URL") if key in os.environ}
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1", AUTO_SEEDER_ENABLED="false",
        AUTO_WARMUP_ENABLED="false", ENABLE_ETL_SCHEDULER="false")
    timed_out = False
    # A descendant inheriting stdout cannot hold communicate() open after its
    # immediate parent exits; the physical process group is checked separately.
    with raw.open("xb") as stream:
        proc = subprocess.Popen(command, cwd=root / "backend", env=env, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
        try:
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        cleanup = cleanup_group(proc)
    try:
        after = identity(root)
    except (ValueError, subprocess.CalledProcessError, OSError):
        after = dict(measurement_error="Source inventory unavailable after execution")
    stable = before == after and digest(Path(__file__)) == generator
    accepted = (stable and not timed_out and proc.returncode == 0
        and not cleanup["survivors_detected"] and cleanup["group_absent"])
    receipt = dict(capture_schema=2, generated_by=str(Path(__file__).relative_to(root)),
        generator_sha256=generator, started_at=started, ended_at=datetime.now(timezone.utc).isoformat(),
        command=command, runtime=dict(executable=sys.executable, python=sys.version, platform=platform.platform(),
            recorder_optimization=sys.flags.optimize),
        environment={key: "<redacted>" if key in SECRET_ENVIRONMENT else value for key, value in env.items()},
        secret_environment_present={key: key in env for key in SECRET_ENVIRONMENT}, before=before, after=after,
        child_exit=proc.returncode, timed_out=timed_out, source_stable=stable, negative_diagnostic=None,
        pid=proc.pid, process_cleanup=cleanup, log_sha256=digest(raw), verdict="PASS" if accepted else "FAIL")
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    require(json.loads(output.read_text()) == receipt and digest(raw) == receipt["log_sha256"], "Capture readback mismatch")
    print(json.dumps(dict(output=str(output), child_exit=proc.returncode, verdict=receipt["verdict"],
        source_stable=stable, process_cleanup=cleanup)))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
