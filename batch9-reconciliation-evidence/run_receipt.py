"""Run an explicit owned-fixture command and preserve its output and provenance."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    name, runtime, *command = sys.argv[1:]
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(ROOT / "backend"),
           "DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-a46a",
           "BATCH9_RECONCILIATION_DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-a46a"}
    env.update(json.loads(os.environ.get("BATCH9_RECEIPT_ENV", "{}")))
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
               "environment": env, "exit_code": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
    path = Path(__file__).parent / (name + ".json")
    if path.exists():
        raise RuntimeError("Receipts are append-only; choose a new name")
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"]
    assert check["exit_code"] == result.returncode
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    print(f"Receipt {path}: exit {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
