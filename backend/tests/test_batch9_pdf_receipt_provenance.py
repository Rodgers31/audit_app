"""Execute recorder provenance checks in a self-contained owned repository."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
RECORDER = "docs/admin/implementation/batch9-pdf-pin-evidence/record_check.py"
BOUND = [".github/workflows/r2-acceptance.yml", "backend/scripts/r2_producer_acceptance.py",
         "backend/tests/test_r2_acceptance_workflow_pin.py",
         "docs/admin/implementation/batch8-producer-evidence/run_check.py"]


@pytest.fixture
def owned_recorder(tmp_path):
    root = tmp_path / "repo"
    for name in [*BOUND, RECORDER]:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO / name).read_bytes())
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "owned source"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root, tmp_path / "receipts"


@pytest.mark.parametrize("change", ["none", "source", "absent", "generator", "commit", "child-failure"])
def test_receipt_binds_execution_start_and_refuses_changed_source(owned_recorder, change):
    root, output = owned_recorder
    source = root / BOUND[2]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    command = "pass"
    if change == "source":
        command = f"from pathlib import Path; p=Path({BOUND[2]!r});p.write_bytes(p.read_bytes()+b'\\n# mutation\\n')"
    elif change == "absent":
        command = f"from pathlib import Path;Path({BOUND[2]!r}).unlink()"
    elif change == "generator":
        command = f"from pathlib import Path; p=Path({RECORDER!r});p.write_bytes(p.read_bytes()+b'\\n# mutation\\n')"
    elif change == "commit":
        command = "import subprocess;subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','new head'],check=True)"
    elif change == "child-failure":
        command = "raise SystemExit(7)"
    result = subprocess.run([sys.executable, str(root / RECORDER), "--label", "receipt",
                             "--output-dir", str(output), "--cwd", str(root), "--",
                             sys.executable, "-c", command], capture_output=True, text=True, timeout=30)
    record = json.loads((output / "receipt.json").read_text())
    assert record["source_sha256"][BOUND[2]] == before
    assert record["source_changed"] is (change in {"source", "absent", "generator", "commit"})
    expected = 0 if change == "none" else 7 if change == "child-failure" else 1
    assert result.returncode == record["verification_exit_status"] == expected
    assert record["verdict"] == ("PASS" if change == "none" else "FAILED")
    assert record["exit_status"] == (7 if change == "child-failure" else 0)


def test_missing_bound_source_refuses_before_child_execution(owned_recorder):
    root, output = owned_recorder
    (root / BOUND[0]).unlink()
    result = subprocess.run([sys.executable, str(root / RECORDER), "--label", "absent",
                             "--output-dir", str(output), "--cwd", str(root), "--",
                             sys.executable, "-c", "print('CHILD_EXECUTED')"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "required receipt source is absent before execution" in result.stderr
    assert "CHILD_EXECUTED" not in result.stdout
    assert not (output / "absent.json").exists()
