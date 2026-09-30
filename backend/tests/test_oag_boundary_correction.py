"""Execute #379 correction, failure and recovery against disposable PostgreSQL.

Real-source replay uses OAG_TEST_SOURCE_PDF (11MB, never bundled in the repo).
Stored audit/extraction shapes were captured READ ONLY; other rows are synthetic.
"""
import copy
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text, select, update
from sqlalchemy.engine import make_url

from models import Base, Country

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("oag_boundary_correction", ROOT / "scripts/verification/oag_boundary_correction.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
MANIFEST = Path(__file__).parent / "fixtures/oag_boundary_reviewed_manifest.json"
CAPTURED = Path(__file__).parent / "fixtures/oag_boundary_correction_before.json"


@pytest.fixture
def clone():
    url = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    pdf = os.environ.get("OAG_TEST_SOURCE_PDF")
    if not url or not pdf:
        pytest.skip("requires disposable PostgreSQL and exact OAG_TEST_SOURCE_PDF")
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost", "::1"} or not parsed.database.startswith("codex_oag_"):
        pytest.fail("must use loopback codex_oag_* disposable database")
    schema = "boundary_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    # Current production retains this extra column. Reflection must preserve
    # it even though the current ORM does not model it.
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audits ADD COLUMN validation_warnings jsonb"))
        c.execute(Country.__table__.insert().values(id=1, iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en_KE"))
        tables = tool.tables_for(c)
        seen = {k: set() for k in tables}
        for item in json.loads(CAPTURED.read_bytes())["rows"]:
            for part, name in (("source", "source_documents"), ("entity", "entities"),
                               ("period", "fiscal_periods"), ("extraction", "extractions"), ("audit", "audits")):
                row = copy.deepcopy(item[part])
                if row["id"] in seen[name]:
                    continue
                seen[name].add(row["id"])
                for column in tables[name].columns:
                    if column.type.python_type is datetime and row.get(column.name):
                        row[column.name] = datetime.fromisoformat(row[column.name])
                c.execute(tables[name].insert().values(**row))
        # An unrelated stored finding and extraction must be preserved too.
        spare = copy.deepcopy(item["extraction"])
        spare["id"] = 90000
        spare["extracted_json"]["paragraph_no"] = 9999
        spare["created_at"] = datetime.fromisoformat(spare["created_at"])
        c.execute(tables["extractions"].insert().values(**spare))
        audit = copy.deepcopy(item["audit"])
        audit.update(id=90000, extraction_id=90000, external_reference="unrelated-control",
                     validation_warnings={"retained": ["control"]}, finding_text="unrelated positive control")
        audit["created_at"] = datetime.fromisoformat(audit["created_at"])
        c.execute(tables["audits"].insert().values(**audit))
    yield engine, Path(pdf), tables
    engine.dispose()
    with admin.begin() as c:
        c.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()


def inventory(engine, tables):
    with engine.connect() as c:
        return {name: tool.normalized([dict(r) for r in c.execute(select(t).order_by(t.c.id)).mappings()])
                for name, t in tables.items()}


def prepared(clone):
    engine, pdf, _ = clone
    return tool.run(engine, pdf, MANIFEST)


def test_commit_dry_run_recovery_and_future_loader_agree(clone, tmp_path):
    from sqlalchemy.orm import Session
    from models import SourceDocument
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    from seeding.domains.audits.loader import load_blue_book_extractions

    engine, pdf, tables = clone
    before = inventory(engine, tables)
    plan = prepared(clone)
    assert plan == prepared(clone), "plan must be deterministic"
    sha = tool.digest(plan)
    assert tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=sha)["outcome"] == "read_only_dry_run"
    assert inventory(engine, tables) == before
    receipt = tmp_path / "recovery.json"
    assert tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=sha,
                    commit=True, receipt_path=receipt)["outcome"] == "committed"
    after = inventory(engine, tables)
    for name in ("source_documents", "entities", "fiscal_periods"):
        assert before[name] == after[name]
    assert before["audits"][-1] == after["audits"][-1]
    assert before["extractions"][-1] == after["extractions"][-1]
    for item in plan["after"]:
        a, x = item["audit"], item["extraction"]
        assert a["finding_text"] == x["extracted_json"]["finding_text"]
        assert a["source_hash"] == tool.source_hash_of(x["extracted_json"])
    # Exercise the actual nightly writer on corrected authoritative payloads.
    with Session(engine) as session:
        doc = session.get(SourceDocument, 2541)
        stats = load_blue_book_extractions(session, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert stats.created == 0
        # The synthetic spare differs, so don't commit this writer rehearsal.
        assert all(session.get(tool.Audit, r["audit"]["id"]).finding_text == r["audit"]["finding_text"]
                   for r in plan["after"])
        session.rollback()
    assert tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=sha,
                    recover=True)["outcome"] == "read_only_dry_run"
    tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=sha, commit=True,
             recover=True, receipt_path=tmp_path / "rollback.json")
    assert inventory(engine, tables) == before
    assert json.loads(receipt.read_bytes())["plan_sha256"] == sha


