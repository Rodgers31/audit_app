"""Run an explicit owned-fixture command and preserve its output and provenance."""
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from receipt_safety import owned_environment, public_environment, redact

ROOT = Path(__file__).resolve().parents[1]


def source_identity(previous=()):
    paths = {str(p.relative_to(ROOT)) for pattern in (
        "backend/seeding/reconcil*.py", "backend/tests/test_batch9_reconcil*.py",
        "backend/tests/batch9_reconciliation_fixture/*.py", "backend/alembic/versions/e583*.py")
        for p in ROOT.glob(pattern)}
    paths.update(("backend/models.py", str(Path(__file__).relative_to(ROOT)),
                  "batch9-reconciliation-evidence/receipt_safety.py"))
    current = sorted(paths)
    paths.update(previous)
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
            "tracked_status": subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                                        cwd=ROOT, text=True),
            "inventory": current,
            "sha256": {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                       if (ROOT / relative).is_file() else None for relative in sorted(paths)}}


def main():
    name, runtime, *command = sys.argv[1:]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("Use a simple fresh receipt name")
    path = Path(__file__).parent / (name + ".json")
    if path.exists() or path.is_symlink():
        raise RuntimeError("Receipts are append-only; choose a new name")
    env = owned_environment(ROOT)
    before = source_identity()
    required = ("backend/seeding/reconciliation.py", "backend/seeding/reconcile_operator.py",
                "backend/models.py", "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py",
                str(Path(__file__).relative_to(ROOT)), "batch9-reconciliation-evidence/receipt_safety.py")
    if any(not before["sha256"].get(relative) for relative in required):
        raise RuntimeError("Required receipt sources are missing")
    version = subprocess.run([runtime, "-c", "import sys, sqlalchemy; print(sys.version); print('SQLAlchemy', sqlalchemy.__version__)"],
                             env=env, text=True, capture_output=True, check=True).stdout
    result = subprocess.run([runtime, *command], cwd=ROOT, env=env, text=True, capture_output=True)
    after = source_identity(before["sha256"])
    changed = before != after
    verification_exit = result.returncode if result.returncode else (90 if changed else 0)
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": before["sha256"][str(Path(__file__).relative_to(ROOT))],
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "target_commit": before["head"], "target_tree": before["tree"],
               "source_sha256": before["sha256"], "source_before": before, "source_after": after,
               "source_changed": changed, "verification_exit_code": verification_exit,
               "verdict": "PASS" if verification_exit == 0 else "FAIL",
               "runtime": version, "platform": platform.platform(), "command": [runtime, *command],
               "environment": public_environment(env),
               "receipt_safety_sha256": before["sha256"]["batch9-reconciliation-evidence/receipt_safety.py"],
               "exit_code": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
    receipt = redact(receipt, env)
    with path.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    if check != receipt:
        raise RuntimeError("Receipt readback mismatch")
    print(receipt["stdout"], end="")
    print(receipt["stderr"], end="", file=sys.stderr)
    print(f"Receipt {path}: child exit {result.returncode}, verification exit {verification_exit}")
    return verification_exit


if __name__ == "__main__":
    sys.exit(main())
