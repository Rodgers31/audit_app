"""Supplementary SQLite/lifecycle replay on preinstalled read-only Linux runtimes."""
import argparse
import json
from pathlib import Path
from uuid import uuid4


IMAGE = "sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--minimum", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    out = args.out.resolve()
    if out.exists() or root == out or root in out.parents:
        raise ValueError("Fresh external output required")
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
    try:
        result = docker(*command, check=False)
        (out / "execution.log").write_text(result.stdout + result.stderr)
        print(json.dumps(dict(command=command, exit=result.returncode, image=IMAGE)))
        if result.returncode:
            raise RuntimeError("Linux replay failed; raw output preserved")
    finally:
        state = json.loads(docker("inspect", name).stdout)[0]
        if state["Name"] != "/" + name or state["Config"]["Labels"]["audit.owner"] != "batch11-bootstrap":
            raise RuntimeError("Linux cleanup ownership mismatch")
        docker("rm", "-f", "-v", state["Id"])
        if docker("inspect", name, check=False).returncode == 0:
            raise RuntimeError("Linux container survived cleanup")
        print("OWNED_LINUX_REMOVED", state["Id"], name)


if __name__ == "__main__":
    main()