@pytest.mark.parametrize("table,field,value", [
    ("audits", "finding_text", "drift"), ("audits", "external_reference", "wrong"),
    ("audits", "source_hash", "wrong"), ("audits", "audit_year", 2024),
    ("audits", "page_ref", "p.169"), ("audits", "amount", 0),
    ("audits", "publishable", False), ("audits", "management_response", "new evidence"),
    ("audits", "provenance", [{"source_url": "https://example.org/wrong.pdf"}]),
    ("extractions", "page_number", 169), ("source_documents", "md5", "wrong"),
    ("source_documents", "url", "https://example.org/other.pdf"),
    ("entities", "canonical_name", "Another County"), ("fiscal_periods", "label", "FY2023/24"),
])
def test_atomic_drift_refusal(clone, tmp_path, table, field, value):
    engine, pdf, tables = clone
    plan = prepared(clone)
    item = plan["before"][0]
    part = {"audits": "audit", "extractions": "extraction", "source_documents": "source", "entities": "entity", "fiscal_periods": "period"}[table]
    with engine.begin() as c:
        c.execute(update(tables[table]).where(tables[table].c.id == item[part]["id"]).values(**{field: value}))
    before = inventory(engine, tables)
    with pytest.raises(ValueError, match="drift"):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan),
                 commit=True, receipt_path=tmp_path / "refused.json")
    assert inventory(engine, tables) == before
    assert not (tmp_path / "refused.json").exists()


def test_payload_drift_missing_row_and_duplicate_refused(clone, tmp_path):
    engine, pdf, tables = clone
    plan = prepared(clone)
    x = copy.deepcopy(plan["before"][0]["extraction"]["extracted_json"])
    x["auditee"] = "County Executive of Narok"
    with engine.begin() as c:
        c.execute(update(tables["extractions"]).where(tables["extractions"].c.id == 6023).values(extracted_json=x))
    before = inventory(engine, tables)
    with pytest.raises(ValueError, match="drift"):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan), commit=True, receipt_path=tmp_path / "refused.json")
    assert inventory(engine, tables) == before
    with engine.begin() as c:
        c.execute(update(tables["audits"]).where(tables["audits"].c.id == 90000).values(external_reference=plan["before"][0]["audit"]["external_reference"]))
    with pytest.raises(ValueError, match="duplicate"):
        tool.run(engine, pdf, MANIFEST)


def test_dml_failure_rolls_back_both_copies(clone, tmp_path):
    engine, pdf, tables = clone
    plan = prepared(clone)
    before = inventory(engine, tables)
    with engine.begin() as c:
        c.execute(text("CREATE FUNCTION refuse_second() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id=5679 THEN RAISE EXCEPTION 'synthetic persistence failure'; END IF; RETURN NEW; END $$"))
        c.execute(text("CREATE TRIGGER refuse_second BEFORE UPDATE ON audits FOR EACH ROW EXECUTE FUNCTION refuse_second()"))
    with pytest.raises(Exception, match="synthetic persistence failure"):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan), commit=True, receipt_path=tmp_path / "intent.json")
    assert inventory(engine, tables) == before
    assert (tmp_path / "intent.json").exists(), "recovery must precede DML"


