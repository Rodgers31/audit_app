"""Run an explicit owned-fixture command and preserve its output and provenance."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone
from receipt_safety import owned_environment, public_environment, redact, safety_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    name, runtime, *command = sys.argv[1:]
    env = owned_environment(ROOT)
    result = subprocess.run([runtime, *command], cwd=ROOT, env=env, text=True, capture_output=True)
    sources = [p for p in ROOT.glob("backend/seeding/reconcil*.py")]
    sources += list(ROOT.glob("backend/tests/test_batch9_reconcil*.py"))
    sources += list(ROOT.glob("backend/tests/batch9_reconciliation_fixture/*.py"))
    sources += list(ROOT.glob("backend/alembic/versions/e583*.py")) + [ROOT / "backend/models.py"]
    version = subprocess.run([runtime, "-c", "import sys, sqlalchemy; print(sys.version); print('SQLAlchemy', sqlalchemy.__version__)"],
                             env=env, text=True, capture_output=True, check=True).stdout
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
               "runtime": version, "platform": platform.platform(), "command": [runtime, *command],
               "environment": public_environment(env), "receipt_safety_sha256": safety_hash(), "exit_code": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
    receipt = redact(receipt, env)
    path = Path(__file__).parent / (name + ".json")
    if path.exists():
        raise RuntimeError("Receipts are append-only; choose a new name")
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"]
    assert check["exit_code"] == result.returncode
    print(receipt["stdout"], end="")
    print(receipt["stderr"], end="", file=sys.stderr)
    print(f"Receipt {path}: exit {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
