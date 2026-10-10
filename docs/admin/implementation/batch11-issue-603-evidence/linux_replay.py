"""Supplementary SQLite/lifecycle replay on preinstalled read-only Linux runtimes."""
import argparse
import json
from pathlib import Path
import re
from uuid import uuid4


IMAGE = "sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"


def readback(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
    if json.loads(path.read_text()) != value:
        raise RuntimeError("Linux cleanup receipt readback mismatch")


def inspect_owned(docker, name, out, stage):
    result = docker("inspect", name, check=False)
    readback(out / ("cleanup-" + stage + ".json"), dict(command=["inspect", name], exit=result.returncode,
        stdout=result.stdout, stderr=result.stderr))
    if result.returncode:
        absent = re.fullmatch(r"(?:error response from daemon: |error: )?no such (?:object|container): " + re.escape(name),
            result.stderr.strip(), re.I)
        if result.returncode == 1 and result.stdout.strip() in ("", "[]") and absent:
            return None
        raise RuntimeError("Cannot verify Linux container absence; Docker inspect failed")
    states = json.loads(result.stdout)
    if type(states) is not list or len(states) != 1 or type(states[0]) is not dict:
        raise RuntimeError("Malformed Linux container inspection")
    return states[0]


def cleanup_owned(docker, name, out):
    state = inspect_owned(docker, name, out, "before")
    if state is None:
        print("OWNED_LINUX_NOT_CREATED", name)
        return
    config = state.get("Config")
    labels = config.get("Labels") if type(config) is dict else None
    if (state.get("Name") != "/" + name or type(labels) is not dict
            or labels.get("audit.owner") != "batch11-bootstrap"
            or type(state.get("Id")) is not str or not state["Id"]):
        raise RuntimeError("Linux cleanup ownership mismatch")
    removed = docker("rm", "-f", "-v", state["Id"], check=False)
    readback(out / "cleanup-remove.json", dict(command=["rm", "-f", "-v", state["Id"]], exit=removed.returncode,
        stdout=removed.stdout, stderr=removed.stderr))
    if removed.returncode:
        raise RuntimeError("Linux owned container removal failed")
    if inspect_owned(docker, name, out, "after") is not None:
        raise RuntimeError("Linux container survived cleanup")
    print("OWNED_LINUX_REMOVED", state["Id"], name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--minimum", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    # Validate the requested spelling before resolution; resolving first can
    # silently admit a dangling leaf or an ancestor that redirects the output.
    out = args.out.absolute()
    if (".." in out.parts or out.resolve() != out or out.is_symlink()
            or out.exists() or root == out or root in out.parents):
        raise ValueError("Fresh external nonsymlink output required")
    out.mkdir()
    import sys
    sys.path.insert(0, str(root / "backend/tests"))
    from batch11_bootstrap_fixture.postgres import docker
    name = "batch11-bootstrap-linux-" + uuid4().hex[:16]
    python = "/owned/linux-min-venv/bin/python" if args.minimum else "/owned/linux-venv/bin/python"
    command = ["run", "--pull=never", "--name", name, "--network", "none",
        "--label", "audit.owner=batch11-bootstrap", "-v", str(root) + ":/source:ro",
        "-v", str(args.runtime_root.resolve()) + ":/owned:ro", "-v", str(out) + ":/out",
        "-w", "/source/backend", "-e", "PYTHON_DOTENV_DISABLED=1", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "DATABASE_URL=sqlite:////out/inert-parent.sqlite", "-e", "JWT_SECRET_KEY=inert-linux",
        "-e", "AUTO_SEEDER_ENABLED=false", "-e", "AUTO_WARMUP_ENABLED=false", "-e", "ENABLE_ETL_SCHEDULER=false",
        IMAGE, python, "-m", "pytest", "tests/test_batch9_bootstrap_sessions.py",
        "tests/test_batch8_exclusion_sqlite.py", "tests/test_bootstrap_defers_to_a_live_seed.py",
        "tests/test_batch10_startup_readiness.py::test_repeated_real_lifespans_cannot_reuse_previous_ready",
        "-vv", "-s", "--junitxml=/out/results.xml", "--basetemp=/out/tmp", "-o", "cache_dir=/out/cache"]
    # Docker's helper deadline is deliberately bounded; this small cohort must
    # complete in 30 seconds. PostgreSQL acceptance runs on the native host.
    primary_failure = None
    try:
        result = docker(*command, check=False)
        (out / "execution.log").write_text(result.stdout + result.stderr)
        print(json.dumps(dict(command=command, exit=result.returncode, image=IMAGE)))
        if result.returncode:
            raise RuntimeError("Linux replay failed; raw output preserved")
    except BaseException as failure:
        primary_failure = failure
        raise
    finally:
        try:
            cleanup_owned(docker, name, out)
        except Exception as cleanup_failure:
            readback(out / "cleanup-unverified.json", dict(name=name, classification="cleanup_unverified",
                error=type(cleanup_failure).__name__ + ": " + str(cleanup_failure)))
            if primary_failure is not None:
                primary_failure.add_note("Linux cleanup unverified: " + str(cleanup_failure))
                print("OWNED_LINUX_CLEANUP_UNVERIFIED", name)
            else:
                raise RuntimeError("Linux cleanup unverified; raw inspection preserved") from cleanup_failure


if __name__ == "__main__":
    main()
