"""Controlled transfer estimates for actual ingestion writes, never provider billing."""

from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import asdict
import copy
import json

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import MultipleResultsFound

from models import Audit, DocumentType, EconomicIndicator, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.audits import loader
from seeding.domains.economic_indicators.parser import parse_economic_payload
from seeding.domains.economic_indicators.writer import persist_economic_records
from seeding.extractors.oag_blue_book import EXTRACTOR_ID, source_hash_of
from seeding.types import DomainRunContext


CTX = DomainRunContext(since=None, dry_run=False)
LARGE = "synthetic-unused-diagnostic-" + "x" * 65536


@contextmanager
def selected_values(db, table):
    """Replay SELECTs on the owned SQLite fixture, including discarded values.

    Count UTF-8 strings of raw DBAPI values, including stored JSON encoding.
    Excludes protocol/TLS/pooler overhead; not provider wire/billing bytes.
    """
    assert db.get_bind().dialect.name == "sqlite"
    samples = []

    def capture(conn, cursor, statement, parameters, context, many):
        flat = " ".join(statement.split()).lower()
        if not flat.startswith("select " + table + "."):
            return
        raw = conn.connection.driver_connection.cursor()
        try:
            raw.execute(statement, parameters)
            rows = raw.fetchall()
            samples.append({
                "rows": len(rows),
                "columns": [c[0] for c in raw.description],
                "bytes": sum(len(str(v).encode("utf-8")) for r in rows for v in r if v is not None),
            })
        finally:
            raw.close()

    engine = db.get_bind().engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield samples
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def report(name, samples):
    result = {"queries": len(samples), "rows": sum(s["rows"] for s in samples),
              "selected_value_bytes_estimate": sum(s["bytes"] for s in samples)}
    print("TRANSFER_RECEIPT " + json.dumps({"operation": name, **result}, sort_keys=True))
    return result


def snapshot(db, model):
    return [{a.key: copy.deepcopy(getattr(row, a.key)) for a in inspect(model).column_attrs}
            for row in db.scalars(select(model).order_by(model.id))]


def records(n=20):
    return parse_economic_payload([{
        "indicator_type": "synthetic_growth", "date": f"{2000+i}-12-31",
        "value": "0" if i == 0 else "1.23456789", "unit": "percent",
        "source_url": f"https://example.invalid/economic-{i % 2}",
        "publisher": "Declared publisher", "measure": "synthetic controlled measure",
    } for i in range(n)])


def source(db, country, url, *, audit=False):
    row = SourceDocument(country_id=country.id, publisher="Old publisher",
        title="Retained title", url=url, fetch_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT if audit else DocumentType.REPORT,
        meta={"retained": LARGE}, md5="a" * 32)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("existing", [False, True])
def test_economic_source_transfer_is_bounded_by_distinct_urls(db_session, seed_country, existing):
    db = db_session
    batch = records()
    if existing:
        for url in sorted({r.source_url for r in batch}):
            source(db, seed_country, url)
    db.flush()
    db.expire_all()
    with selected_values(db, "source_documents") as samples:
        stats = persist_economic_records(db, iter(batch), SeedingSettings(), CTX)
        db.flush()
    values = report("economic_existing" if existing else "economic_new", samples)
    assert asdict(stats) == {"processed": 20, "created": 20, "updated": 0, "skipped": 0, "errors": []}
    sources = list(db.scalars(select(SourceDocument).order_by(SourceDocument.url)))
    assert len(sources) == 2 and all(s.publisher == "Declared publisher" for s in sources)
    if existing:
        assert all(s.meta == {"retained": LARGE} and s.title == "Retained title" for s in sources)
    facts = list(db.scalars(select(EconomicIndicator).order_by(EconomicIndicator.indicator_date)))
    assert len(facts) == 20 and facts[0].value == 0
    assert all(f.source_document_id in {s.id for s in sources} for f in facts)
    assert values["queries"] == 2
    assert values["rows"] == (2 if existing else 0)
    assert values["selected_value_bytes_estimate"] < 1024
    assert not any("metadata" in c or "file_path" in c for s in samples for c in s["columns"])


def test_source_declarations_and_invocation_scope_survive_rollback(db_session, seed_country):
    db = db_session
    batch = records(4)
    for r in batch:
        r.source_url = batch[0].source_url
    batch[1].metadata.pop("publisher")
    batch[2].metadata["publisher"] = "Later publisher"
    batch[3].metadata.pop("publisher")
    with db.begin_nested() as transaction:
        persist_economic_records(db, batch, SeedingSettings(), CTX)
        db.flush()
        assert db.scalar(select(SourceDocument)).publisher == "Later publisher"
        transaction.rollback()
    assert db.scalar(select(SourceDocument)) is None
    with selected_values(db, "source_documents") as samples:
        result = persist_economic_records(db, batch, SeedingSettings(), CTX)
        db.flush()
    assert result.created == 4 and len(samples) == 1
    saved = db.scalar(select(SourceDocument))
    saved.publisher = "External publisher"
    db.flush()
    with selected_values(db, "source_documents") as samples:
        persist_economic_records(db, [batch[-1]], SeedingSettings(), CTX)
    assert len(samples) == 1 and saved.publisher == "External publisher"


