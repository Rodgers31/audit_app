"""Run a bounded command and retain its exact output and source provenance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("python")
parser.add_argument("args", nargs=argparse.REMAINDER)
options = parser.parse_args()
out = Path("/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_9_SESSIONS/NATIVE_SCHEMA_READINESS")
out.mkdir(parents=True, exist_ok=True)
hash_bytes = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
environment = dict(os.environ)
environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHON_DOTENV_DISABLED="1",
    PYTHONPATH=str(ROOT / "backend"), DATABASE_URL="sqlite:///" + str(out / "owned-import.sqlite"),
    JWT_SECRET_KEY="batch9-readiness-inert-jwt-key",
    BATCH9_NATIVE_READINESS_DATABASE_URL="postgresql+psycopg2://batch9_readiness:batch9-inert-local@127.0.0.1:55495/batch9_native_readiness")
environment.pop("BATCH7_ETL_TEST_DATABASE_URL", None)
command = [options.python, *options.args]
started = datetime.now(timezone.utc).isoformat()
try:
    result = subprocess.run(command, cwd=ROOT / "backend", env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    code, output = result.returncode, result.stdout
except subprocess.TimeoutExpired as exc:
    code, output = 124, (exc.stdout or b"").decode() + "\nCOMMAND TIMEOUT\n"
receipt = {"generated_by": str(Path(__file__).resolve()), "generator_sha256": hash_bytes(Path(__file__)),
    "generated_at": started, "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_hashes": {str(path.relative_to(ROOT)): hash_bytes(path) for path in
        [ROOT / "backend/seeding/exclusion.py", ROOT / "backend/tests/test_batch9_native_schema_readiness.py"]},
    "command": command, "cwd": str(ROOT / "backend"),
    "environment": {key: environment[key] for key in ("PYTHONDONTWRITEBYTECODE", "PYTHON_DOTENV_DISABLED", "PYTHONPATH", "DATABASE_URL", "JWT_SECRET_KEY", "BATCH9_NATIVE_READINESS_DATABASE_URL")},
    "exit_code": code, "verdict": "PASSED" if code == 0 else "FAILED", "output": output}
path = out / (options.name + ".json")
path.write_text(json.dumps(receipt, indent=2) + "\n")
check = json.loads(path.read_text())
assert check["generator_sha256"] == hash_bytes(Path(__file__)) and check["exit_code"] == code
print(output)
print("Receipt:", path)
sys.exit(code)
