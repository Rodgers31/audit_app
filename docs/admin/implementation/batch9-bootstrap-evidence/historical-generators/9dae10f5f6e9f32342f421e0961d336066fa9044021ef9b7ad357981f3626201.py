"""Append-only local receipts; execute explicit commands in an inert environment."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
name, *command = sys.argv[1:]
assert name and command
out = HERE / (name + ".txt")
receipt = HERE / (name + ".json")
assert not out.exists() and not receipt.exists(), "Receipts are append-only"
env = {"PATH": os.environ["PATH"], "PYTHON_DOTENV_DISABLED": "1",
       "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "backend"),
       "DATABASE_URL": "postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183",
       "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false",
       "JWT_SECRET_KEY": "batch9-bootstrap-inert-key"}
env["BATCH9_BOOTSTRAP_POSTGRES_URL"] = env["DATABASE_URL"]
data = {"generated_by": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(), "command": command,
        "cwd": str(ROOT), "environment": env,
        "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT / "backend/bootstrap.py", ROOT / "backend/seeding/exclusion.py",
                                    ROOT / "backend/tests/test_batch9_bootstrap_ownership.py",
                                    ROOT / "backend/tests/batch9_bootstrap_fixture/sitecustomize.py"]}}
with out.open("w") as stream:
    stream.write(json.dumps(data, indent=2) + "\n\n")
    stream.flush()
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
data["exit_code"] = result.returncode
data["verdict"] = "PASSED" if result.returncode == 0 else "FAILED"
data["output_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
receipt.write_text(json.dumps(data, indent=2) + "\n")
check = json.loads(receipt.read_text())
assert check["generator_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
assert check["exit_code"] == result.returncode
print(json.dumps({"receipt": str(receipt), "exit_code": result.returncode}))
raise SystemExit(result.returncode)