def test_bad_plan_and_receipt_failure_refused(clone, tmp_path):
    engine, pdf, tables = clone
    plan = prepared(clone)
    before = inventory(engine, tables)
    tampered = copy.deepcopy(plan)
    tampered["after"][0]["audit"]["amount"] = "0"
    with pytest.raises(ValueError, match="drift"):
        tool.run(engine, pdf, MANIFEST, plan=tampered, expected_plan_sha256=tool.digest(tampered), commit=True, receipt_path=tmp_path / "bad.json")
    with pytest.raises(FileNotFoundError):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan), commit=True, receipt_path=tmp_path / "absent/receipt.json")
    assert inventory(engine, tables) == before


@pytest.mark.parametrize("part,field,value", [
    ("audit", "publishable", 1), ("audit", "period_id", True), ("audit", "id", 5545.0),
])
def test_plan_numeric_type_drift_refused(clone, tmp_path, part, field, value):
    engine, pdf, tables = clone
    plan = prepared(clone)
    plan["after"][0][part][field] = value
    before = inventory(engine, tables)
    with pytest.raises(ValueError, match="drift"):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan),
                 commit=True, receipt_path=tmp_path / "bad.json")
    assert inventory(engine, tables) == before


def test_stored_payload_numeric_type_drift_refused(clone):
    engine, pdf, tables = clone
    plan = prepared(clone)
    payload = copy.deepcopy(plan["before"][0]["extraction"]["extracted_json"])
    payload["pdf_page"] = 168.0
    with engine.begin() as c:
        c.execute(update(tables["extractions"]).where(tables["extractions"].c.id == 6023).values(extracted_json=payload))
        c.execute(update(tables["audits"]).where(tables["audits"].c.id == 5545).values(source_hash=tool.source_hash_of(payload)))
    with pytest.raises(ValueError, match="drift"):
        tool.run(engine, pdf, MANIFEST)


def test_trigger_cannot_change_unrelated_json_types(clone, tmp_path):
    engine, pdf, tables = clone
    with engine.begin() as c:
        c.execute(update(tables["audits"]).where(tables["audits"].c.id == 5545).values(validation_warnings={"control": True}))
    plan = prepared(clone)
    before = inventory(engine, tables)
    with engine.begin() as c:
        c.execute(text("CREATE FUNCTION change_extra_column() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id=5545 THEN NEW.validation_warnings=jsonb_build_object('control',1); END IF; RETURN NEW; END $$"))
        c.execute(text("CREATE TRIGGER change_extra_column BEFORE UPDATE ON audits FOR EACH ROW EXECUTE FUNCTION change_extra_column()"))
    with pytest.raises(ValueError, match="postwrite snapshot drift"):
        tool.run(engine, pdf, MANIFEST, plan=plan, expected_plan_sha256=tool.digest(plan),
                 commit=True, receipt_path=tmp_path / "intent.json")
    assert inventory(engine, tables) == before


@pytest.mark.parametrize("content", [b"", b"{}", b"malformed"])
def test_wrong_source_and_manifest_refused(tmp_path, content):
    file = tmp_path / "wrong"
    file.write_bytes(content)
    with pytest.raises(ValueError, match="manifest"):
        tool.validate_source(file, file)
    with pytest.raises(ValueError, match="PDF"):
        tool.validate_source(file, MANIFEST)
    with pytest.raises(FileNotFoundError):
        tool.validate_source(tmp_path / "absent", MANIFEST)


@pytest.mark.parametrize("plan", [None, {}, {"before": [], "after": []}, True])
def test_direct_commit_cannot_bypass_guards(clone, plan):
    engine, pdf, _ = clone
    with pytest.raises(ValueError):
        tool.run(engine, pdf, MANIFEST, plan=plan, commit=True)
