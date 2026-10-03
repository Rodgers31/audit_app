"""Coverage must transfer finding evidence without repeating shared metadata."""
import copy
import json

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from models import Audit, Entity, Extraction, SourceDocument
from seeding.county_audit_coverage import county_audit_coverage_receipt, coverage_verdict
from seeding.domains.audits import observation as obs
from test_audits_listing_observation import adopted, html_client, job, SELECTED
from test_county_audit_coverage_gate import db


@pytest.fixture
def large_coverage(adopted):
    session, meta = adopted
    current_job = job(session, meta)
    current_job.started_at = current_job.started_at.replace(tzinfo=None)
    session.flush()
    original_receipt = county_audit_coverage_receipt(session)
    # Large unrelated context is valid evidence and must still be available to
    # the verifier, but sending it once per finding multiplies result egress.
    for county in session.query(Entity).all():
        county.meta = {**(county.meta or {}), "large_context": "C" * 20_000}
    for source in session.query(SourceDocument).all():
        source.meta = {**source.meta, "large_context": "D" * 30_000}
    session.flush()
    meta = copy.deepcopy(current_job.meta)
    discovery, _ = obs.observe_listing(html_client())
    meta["oag_county_observation"]["adopted"] = [
        obs.verify_adopted_volume(session, volume)
        for volume in discovery.volumes() if volume.url not in SELECTED
    ]
    current_job.meta = meta
    session.flush()
    return session, original_receipt


def _finding_selects(session, action):
    statements = []

    def capture(state):
        if state.is_select:
            entities = [d.get("entity") for d in state.statement.column_descriptions]
            if Audit in entities and Extraction in entities:
                statements.append(state.statement)

    event.listen(session, "do_orm_execute", capture)
    try:
        result = action()
    finally:
        event.remove(session, "do_orm_execute", capture)
    return result, statements


def _result_bytes(connection, statement):
    rows = connection.execute(statement).all()
    return rows, sum(len(json.dumps(list(row), default=str).encode()) for row in rows)


def test_complete_coverage_does_not_repeat_large_county_and_source_metadata(large_coverage, record_property):
    session, original = large_coverage
    receipt, statements = _finding_selects(
        session, lambda: county_audit_coverage_receipt(session)
    )
    assert receipt == original
    assert len(receipt["cells"]) == 376 and coverage_verdict(receipt)[0] == "OK"
    assert len(statements) == 1
    actual = statements[0]
    legacy = actual.with_only_columns(
        Audit, Entity, Extraction, SourceDocument, maintain_column_froms=True
    )
    # Run the actual emitted finding query and a full-projection control with
    # exactly its joins, filters and parameters, rather than timing a mock.
    connection = session.connection()
    actual_rows, actual_bytes = _result_bytes(connection, actual)
    legacy_rows, legacy_bytes = _result_bytes(connection, legacy)
    assert len(actual_rows) == len(legacy_rows) == 376
    record_property("projected_result_bytes", actual_bytes)
    record_property("legacy_result_bytes", legacy_bytes)
    assert actual_bytes * 20 < legacy_bytes, (
        f"shared metadata repeated across findings: {actual_bytes} vs {legacy_bytes} bytes"
    )
    actual_sql = str(actual.compile(dialect=postgresql.dialect()))
    legacy_sql = str(legacy.compile(dialect=postgresql.dialect()))
    assert actual_sql.partition("\nFROM ")[2] == legacy_sql.partition("\nFROM ")[2]
    assert "entities.metadata" not in actual_sql.partition("\nFROM ")[0]
    assert "source_documents.metadata" not in actual_sql.partition("\nFROM ")[0]


@pytest.mark.parametrize("mutation", ["partial", "failed", "wrong_md5", "wrong_county", "wrong_page", "withheld"])
def test_large_shared_metadata_keeps_source_and_attribution_refusals(large_coverage, mutation):
    session, original = large_coverage
    source = session.query(SourceDocument).filter(SourceDocument.url.in_(SELECTED)).first()
    audit = session.query(Audit).filter_by(source_document_id=source.id).first()
    if mutation == "partial":
        source.meta = {**source.meta, "extraction_stats": {**source.meta["extraction_stats"], "partial": True}}
    elif mutation == "failed":
        from models import DocumentStatus
        source.status = DocumentStatus.FAILED
    elif mutation == "wrong_md5":
        source.md5 = "0" * 32
    elif mutation == "wrong_county":
        extraction = session.get(Extraction, audit.extraction_id)
        extraction.extracted_json = {**extraction.extracted_json, "auditee": "County Executive of Elsewhere"}
    elif mutation == "wrong_page":
        audit.page_ref = "p.2"
    else:
        audit.publishable = False
    session.flush()
    receipt = county_audit_coverage_receipt(session)
    assert coverage_verdict(original)[0] == "OK"
    assert coverage_verdict(receipt)[0] != "OK"
