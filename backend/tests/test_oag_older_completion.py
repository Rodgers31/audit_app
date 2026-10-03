"""Owned PostgreSQL operator controls; source proof is explicitly synthetic here.

Actual 701-page Tesseract source proof is recorded separately in Round21 docs.
Never use an application/default database URL for these disposable fixtures.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

spec = importlib.util.spec_from_file_location(
    "round21_operator", Path(__file__).resolve().parents[2] / "tools/oag_older_completion.py")
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)


@pytest.fixture
def operation(monkeypatch):
    url = os.environ.get("ROUND21_TEST_DATABASE_URL")
    if not url:
        pytest.skip("explicit owned ROUND21_TEST_DATABASE_URL required")
    engine = create_engine(url)
    if engine.url.host != "127.0.0.1" or engine.url.database != "round21_oag":
        raise ValueError("only dedicated owned round21_oag PostgreSQL permitted")
    with engine.begin() as c:
        for table in op.TABLES:
            c.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
            if table == "source_documents":
                c.execute(text(f"CREATE TABLE {table}(id integer primary key,metadata jsonb,title text,url text,md5 text)"))
            elif table == "extractions":
                c.execute(text(f"CREATE TABLE {table}(id integer primary key,source_document_id integer,extracted_json jsonb,page_number integer,confidence numeric,extractor text)"))
            elif table == "audits":
                c.execute(text(f"CREATE TABLE {table}(id integer primary key,source_document_id integer,extraction_id integer,finding_text text)"))
            else:
                c.execute(text(f"CREATE TABLE {table}(id integer primary key,value text)"))
                c.execute(text(f"INSERT INTO {table} VALUES (1,'preserved')"))
        for sid in op.IDS:
            payload = {"vote": 1, "paragraph_no": 1, "title": "Source finding", "finding_text": "Source finding",
                       "pdf_page": 1, "extraction_method": "pdfplumber"}
            c.execute(text("INSERT INTO source_documents VALUES (:id,CAST(:metadata AS jsonb),'Exact source','https://official.example/older.pdf','pinned')"),
                      {"id": sid, "metadata": json.dumps({"last_extraction_attempt": {"status": "partial", "error": "historical"}, "other": "preserved"})})
            c.execute(text("INSERT INTO extractions VALUES (:id,:id,CAST(:payload AS jsonb),1,0.9,'oag_blue_book')"),
                      {"id": sid, "payload": json.dumps(payload)})
            c.execute(text("INSERT INTO audits VALUES (:id,:id,:id,'Source finding')"), {"id": sid})
    with engine.connect() as c:
        sources = op.rows(c, "source_documents")
        exts = op.rows(c, "extractions", source=True)
        audits = op.rows(c, "audits", source=True)
        authority = {"reader_sha256": "synthetic", "protected": op.protection(c),
                     "sequences": op.sequences(c), "sources": []}
        proof = {"schema": "oag_older_complete_source_proof/v1", "reader_sha256": "synthetic", "sources": []}
        for source in sources:
            sid = source["id"]
            es = [r for r in exts if r["source_document_id"] == sid]
            ars = [r for r in audits if r["source_document_id"] == sid]
            after = {**source["metadata"], "extractor_version": 3, "last_extraction_attempt": {"status": "complete"}}
            authority["sources"].append({"source_id": sid, "source_before": source,
                "metadata_after_existing_writer": after, "extraction_rows_before_sha256": op.sha(es),
                "audit_rows_before_sha256": op.sha(ars), "extraction_ids": [r["id"] for r in es],
                "audit_ids": [r["id"] for r in ars], "candidate_payloads_sha256": op.sha([r["extracted_json"] for r in es]),
                "pdf_sha256": "synthetic", "page_count": 1})
            proof["sources"].append({"source_id": sid, "payloads": [r["extracted_json"] for r in es],
                                     "pdf_sha256": "synthetic", "pages": 1})
    monkeypatch.setattr(op, "manifest", lambda: copy.deepcopy(authority))
    monkeypatch.setattr(op, "source_proof", lambda *args: copy.deepcopy(proof))
    try:
        yield engine, authority, proof
    finally:
        engine.dispose()


def invoke(operation, **kwargs):
    return op.run(operation[0], {2395: "synthetic", 2396: "synthetic"}, **kwargs)


def test_default_forward_executes_exact_transition_then_rolls_back(operation):
    engine, authority, _ = operation
    result = invoke(operation)
    assert result["outcome"] == "rolled_back"
    assert result["before"] != result["after"]
    with engine.connect() as c:
        assert op.same(op.rows(c, "source_documents"), result["before"])
        assert op.same(op.protection(c), authority["protected"])


def test_legitimate_forward_and_guarded_inverse_preserve_every_other_field(operation, tmp_path):
    engine, authority, _ = operation
    forward = invoke(operation, commit=True, expected_manifest_sha256=op.MANIFEST_SHA256,
                     receipt_path=tmp_path / "forward.json")
    assert forward["outcome"] == "committed"
    inverse = invoke(operation, inverse=True, recovery=forward,
                     expected_recovery_sha256=op.sha(forward))
    assert inverse["outcome"] == "rolled_back"
    with engine.connect() as c:
        assert op.same(op.rows(c, "source_documents"), forward["after"])
    inverse = invoke(operation, inverse=True, commit=True, recovery=forward,
                     expected_recovery_sha256=op.sha(forward), expected_manifest_sha256=op.MANIFEST_SHA256,
                     receipt_path=tmp_path / "inverse.json")
    assert inverse["outcome"] == "committed"
    with engine.connect() as c:
        assert op.same(op.rows(c, "source_documents"), forward["before"])
        assert op.same(op.protection(c), authority["protected"])


@pytest.mark.parametrize("sql", [
    "UPDATE source_documents SET title='drift' WHERE id=2395",
    "UPDATE source_documents SET metadata=metadata || '{\"other\":\"drift\"}' WHERE id=2396",
    "UPDATE extractions SET confidence=0.6 WHERE id=2395",
    "UPDATE extractions SET page_number=2 WHERE id=2395",
    "UPDATE audits SET extraction_id=99 WHERE id=2396",
    "INSERT INTO extractions SELECT 999,2395,extracted_json,page_number,confidence,extractor FROM extractions WHERE id=2395",
    "UPDATE entities SET value='drift' WHERE id=1",
    "INSERT INTO source_documents VALUES (999,'{}','unexpected','unexpected','unexpected')",
])
def test_source_cohort_or_unrelated_drift_refuses_before_any_metadata_write(operation, sql):
    engine, _, _ = operation
    with engine.begin() as c:
        c.execute(text(sql))
    with engine.connect() as c:
        before = op.rows(c, "source_documents")
    with pytest.raises(ValueError):
        invoke(operation)
    with engine.connect() as c:
        assert op.same(op.rows(c, "source_documents"), before)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "wrong_hash", "bool_page", "changed_payload"])
def test_malformed_or_changed_proof_cannot_mark_sources_complete(operation, mutation):
    _, _, proof = operation
    source = proof["sources"][0]
    if mutation == "empty":
        source["payloads"] = []
    elif mutation == "duplicate":
        proof["sources"][1] = copy.deepcopy(source)
    elif mutation == "wrong_hash":
        source["pdf_sha256"] = "wrong"
    elif mutation == "bool_page":
        source["pages"] = True
    else:
        source["payloads"][0]["finding_text"] = "changed"
    with pytest.raises(ValueError):
        invoke(operation)


def test_intent_receipt_path_collision_refuses_before_write(operation, tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("existing")
    with pytest.raises(FileExistsError):
        invoke(operation, commit=True, expected_manifest_sha256=op.MANIFEST_SHA256, receipt_path=path)
    assert path.read_text() == "existing"


def test_inverse_refuses_intervening_unrelated_drift_even_rehashed_receipt(operation, tmp_path):
    engine, _, _ = operation
    forward = invoke(operation, commit=True, expected_manifest_sha256=op.MANIFEST_SHA256,
                     receipt_path=tmp_path / "forward.json")
    with engine.begin() as c:
        c.execute(text("UPDATE entities SET value='later writer'"))
    with engine.connect() as c:
        forged = copy.deepcopy(forward)
        forged["protected_after"] = op.protection(c)
    with pytest.raises(ValueError, match="inverse unrelated protection drift"):
        invoke(operation, inverse=True, recovery=forged, expected_recovery_sha256=op.sha(forged))


def test_sequence_drift_refuses_before_metadata_write(operation):
    engine, authority, _ = operation
    with engine.begin() as c:
        c.execute(text("CREATE SEQUENCE round21_control_seq START 10"))
    try:
        with engine.connect() as c:
            authority["sequences"] = op.sequences(c)
            before = op.rows(c, "source_documents")
        with engine.begin() as c:
            c.execute(text("SELECT nextval('round21_control_seq')"))
        with pytest.raises(ValueError, match="sequence drift"):
            invoke(operation)
        with engine.connect() as c:
            assert op.same(op.rows(c, "source_documents"), before)
    finally:
        with engine.begin() as c:
            c.execute(text("DROP SEQUENCE round21_control_seq"))


def test_trigger_side_effect_refuses_postimage_and_rolls_back_every_write(operation):
    engine, authority, _ = operation
    with engine.begin() as c:
        c.execute(text("CREATE OR REPLACE FUNCTION round21_side_effect() RETURNS trigger "
                       "LANGUAGE plpgsql AS $$BEGIN UPDATE entities SET value='trigger drift'; RETURN NEW; END$$"))
        c.execute(text("CREATE TRIGGER round21_side_effect AFTER UPDATE ON source_documents "
                       "FOR EACH ROW EXECUTE FUNCTION round21_side_effect()"))
    with pytest.raises(ValueError, match="postwrite full-image/protection drift"):
        invoke(operation)
    with engine.connect() as c:
        assert op.same(op.protection(c), authority["protected"])


def test_production_proof_does_not_accept_missing_or_replaced_pdf():
    authority = op.manifest()
    with pytest.raises(ValueError, match="both exact older PDFs"):
        op.source_proof(authority, {})


def test_direct_proof_refuses_recomputed_caller_source_authority():
    authority = op.manifest()
    authority["sources"][0]["pdf_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="exact reviewed authority"):
        op.source_proof(authority, {})
