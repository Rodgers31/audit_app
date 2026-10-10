"""Bind a bounded command to complete source bytes and fresh exclusive outputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(root, paths=None):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()

    if paths is None:
        paths = git("ls-files", "-c", "--others", "--exclude-standard").splitlines()
    return dict(
        head=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        status=git("status", "--porcelain"),
        sources={p: digest(root / p) if (root / p).is_file() else None for p in paths},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--negative-diagnostic")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.absolute()
    raw = output.with_suffix(".txt")
    if output.exists() or raw.exists() or output.is_symlink() or raw.is_symlink():
        raise RuntimeError("Refuse inherited or symlink output")
    if Path(__file__).resolve() in {output.resolve(), raw.resolve()}:
        raise RuntimeError("Refuse generator self-overwrite")
    if root == output.resolve() or root in output.resolve().parents:
        raise RuntimeError("Evidence output must be external to consumed source")
    if output.parent.resolve() != output.parent or ".." in output.parts:
        raise RuntimeError("Refuse output path escape")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise RuntimeError("A real command is required")
    before = identity(root)
    generator = digest(Path(__file__))
    started = datetime.now(timezone.utc).isoformat()
    env = {
        k: os.environ[k]
        for k in (
            "PATH",
            "DATABASE_URL",
            "PYTHONPATH",
            "JWT_SECRET_KEY",
            "BATCH9_BOOTSTRAP_POSTGRES_URL",
        )
        if k in os.environ
    }
    env.update(
        PYTHON_DOTENV_DISABLED="1",
        PYTHONDONTWRITEBYTECODE="1",
        AUTO_SEEDER_ENABLED="false",
        AUTO_WARMUP_ENABLED="false",
        ENABLE_ETL_SCHEDULER="false",
    )
    proc = subprocess.Popen(
        command,
        cwd=root / "backend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    timed_out = False
    try:
        log, _ = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        log, _ = proc.communicate(timeout=10)
    after = identity(root, before["sources"])
    stable = before == after and digest(Path(__file__)) == generator
    negative = bool(args.negative_diagnostic)
    decoded = log.decode(errors="replace")
    intended = True
    if negative:
        diagnostic = re.search(
            r"^E\s+AssertionError:.*" + re.escape(args.negative_diagnostic),
            decoded,
            re.M,
        )
        inventory = re.search(r"=+\s+[1-9][0-9]* failed", decoded)
        exceptions = re.findall(r"^E\s+([\w.]+(?:Error|Exception)):", decoded, re.M)
        intended = bool(
            diagnostic
            and inventory
            and exceptions
            and set(exceptions) == {"AssertionError"}
        )
    accepted = (
        stable
        and not timed_out
        and intended
        and (proc.returncode == 1 if negative else proc.returncode == 0)
    )
    receipt = dict(
        generated_by=str(Path(__file__).relative_to(root)),
        generator_sha256=generator,
        started_at=started,
        ended_at=datetime.now(timezone.utc).isoformat(),
        command=command,
        runtime=dict(
            executable=sys.executable, python=sys.version, platform=platform.platform()
        ),
        environment=env,
        before=before,
        after=after,
        child_exit=proc.returncode,
        timed_out=timed_out,
        source_stable=stable,
        negative_diagnostic=args.negative_diagnostic,
        log_sha256=hashlib.sha256(log).hexdigest(),
        verdict="PASS" if accepted else "FAIL",
    )
    with raw.open("xb") as stream:
        stream.write(log)
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    readback = json.loads(output.read_text())
    if readback != receipt or digest(raw) != receipt["log_sha256"]:
        raise RuntimeError("Evidence readback mismatch")
    print(
        json.dumps(
            dict(
                output=str(output),
                child_exit=proc.returncode,
                verdict=receipt["verdict"],
                source_stable=stable,
                tail=log.decode(errors="replace")[-2200:],
            )
        )
    )
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
