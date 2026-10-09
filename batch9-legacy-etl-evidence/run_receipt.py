"""Execute one verification command and bind its raw output to its source."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
out = root / "batch9-legacy-etl-evidence" / sys.argv[1]
command = sys.argv[2:]
generator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
source_hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files
                 if (p.startswith("etl/") or p.startswith("backend/seeding/") or p.startswith("backend/tests/test_batch9_legacy") or p.startswith("backend/tests/batch9_legacy")) and (root / p).is_file()}
result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
receipt = {"generated_by": "batch9-legacy-etl-evidence/run_receipt.py", "generator_sha256": generator_hash,
           "generated_at": datetime.now(timezone.utc).isoformat(), "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
           "source_sha256": source_hashes, "command": command, "cwd": str(root), "python": platform.python_version(),
           "environment": {k: os.environ.get(k) for k in ("DATABASE_URL", "BATCH9_LEGACY_DATABASE_URL", "PYTHONPATH", "PYTHON_DOTENV_DISABLED", "ADMIN_ETL_DISPATCH_ENABLED")},
           "exit_code": result.returncode, "verdict": "PASSED" if result.returncode == 0 else "FAILED", "output": result.stdout}
out.write_text(json.dumps(receipt, indent=2) + "\n")
check = json.loads(out.read_text())
assert check["generator_sha256"] == generator_hash and check["exit_code"] == result.returncode
print(result.stdout)
print(f"Receipt {out.name}: exit={result.returncode}, generator={generator_hash}")
sys.exit(result.returncode)