def test_duplicate_economic_source_identity_is_still_refused(db_session, seed_country):
    r = records(1)[0]
    source(db_session, seed_country, r.source_url)
    source(db_session, seed_country, r.source_url)
    with pytest.raises(MultipleResultsFound):
        persist_economic_records(db_session, [r], SeedingSettings(), CTX)
    assert db_session.query(EconomicIndicator).count() == 0


@pytest.mark.parametrize("existing", [False, True])
def test_economic_flush_failure_rolls_back_source_and_next_call_resolves_again(db_session, seed_country, existing):
    db = db_session
    batch = records(2)
    if existing:
        for r in batch:
            source(db, seed_country, r.source_url)
    before = snapshot(db, SourceDocument)
    engine = db.get_bind().engine

    def fail_fact_insert(conn, cursor, statement, parameters, context, many):
        if statement.lower().startswith("insert into economic_indicators"):
            raise RuntimeError("injected isolated fact flush failure")

    event.listen(engine, "before_cursor_execute", fail_fact_insert)
    try:
        with pytest.raises(RuntimeError, match="isolated fact flush failure"):
            with db.begin_nested():
                persist_economic_records(db, batch, SeedingSettings(), CTX)
                db.flush()
    finally:
        event.remove(engine, "before_cursor_execute", fail_fact_insert)
    assert snapshot(db, SourceDocument) == before
    assert db.query(EconomicIndicator).count() == 0
    with selected_values(db, "source_documents") as samples:
        stats = persist_economic_records(db, batch, SeedingSettings(), CTX)
        db.flush()
    assert stats.created == 2 and len(samples) == 2


def audit_fixture(db, country):
    doc = source(db, country, "https://example.invalid/annual-audit.pdf", audit=True)
    for i in range(2):
        db.add(Extraction(source_document_id=doc.id, extractor=EXTRACTOR_ID,
            confidence="0.9", page_number=i+2, extracted_json={
                "schema": "oag_blue_book/v1", "entity_name": "Synthetic Ministry",
                "fiscal_year": "2024/2025", "finding_text": f"Synthetic finding {i}",
                "severity": "INFO", "amounts": [0] if i == 0 else [], "vote": 1071,
                "paragraph_no": i+1, "pdf_page": i+2, "diagnostic": LARGE,
            }))
    db.flush()
    assert loader.load_blue_book_extractions(db, doc, SeedingSettings(), CTX).created == 2
    for a in db.scalars(select(Audit)):
        a.management_response = LARGE
        a.recommended_action = LARGE
    db.flush()
    return doc


@pytest.mark.parametrize("confirming", [False, True])
def test_loader_omits_unused_audit_columns_without_changing_rows(db_session, seed_country, monkeypatch, confirming):
    db = db_session
    doc = audit_fixture(db, seed_country)
    before = snapshot(db, Audit)
    if confirming:
        original = loader._audits_by_extraction_id
        def confirmed_miss(*args):
            original(*args)
            return {}
        monkeypatch.setattr(loader, "_audits_by_extraction_id", confirmed_miss)
    db.expire_all()
    with selected_values(db, "audits") as samples, selected_values(db, "extractions") as extraction_samples:
        stats = loader.load_blue_book_extractions(db, doc, SeedingSettings(), CTX)
    values = report("audit_confirming" if confirming else "audit_unchanged", samples)
    report("extractions_for_confirming" if confirming else "extractions_for_unchanged", extraction_samples)
    assert stats.processed == 2 and stats.created == stats.updated == stats.skipped == 0
    assert stats.errors == [] and snapshot(db, Audit) == before
    assert values["queries"] == (3 if confirming else 1)
    assert values["rows"] == (4 if confirming else 2)
    assert values["selected_value_bytes_estimate"] < 10000
    assert not any("management_response" in c or "recommended_action" in c for s in samples for c in s["columns"])


def test_loader_retains_full_payload_hash_and_repairs_missing_rows(db_session, seed_country):
    db = db_session
    doc = audit_fixture(db, seed_country)
    extraction = db.scalar(select(Extraction).order_by(Extraction.id))
    changed = dict(extraction.extracted_json)
    changed["diagnostic"] = "changed whole-payload evidence"
    changed["finding_text"] = "Changed synthetic finding"
    extraction.extracted_json = changed
    victim = db.scalar(select(Audit).where(Audit.extraction_id != extraction.id))
    db.delete(victim)
    db.flush()
    stats = loader.load_blue_book_extractions(db, doc, SeedingSettings(), CTX)
    assert stats.updated == stats.created == 1
    repaired = db.scalar(select(Audit).where(Audit.extraction_id == extraction.id))
    assert repaired.source_hash == source_hash_of(changed)
    assert repaired.finding_text == changed["finding_text"] and repaired.amount == 0
    assert db.query(Audit).count() == 2
