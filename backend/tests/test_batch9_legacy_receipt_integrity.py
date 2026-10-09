"""Delivery verification must refuse corrupted evidence under normal and -O Python."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "batch9-legacy-etl-evidence"


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("mutation", ["valid", "verdict", "exit", "generator", "source", "archive"])
def test_delivery_integrity_is_enforced_under_python_optimization(tmp_path, optimized, mutation):
    owned = tmp_path / "app"
    evidence = owned / "batch9-legacy-etl-evidence"
    shutil.copytree(EVIDENCE, evidence)
    if mutation == "archive":
        with (evidence / "historical-source.tar.gz").open("ab") as stream:
            stream.write(b"inert-corruption")
    elif mutation != "valid":
        path = evidence / "process-final-current.json"
        receipt = json.loads(path.read_text())
        if mutation == "verdict":
            receipt["verdict"] = "FAILED"
        elif mutation == "exit":
            receipt["exit_code"] = 1
        elif mutation == "generator":
            receipt["generator_sha256"] = "0" * 64
        elif mutation == "source":
            receipt["source_sha256"]["etl/writer_ownership.py"] = "0" * 64
        path.write_text(json.dumps(receipt))
    command = [sys.executable, *(["-O"] if optimized else []), str(evidence / "verify_delivery.py"), "--historical-only"]
    result = subprocess.run(command, cwd=owned,
                            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True)
    if mutation == "valid":
        assert result.returncode == 0, result.stdout + result.stderr
        output = json.loads((evidence / "historical-delivery-provenance.json").read_text())
        assert output["verdict"] == "PASSED"
        assert output["verified_author_commit"] == "b4128f7012951d79e0fc4c58305a60a3baafd7aa"
        assert "historical author" in output["scope"]
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "Delivery verification failed" in result.stderr
        assert not (evidence / "historical-delivery-provenance.json").exists()


@pytest.mark.parametrize("optimized", [False, True])
def test_historical_success_cannot_certify_an_edited_candidate_without_fresh_checks(tmp_path, optimized):
    owned = tmp_path / "app"
    evidence = owned / "batch9-legacy-etl-evidence"
    shutil.copytree(EVIDENCE, evidence)
    (evidence / "review-verification-manifest.json").unlink(missing_ok=True)
    result = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(evidence / "verify_delivery.py")],
                            cwd=owned, env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "fresh source-bound candidate verification manifest required" in result.stderr
    assert not (evidence / "review-delivery-provenance.json").exists()


@pytest.mark.parametrize("mutates", [False, True, "generator"])
def test_receipt_runner_does_not_certify_source_changes_during_execution(tmp_path, mutates):
    root = tmp_path / "app"
    evidence = root / "batch9-legacy-etl-evidence"
    evidence.mkdir(parents=True)
    shutil.copyfile(EVIDENCE / "run_receipt.py", evidence / "run_receipt.py")
    (root / "etl").mkdir()
    (root / "etl/inert.py").write_text("VALUE = 'before'\n")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Owned receipt fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    target = "batch9-legacy-etl-evidence/run_receipt.py" if mutates == "generator" else "etl/inert.py"
    code = f"from pathlib import Path; p=Path({target!r}); p.write_text(p.read_text()+'\\n# inert changed bytes\\n')" if mutates else "print('inert check completed')"
    result = subprocess.run([sys.executable, str(evidence / "run_receipt.py"), "owned.json", sys.executable, "-c", code],
                            cwd=root, env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True)
    receipt = json.loads((evidence / "owned.json").read_text())
    if mutates:
        assert result.returncode != 0
        assert receipt["verdict"] == "FAILED"
        assert receipt["source_stable"] is False
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert receipt["verdict"] == "PASSED"
        assert receipt["source_stable"] is True


@pytest.mark.parametrize("override", ["valid", "hostaddr-query", "service-query", "remote-host", "other-database", "libpq-hostaddr", "unowned-port-selector"])
@pytest.mark.parametrize("optimized", [False, True])
def test_destructive_process_target_refuses_redirects_before_any_connection(tmp_path, override, optimized):
    target = ROOT / "backend/tests/batch9_legacy_fixture/batch9_legacy_target.py"
    raw = "postgresql+psycopg2://batch9_review_596:batch9-review-inert-local@127.0.0.1:55506/batch9-review-596"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    if override == "hostaddr-query":
        raw += "?hostaddr=203.0.113.7"
    elif override == "service-query":
        raw += "?service=inert-redirect"
    elif override == "remote-host":
        raw = raw.replace("127.0.0.1", "203.0.113.7")
    elif override == "other-database":
        raw = raw.replace("/batch9-review-596", "/other")
    elif override == "libpq-hostaddr":
        env["PGHOSTADDR"] = "203.0.113.7"
    elif override == "unowned-port-selector":
        env["BATCH9_LEGACY_FIXTURE_PORT"] = "55508"
    code = f"import runpy; target=runpy.run_path({str(target)!r}); target['validate_target']({raw!r}); print('validated-before-connection')"
    result = subprocess.run([sys.executable, *(["-O"] if optimized else []), "-c", code],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    if override == "valid":
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "validated-before-connection"
    else:
        assert result.returncode != 0
        assert "Exact owned legacy fixture target required" in result.stderr
        assert "validated-before-connection" not in result.stdout
