"""Replay the final unchanged process measurements on the exact owned base files.

Only the six owned legacy files and new ownership module are temporarily changed.
All bytes are restored even when the expected defect assertions fail.
Run only when other tests/reviewers are idle.
"""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
base = "9e97ca3f1ca43f103a8655447a86d889456a218a"
paths = ["etl/backfill.py", "etl/database_loader.py", "etl/kenya_pipeline.py",
         "etl/monitored_runner.py", "etl/scheduler.py", "etl/worker.py",
         "etl/writer_ownership.py"]
saved = {path: (root / path).read_bytes() for path in paths}
try:
    for path in paths[:-1]:
        (root / path).write_bytes(subprocess.check_output(["git", "show", base + ":" + path], cwd=root))
    (root / paths[-1]).unlink()
    result = subprocess.run([sys.executable, str(root / "batch9-legacy-etl-evidence/run_receipt.py"),
        "baseline-final-red.json", sys.executable, "-m", "pytest",
        "backend/tests/test_batch9_legacy_etl_ownership.py", "--confcutdir=backend/tests", "-q",
        "-k", "legacy_first_blocks_native_or_dispatch_then_next_run or simultaneous_starts_have_one_effect",
        "--basetemp=/tmp/batch9-legacy-etl-final-red"], cwd=root, env=os.environ.copy())
    assert result.returncode == 1, "Pinned base must reproduce the expected defect"
finally:
    for path, contents in saved.items():
        (root / path).write_bytes(contents)
    assert all((root / path).read_bytes() == contents for path, contents in saved.items())
    print("owned_candidate_bytes_restored=true")
