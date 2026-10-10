"""Append a new PR590 local verification without rewriting author receipts."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "backend/tests/batch9_bootstrap_fixture"))
from owned_database import owned_url


def main():
    name, *command = sys.argv[1:]
    assert name.startswith("review-") and name.replace("-", "").isalnum() and command
    raw = os.environ["BATCH9_BOOTSTRAP_POSTGRES_URL"]
    owned_url(raw)
    out, receipt = HERE / (name + ".txt"), HERE / (name + ".json")
    assert not out.exists() and not receipt.exists(), "Append-only verification"
    env = {"PATH": os.environ["PATH"], "PYTHON_DOTENV_DISABLED": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "backend"),
           "DATABASE_URL": raw, "BATCH9_BOOTSTRAP_POSTGRES_URL": raw,
           "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false",
           "ENABLE_ETL_SCHEDULER": "false", "JWT_SECRET_KEY": "batch9-review-590-inert"}
    sources = [ROOT / "backend/bootstrap.py", ROOT / "backend/seeding/exclusion.py",
               *sorted((ROOT / "backend/tests/batch9_bootstrap_fixture").glob("*.py")),
               *sorted((ROOT / "backend/tests").glob("test_batch9_bootstrap*.py")),
               *sorted(HERE.glob("*.py")), HERE / "adversarial/control.py"]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    data = {"generated_by": str(Path(__file__).relative_to(ROOT)),
            "generator_sha256": sha(Path(__file__)), "generated_at": datetime.now(timezone.utc).isoformat(),
            "command": command, "cwd": str(ROOT), "environment": env,
            "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_state": "working_tree_bound_by_source_sha256", "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in sources}}
    with out.open("w") as stream:
        stream.write(json.dumps(data, indent=2) + "\n\n"); stream.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    data.update(exit_code=result.returncode, verdict="PASSED" if result.returncode == 0 else "FAILED", output_sha256=sha(out))
    receipt.write_text(json.dumps(data, indent=2) + "\n")
    disk = json.loads(receipt.read_text())
    assert disk["generator_sha256"] == sha(Path(__file__)) and disk["output_sha256"] == sha(out)
    print(json.dumps({"receipt": str(receipt), "exit_code": result.returncode}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
