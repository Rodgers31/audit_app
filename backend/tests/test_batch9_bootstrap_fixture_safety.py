"""Destructive bootstrap fixtures refuse redirects before constructing an engine."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import runpy
from unittest.mock import Mock

import pytest
import sqlalchemy

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/admin/implementation/batch9-bootstrap-evidence"
BASE = "postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183"
ENTRYPOINTS = ["process", "cleanup_probe.py", "migration_probe.py", "other_domain_readiness.py", "spec-readiness-control.py", "adversarial/control.py"]
BAD_INPUTS = [
    BASE + "?hostaddr=127.0.0.2", BASE + "?host=localhost", BASE + "?dbname=unowned",
    BASE + "?service=redirect", BASE + "?options=-csearch_path=public", BASE + "?port=5432",
    BASE + "?host=127.0.0.1&host=127.0.0.2", BASE.replace("127.0.0.1", "localhost"),
    BASE.replace("55492", "5432"), BASE.replace("batch9-bootstrap-1183", "unowned"),
    BASE.replace("batch9_bootstrap:", "someone_else:"), BASE.replace("psycopg2", "asyncpg"),
]


def load(path, name):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(entry, tmp_path):
    if entry == "process":
        module = load(ROOT / "backend/tests/test_batch9_bootstrap_ownership.py", "process_safety")
        next(module.owned_pg.__wrapped__(tmp_path, os.environ["BATCH9_BOOTSTRAP_POSTGRES_URL"]))
    elif entry == "adversarial/control.py":
        module = load(EVIDENCE / entry, "adversarial_safety")
        module.child("normal")
    else:
        runpy.run_path(str(EVIDENCE / entry), run_name="fixture_safety")


@pytest.mark.parametrize("entry", ENTRYPOINTS)
@pytest.mark.parametrize("raw", BAD_INPUTS)
def test_redirects_refused_before_engine_creation(monkeypatch, tmp_path, entry, raw):
    monkeypatch.setenv("DATABASE_URL", raw)
    monkeypatch.setenv("BATCH9_BOOTSTRAP_POSTGRES_URL", raw)
    engine = Mock(side_effect=AssertionError("ENGINE_CONSTRUCTED_BEFORE_REFUSAL"))
    monkeypatch.setattr(sqlalchemy, "create_engine", engine)
    with pytest.raises(ValueError, match="owned bootstrap"):
        execute(entry, tmp_path)
    engine.assert_not_called()


@pytest.mark.parametrize("entry", ENTRYPOINTS)
@pytest.mark.parametrize("name,value", [("PGHOSTADDR", "127.0.0.2"), ("PGSERVICE", "redirect"), ("PGDATABASE", "unowned"), ("PGOPTIONS", "-csearch_path=public"), ("PGSERVICEFILE", "/unused/service.conf")])
def test_ambient_redirects_refused_before_engine_creation(monkeypatch, tmp_path, entry, name, value):
    monkeypatch.setenv("DATABASE_URL", BASE)
    monkeypatch.setenv("BATCH9_BOOTSTRAP_POSTGRES_URL", BASE)
    monkeypatch.setenv(name, value)
    engine = Mock(side_effect=AssertionError("ENGINE_CONSTRUCTED_BEFORE_REFUSAL"))
    monkeypatch.setattr(sqlalchemy, "create_engine", engine)
    with pytest.raises(ValueError, match="owned bootstrap"):
        execute(entry, tmp_path)
    engine.assert_not_called()


@pytest.mark.parametrize("raw", [BASE, "postgresql+psycopg2://batch9_review_590:batch9-review-590-inert@127.0.0.1:55590/batch9-review-590-base"])
def test_owned_targets_pin_libpq_destination(monkeypatch, raw):
    from batch9_bootstrap_fixture import owned_database as guard
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)
    engine = Mock(return_value=object())
    monkeypatch.setattr(guard, "create_engine", engine)
    assert guard.owned_engine(raw) is engine.return_value
    target, = engine.call_args.args
    options = engine.call_args.kwargs["connect_args"]
    assert options["host"] == options["hostaddr"] == "127.0.0.1"
    assert options["port"] == target.port
    assert options["dbname"] == target.database
    assert options["user"] == target.username and options["password"] == target.password
    assert "service" not in options and options["sslmode"] == "disable"


def test_receipt_verifier_rejects_source_drift(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys
    root = tmp_path / "root"
    here = root / "evidence"
    here.mkdir(parents=True)
    source = root / "source.py"
    source.write_text("print('owned receipt control')\n")
    output = subprocess.check_output([sys.executable, str(source)])
    (here / "control.txt").write_bytes(output)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = {"generated_by": "source.py", "generator_sha256": sha(source),
               "source_sha256": {"source.py": sha(source)}, "exit_code": 0,
               "verdict": "PASSED", "output_sha256": sha(here / "control.txt")}
    (here / "control.json").write_text(json.dumps(receipt))
    (here / "historical-provenance.json").write_text(json.dumps({"receipts": {}, "spec_raw": []}))
    verifier = load(EVIDENCE / "verify_receipts.py", "receipt_verifier_safety")
    assert verifier.verify(here, root)["current_source_bound_receipts"] == 1
    # Preserve a generator; source binding must independently catch drift.
    generator = root / "generator.py"
    generator.write_bytes(source.read_bytes())
    receipt["generated_by"] = "generator.py"
    (here / "control.json").write_text(json.dumps(receipt))
    source.write_text("print('different source')\n")
    with pytest.raises(AssertionError, match="Current source mismatch"):
        verifier.verify(here, root)


def test_receipt_verifier_refuses_removed_historical_output(tmp_path):
    import hashlib
    import json
    root = tmp_path / "root"
    here = root / "evidence"
    here.mkdir(parents=True)
    generator = root / "generator.py"
    generator.write_text("print('historical fixture')\n")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    data = {"generated_by": "generator.py", "generator_sha256": sha(generator),
            "source_sha256": {"generator.py": sha(generator)}, "exit_code": 0,
            "verdict": "PASSED", "output_sha256": hashlib.sha256(b'fixture\n').hexdigest()}
    path = here / "baseline.json"
    path.write_text(json.dumps(data))
    (here / "historical-provenance.json").write_text(json.dumps({"receipts": {"baseline.json": {
        "receipt_sha256": sha(path), "status": "HISTORICAL_ONLY", "source_sha256": data["source_sha256"]}}, "spec_raw": []}))
    verifier = load(EVIDENCE / "verify_receipts.py", "receipt_verifier_missing_output")
    with pytest.raises(FileNotFoundError):
        verifier.verify(here, root)


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("mutation", ["source", "output", "verdict"])
def test_receipt_verifier_retains_integrity_checks_under_optimization(tmp_path, optimized, mutation):
    import hashlib
    import json
    import subprocess
    import sys
    root = tmp_path / "root"
    here = root / "evidence"
    here.mkdir(parents=True)
    generator = root / "generator.py"
    source = root / "source.py"
    generator.write_text("# owned generator\n")
    source.write_text("# owned source\n")
    output = here / "control.txt"
    output.write_text("owned child output\n")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    data = {"generated_by": "generator.py", "generator_sha256": sha(generator),
            "source_sha256": {"source.py": sha(source)}, "exit_code": 0,
            "verdict": "PASSED", "output_sha256": sha(output)}
    (here / "historical-provenance.json").write_text(json.dumps({"receipts": {}, "spec_raw": []}))
    receipt = here / "control.json"
    receipt.write_text(json.dumps(data))
    code = ("import importlib.util, pathlib, sys; "
            "s=importlib.util.spec_from_file_location('owned_verifier',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "print(m.verify(pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3])))")
    command = [sys.executable, *(["-O"] if optimized else []), "-c", code,
               str(EVIDENCE / "verify_receipts.py"), str(here), str(root)]
    baseline = subprocess.run(command, text=True, capture_output=True, timeout=30)
    assert baseline.returncode == 0, baseline.stderr
    if mutation == "source":
        source.write_text("# changed source\n")
    elif mutation == "output":
        output.write_text("changed output\n")
    else:
        data["verdict"] = "FAILED"
        receipt.write_text(json.dumps(data))
    changed = subprocess.run(command, text=True, capture_output=True, timeout=30)
    assert changed.returncode != 0, changed.stdout + changed.stderr
