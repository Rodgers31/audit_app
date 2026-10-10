"""Exercise the public recorder in an owned Git tree with inert child commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "backend/seeding/reconciliation.py"


@pytest.fixture
def owned_tree(tmp_path):
    paths = [SOURCE, "backend/seeding/reconcile_operator.py", "backend/models.py",
             "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py",
             "batch9-reconciliation-evidence/run_receipt.py",
             "batch9-reconciliation-evidence/receipt_safety.py"]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Owned receipt control", "-c", "user.email=receipt@example.invalid",
                  "commit", "-qm", "Owned baseline"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    return tmp_path


def invoke(root, code, name="control"):
    env = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1",
           "BATCH9_RECONCILIATION_DATABASE_URL":
               "postgresql+psycopg2://postgres@127.0.0.1:55496/batch9-review-592-inert"}
    result = subprocess.run([sys.executable, str(root / "batch9-reconciliation-evidence/run_receipt.py"),
                             name, sys.executable, "-c", code],
                            env=env, cwd=root, text=True, capture_output=True, timeout=30)
    path = root / "batch9-reconciliation-evidence" / (name + ".json")
    return result, json.loads(path.read_text()) if path.exists() else None


@pytest.mark.parametrize("change", ["source", "delete", "generator", "safety", "head", "inventory"])
def test_successful_child_cannot_certify_changed_source(owned_tree, change):
    commands = {
        "source": f"from pathlib import Path; p=Path('{SOURCE}'); p.write_text(p.read_text()+'\\n# owned mutation\\n')",
        "delete": f"from pathlib import Path; Path('{SOURCE}').unlink()",
        "generator": "from pathlib import Path; p=Path('batch9-reconciliation-evidence/run_receipt.py'); p.write_text(p.read_text()+'\\n# changed\\n')",
        "safety": "from pathlib import Path; p=Path('batch9-reconciliation-evidence/receipt_safety.py'); p.write_text(p.read_text()+'\\n# changed\\n')",
        "head": "import subprocess; subprocess.run(['git','-c','user.name=Owned','-c','user.email=owned@example.invalid','commit','--allow-empty','-qm','Owned new HEAD'],check=True)",
        "inventory": "from pathlib import Path; import subprocess; Path('backend/seeding/reconciliation_added.py').write_text('# owned addition\\n'); subprocess.run(['git','add','backend/seeding/reconciliation_added.py'],check=True)",
    }
    before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=owned_tree, text=True).strip()
    result, receipt = invoke(owned_tree, commands[change])
    assert result.returncode != 0, result.stdout + result.stderr
    assert receipt["exit_code"] == 0
    assert receipt["verification_exit_code"] != 0
    assert receipt["source_changed"] is True
    assert receipt["target_commit"] == before
    assert receipt["verdict"] == "FAIL"
    assert receipt["source_before"] != receipt["source_after"]


def test_unchanged_success_and_child_failure_keep_distinct_verdicts(owned_tree):
    good, success = invoke(owned_tree, "print('owned child executed')")
    assert good.returncode == 0
    assert success["verdict"] == "PASS"
    assert success["source_before"] == success["source_after"]
    bad, failed = invoke(owned_tree, "raise SystemExit(7)", "failed")
    assert bad.returncode == 7
    assert failed["exit_code"] == 7
    assert failed["verification_exit_code"] == 7
    assert failed["source_changed"] is False
    assert failed["verdict"] == "FAIL"


@pytest.mark.parametrize("name", ["control", "../escape"])
def test_invalid_or_existing_destination_refuses_before_child(owned_tree, name):
    existing = owned_tree / "batch9-reconciliation-evidence/control.json"
    existing.write_text('{"historical":true}\n')
    before = existing.read_bytes()
    result, _ = invoke(owned_tree, "from pathlib import Path; Path('child-ran').write_text('ran')", name)
    assert result.returncode != 0
    assert not (owned_tree / "child-ran").exists()
    assert existing.read_bytes() == before
