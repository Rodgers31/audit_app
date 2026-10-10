"""Execute one verification command and bind its raw output to its source."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
name = sys.argv[1]
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*\.json", name):
    raise ValueError("Use a fresh JSON receipt filename inside the evidence directory")
out = root / "batch9-legacy-etl-evidence" / name
if out.exists() or out.is_symlink():
    raise ValueError("Receipt destinations are append-only and cannot be symlinks")
command = sys.argv[2:]
if not command:
    raise ValueError("An explicit verification command is required")
generator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def source_snapshot():
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files
            if (p.startswith("etl/") or p.startswith("backend/seeding/") or p.startswith("backend/tests/test_batch9_legacy") or p.startswith("backend/tests/batch9_legacy")) and (root / p).is_file()}

source_hashes = source_snapshot()
head_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
source_after = source_snapshot()
head_after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
generator_after = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
source_stable = source_hashes == source_after and head_before == head_after and generator_hash == generator_after
receipt = {"generated_by": "batch9-legacy-etl-evidence/run_receipt.py", "generator_sha256": generator_hash,
           "generated_at": datetime.now(timezone.utc).isoformat(), "target_commit": head_before,
           "end_target_commit": head_after, "source_stable": source_stable, "end_source_sha256": source_after,
           "end_generator_sha256": generator_after,
           "source_sha256": source_hashes, "command": command, "cwd": str(root), "python": platform.python_version(),
           "environment": {k: ("[redacted]" if k.endswith("DATABASE_URL") and os.environ.get(k) else os.environ.get(k)) for k in ("DATABASE_URL", "BATCH9_LEGACY_DATABASE_URL", "PYTHONPATH", "PYTHON_DOTENV_DISABLED", "ADMIN_ETL_DISPATCH_ENABLED")},
           "exit_code": result.returncode, "verdict": "PASSED" if result.returncode == 0 and source_stable else "FAILED", "output": result.stdout}
for key in ("DATABASE_URL", "BATCH9_LEGACY_DATABASE_URL"):
    value = os.environ.get(key)
    if value:
        receipt["output"] = receipt["output"].replace(value, "[redacted database URL]")
with out.open("x") as stream:
    stream.write(json.dumps(receipt, indent=2) + "\n")
check = json.loads(out.read_text())
if check != receipt:
    raise ValueError("Receipt readback failed")
print(receipt["output"])
print(f"Receipt {out.name}: exit={result.returncode}, generator={generator_hash}")
sys.exit(result.returncode or (0 if source_stable else 1))
