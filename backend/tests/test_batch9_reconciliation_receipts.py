"""Publishing controls use synthetic secrets and execute the real generators."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "batch9-reconciliation-evidence"
SECRET = "receipt-only-secret-do-not-publish"
URL = "postgresql+psycopg2://postgres:" + SECRET + "@127.0.0.1:55496/batch9-review-592-template"


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(EVIDENCE))
    spec = importlib.util.spec_from_file_location("receipt_control_" + name, EVIDENCE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(module, tmp_path, monkeypatch, output):
    folder = tmp_path / "batch9-reconciliation-evidence"
    folder.mkdir()
    copied = folder / Path(module.__file__).name
    copied.write_bytes(Path(module.__file__).read_bytes())
    (folder / "receipt_safety.py").write_bytes((EVIDENCE / "receipt_safety.py").read_bytes())
    for source in ("backend/seeding/reconciliation.py", "backend/seeding/reconcile_operator.py",
                   "backend/models.py", "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py"):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "__file__", str(copied))
    monkeypatch.setenv("BATCH9_RECONCILIATION_DATABASE_URL", URL)
    monkeypatch.setenv("BATCH9_RECEIPT_ENV", json.dumps({"PRIVATE_TOKEN": SECRET}))
    monkeypatch.setenv("BATCH9_RECEIPT_RUNTIMES", json.dumps([sys.executable]))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=output, stderr="stderr " + SECRET)

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "fixture-commit")
    monkeypatch.setattr(module.platform, "platform", lambda: "owned-control-platform")
    return folder, calls


def test_runner_redacts_environment_command_output_and_console(tmp_path, monkeypatch, capsys):
    module = load("run_receipt", monkeypatch)
    folder, _ = fixture(module, tmp_path, monkeypatch, URL + " " + SECRET)
    monkeypatch.setattr(sys, "argv", [module.__file__, "control", sys.executable, "-c", SECRET])
    assert module.main() == 0
    raw = (folder / "control.json").read_text()
    console = capsys.readouterr()
    assert SECRET not in raw + console.out + console.err
    receipt = json.loads(raw)
    assert receipt["environment"]["PRIVATE_TOKEN"] == "[REDACTED]"
    assert receipt["exit_code"] == 0
    assert receipt["generator_sha256"]


@pytest.mark.parametrize("url", [None, "postgresql://u:p@db.example/production", "postgresql://u:p@127.0.0.1:55496/postgres"])
def test_runner_requires_explicit_owned_target_before_launch(tmp_path, monkeypatch, url):
    module = load("run_receipt", monkeypatch)
    _, calls = fixture(module, tmp_path, monkeypatch, "never launched")
    if url is None:
        monkeypatch.delenv("BATCH9_RECONCILIATION_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("BATCH9_RECONCILIATION_DATABASE_URL", url)
    monkeypatch.setattr(sys, "argv", [module.__file__, "refusal", sys.executable, "-c", "pass"])
    with pytest.raises(ValueError, match="owned"):
        module.main()
    assert calls == []


def test_runner_refuses_connection_override_before_launch(tmp_path, monkeypatch):
    module = load("run_receipt", monkeypatch)
    _, calls = fixture(module, tmp_path, monkeypatch, "never launched")
    monkeypatch.setenv("BATCH9_RECEIPT_ENV", json.dumps({"DATABASE_URL": "postgresql://u:p@db.example/prod"}))
    monkeypatch.setattr(sys, "argv", [module.__file__, "refusal", sys.executable, "-c", "pass"])
    with pytest.raises(ValueError, match="owned"):
        module.main()
    assert calls == []


def test_spec_redacts_all_serialized_and_console_outputs(tmp_path, monkeypatch, capsys):
    module = load("spec_review_record", monkeypatch)
    folder, _ = fixture(module, tmp_path, monkeypatch, URL + " " + SECRET)
    monkeypatch.setattr(module, "OUT", folder / "spec-control.md")
    monkeypatch.setattr(sys, "argv", [module.__file__, "--verify"])
    module.main()
    assert SECRET not in module.OUT.read_text() + capsys.readouterr().out


def test_census_declares_exact_scope_and_tracks_omitted_launchers(tmp_path, monkeypatch):
    module = load("inventory_receipt", monkeypatch)
    for name in ("backend/writer.py", "admin/launcher.sh", "infra/render.toml", "Dockerfile", "backend/tests/control.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("initialize_reference_data()\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    evidence = tmp_path / "batch9-reconciliation-evidence"
    evidence.mkdir()
    generator = evidence / "inventory_receipt.py"
    generator.write_bytes(Path(module.__file__).read_bytes())
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "__file__", str(generator))
    monkeypatch.setattr(sys, "argv", [str(generator)])
    real = module.subprocess.check_output

    def git(command, **kwargs):
        if command == ["git", "rev-parse", "HEAD"]:
            return "fixture-commit"
        return real(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "check_output", git)
    module.main()
    receipt = json.loads(generator.with_name("writer-census.json").read_text())
    assert receipt["whole_repository_writer_coverage"] is False
    assert receipt["source_sha256"].keys() == {"backend/writer.py"}
    assert set(receipt["omitted_tracked_files"]) == {"admin/launcher.sh", "infra/render.toml", "Dockerfile", "backend/tests/control.py"}
    assert "independent" in receipt["omitted_scope_requirement"]


def test_unicode_private_input_cannot_leak_through_json_escaped_output(monkeypatch):
    safety = load("receipt_safety", monkeypatch)
    private = "receipt-only-é-secret"
    escaped = json.dumps(private)[1:-1]
    publication = safety.redact({"stdout": "child=" + escaped}, {"PRIVATE_TOKEN": private})
    assert escaped not in publication["stdout"]


def test_short_private_input_does_not_corrupt_provenance_digest(monkeypatch):
    safety = load("receipt_safety", monkeypatch)
    payload = {"generator_sha256": "a1" * 32, "stdout": "private=1"}
    publication = safety.redact(payload, {"PRIVATE_TOKEN": "1"})
    assert publication["generator_sha256"] == payload["generator_sha256"]
    assert publication["stdout"] == "private=[REDACTED]"
