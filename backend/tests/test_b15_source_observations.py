"""Committed PostgreSQL evidence seam; stored fixture proofs are not live acceptance."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models import (BudgetLine, Country, DocumentStatus, DocumentType, Entity, EntityType,
                    Extraction, FiscalPeriod, IngestionJob, IngestionStatus, SourceDocument)
from seeding.source_observations import SourceObservationUnavailable, read_county_budget_observation, read_county_budget_record_ids
from services.figure_qualification import row_identities

from b15_etl_fixture import postgres


@pytest.fixture(scope="module")
def pg():
    with postgres() as value:
        yield value


@pytest.fixture
def stored(pg, tmp_path):
    factory, engine = pg
    with factory.begin() as db:
        country = db.query(Country).filter_by(iso_code="KEN").first()
        if country is None:
            country = Country(iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en")
            db.add(country)
            db.flush()
        entity = Entity(country_id=country.id, type=EntityType.COUNTY, slug="test-" + uuid4().hex, canonical_name="Nairobi County")
        period = db.query(FiscalPeriod).filter_by(country_id=country.id, label="FY2025/26").first()
        if period is None:
            period = FiscalPeriod(country_id=country.id, label="FY2025/26",
                                  start_date=datetime(2025,7,1), end_date=datetime(2026,6,30))
        doc = SourceDocument(country_id=country.id, publisher="Controller of Budget", title="Sanitized PDF control",
                             url="https://cob.go.ke/inert-control.pdf", fetch_date=datetime(2026,8,1),
                             doc_type=DocumentType.BUDGET, status=DocumentStatus.AVAILABLE,
                             meta={"publication_date": "2026-07-31", "data_quality": "official"})
        job = IngestionJob(domain="counties_budget", status=IngestionStatus.COMPLETED, dry_run=False,
                           started_at=datetime(2026, 8, 2), finished_at=datetime.now(timezone.utc),
                           errors=[], meta={"source_mode": "live"})
        db.add_all([entity, period, doc, job]); db.flush()
        row = BudgetLine(entity_id=entity.id, period_id=period.id, category="Total", line_type="total",
                         actual_spent=Decimal(0), currency="KES", source_document_id=doc.id, publishable=True)
        db.add(row); db.flush()
        identity = row_identities("budget_lines", row, {entity.id: entity}, {period.id: period})["actual_spent"].model_dump()
        # Independent stored input/observation is re-read from retained fixture bytes.
        body = json.dumps({"identity": identity, "value": "0"}).encode()
        path = tmp_path / "source-control"; path.write_bytes(body)
        parsed = json.loads(path.read_bytes())
        digest = sha256(path.read_bytes()).hexdigest()
        locator = {"page": 7, "table": "5.2", "cell": "actual expenditure"}
        receipt = {"source_kind": "pdf", "status": 200, "content_type": "application/pdf",
                   "request_url": doc.url, "acquired_at": "2026-08-01T00:00:00Z", "parser_version": "inert-v1",
                   "digest": digest, "byte_size": len(body), "storage_key": str(path),
                   "byte_check": {"status": "matched", "sha256": digest, "checked_at": "2026-08-01T00:00:01Z"},
                   "observations": [{"identity": parsed["identity"], "raw_value": parsed["value"], "raw_unit": "KES", "locator": locator}]}
        extraction = Extraction(source_document_id=doc.id, extractor="pdf-receipt-v1", extracted_json={"response_receipt": receipt})
        db.add(extraction); db.flush()
        date_proof = {'publication_date':'2026-07-31','digest':digest,'request_url':doc.url,
                      'locator':{'page':1,'text_span':'Publication date: 2026-07-31'}}
        dated = Extraction(source_document_id=doc.id, extractor='cob-publication-date-v1',
            extracted_json={'response_receipt':{'digest':digest,'request_url':doc.url,
                'observations':[date_proof],'byte_check':{'status':'matched'}}})
        db.add(dated); db.flush()
        doc.meta = {**doc.meta,'publication_date_evidence':{**date_proof,'extraction_id':dated.id}}
        evidence = {"version": 1, "source_kind": "pdf", "identity": identity,
                    "receipt": {"extraction_id": extraction.id, "digest": digest}, "raw_value": "0", "raw_unit": "KES",
                    "value": "0", "unit": "KES", "locator": locator, "transformation": {"operation": "identity"},
                    "checks": dict.fromkeys(("identity", "value", "transport", "bytes", "locator"), True),
                    "reconciliation": {"status": "matched"}}
        row.provenance = [{"ingestion_job_id": job.id, "data_quality": "official", "artifact_sha256": digest, "source_evidence": [evidence]}]
        ids = row.id, job.id, doc.id, extraction.id
    return factory, ids


def test_exact_committed_zero_and_wire_identity(stored):
    factory, (record, job, doc, _) = stored
    observation = read_county_budget_observation(factory, record_id=record, ingestion_id=job)
    assert observation["committed"] is True and observation["fixture"] is False
    assert observation["source_key"] == f"budget_lines:{record}:actual_spent"
    assert observation["evidence_version"] == job
    fact = observation["facts"][0]
    assert Decimal(fact["value"]) == 0 and fact["classification"] == "actual"
    assert fact["source_document_id"] == doc
    assert fact["published_on"] == "2026-07-31"
    assert fact["unit"] == "KES" and fact["scale"] == "units"


@pytest.mark.parametrize("mutation", ["dry_run", "failed", "running", "fixture", "errors", "quarantine", "modelled", "unknown_lineage", "unlinked_evidence", "changed_value", "missing_receipt", "wrong_hash", "unknown_date", "future_date", "naive_time", "wrong_host", "missing_row", "unpublishable", "same_host_wrong_path", "future_acquisition", "future_verification", "check_after_job", "future_job", "inverted_job"])
def test_ineligible_records_never_become_observations(stored, mutation):
    factory, (record, job_id, doc_id, receipt_id) = stored
    with factory.begin() as db:
        job, row, doc, extraction = db.get(IngestionJob, job_id), db.get(BudgetLine, record), db.get(SourceDocument, doc_id), db.get(Extraction, receipt_id)
        if mutation == "dry_run": job.dry_run = True
        elif mutation in ("failed", "running"): job.status = IngestionStatus[mutation.upper()]
        elif mutation == "fixture": job.meta = {"source_mode": "fixture"}
        elif mutation == "errors": job.errors = ["quarantined input"]
        elif mutation == "quarantine": row.quarantine_reason = "refused"
        elif mutation == "unpublishable": row.publishable = False
        elif mutation == "modelled": doc.meta = {**doc.meta, "data_quality": "modelled"}
        elif mutation == "changed_value": row.actual_spent = Decimal(1)
        elif mutation == "missing_receipt": extraction.extracted_json = {}
        elif mutation == "unknown_date": doc.meta = {"data_quality": "official"}
        elif mutation == "future_date": doc.meta = {**doc.meta, "publication_date": "2027-01-01"}
        elif mutation == "wrong_host": doc.url = "https://example.invalid/report.pdf"
        elif mutation == "same_host_wrong_path": doc.url = "https://cob.go.ke/never-acquired.pdf"
        elif mutation == "future_job": job.finished_at = datetime(2099, 1, 1)
        elif mutation == "inverted_job": job.finished_at = datetime(2025, 1, 1)
        elif mutation == "missing_row": record = 2147483647
        elif mutation == "naive_time":
            extraction.extracted_json["response_receipt"]["acquired_at"] = "2026-08-01T00:00:00"
            flag_modified(extraction, "extracted_json")
        elif mutation in ("future_acquisition", "future_verification", "check_after_job"):
            receipt = extraction.extracted_json["response_receipt"]
            if mutation == "future_acquisition": receipt["acquired_at"] = "2099-08-01T00:00:00Z"
            receipt["byte_check"]["checked_at"] = "2099-08-01T00:00:01Z"
            if mutation == "check_after_job":
                job.started_at = datetime(2026, 8, 1)
                job.finished_at = datetime(2026, 8, 1, 0, 0, 0)
                receipt["byte_check"]["checked_at"] = "2026-08-01T00:00:01Z"
            flag_modified(extraction, "extracted_json")
        elif mutation in ("unknown_lineage", "wrong_hash", "unlinked_evidence"):
            if mutation == "unknown_lineage": row.provenance[0]["ingestion_job_id"] = job_id + 1
            elif mutation == "wrong_hash": row.provenance[0]["artifact_sha256"] = "a" * 64
            else:
                evidence = row.provenance[0].pop("source_evidence")
                row.provenance.append({"source_evidence": evidence})
            flag_modified(row, "provenance")
    with pytest.raises(SourceObservationUnavailable):
        read_county_budget_observation(factory, record_id=record, ingestion_id=job_id)


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 2147483648, 1.0, "1", float("nan"), float("inf")])
def test_bounds_before_factory(bad):
    def no_session():
        pytest.fail("invalid input must not open a database session")
    for args in ({"record_id": bad, "ingestion_id": 1}, {"record_id": 1, "ingestion_id": bad}):
        with pytest.raises(SourceObservationUnavailable):
            read_county_budget_observation(no_session, **args)


def test_reader_does_not_export_uncommitted_change(stored):
    factory, (record, job, _, _) = stored
    with factory() as writer:
        writer.get(BudgetLine, record).actual_spent = Decimal(999)
        writer.flush()
        out = read_county_budget_observation(factory, record_id=record, ingestion_id=job)
        assert Decimal(out["facts"][0]["value"]) == 0
        with pytest.raises(SourceObservationUnavailable, match="Fresh committed-reader"):
            read_county_budget_observation(lambda: writer, record_id=record, ingestion_id=job)
        assert writer.in_transaction()
        assert writer.get(BudgetLine, record).actual_spent == 999


def test_active_writer_refusal_does_not_rollback_callers_transaction():
    engine = create_engine("sqlite:///:memory:")
    try:
        with Session(engine) as writer:
            writer.execute(text("CREATE TABLE marker(value integer)"))
            writer.commit()
            writer.execute(text("INSERT INTO marker VALUES (1)"))
            with pytest.raises(SourceObservationUnavailable, match="Fresh committed-reader"):
                read_county_budget_observation(lambda: writer, record_id=1, ingestion_id=1)
            assert writer.in_transaction()
            assert writer.scalar(text("SELECT count(*) FROM marker")) == 1
    finally:
        engine.dispose()


def test_reader_refuses_preloaded_stale_identity_map(stored):
    factory, (record, job, _, _) = stored
    with factory(expire_on_commit=False) as cached:
        row = cached.get(BudgetLine, record)
        cached.commit()
        with factory.begin() as writer:
            writer.get(BudgetLine, record).actual_spent = Decimal(1)
        assert row.actual_spent == 0
        with pytest.raises(SourceObservationUnavailable, match="Fresh committed-reader"):
            read_county_budget_observation(lambda: cached, record_id=record, ingestion_id=job)
        assert row in cached


def test_selector_binds_exact_persisted_job_and_refuses_overflow(stored):
    factory, (record, job, doc, _) = stored
    assert read_county_budget_record_ids(factory, ingestion_id=job) == (record,)
    with factory.begin() as db:
        row = db.get(BudgetLine, record)
        common = dict(entity_id=row.entity_id, period_id=row.period_id, source_document_id=doc,
                      actual_spent=0, currency="KES", provenance=[{"ingestion_job_id": job}])
        db.add_all([BudgetLine(category=f"control_{n}", **common) for n in range(999)])
    assert len(read_county_budget_record_ids(factory, ingestion_id=job)) == 1000
    with factory.begin() as db:
        db.add(BudgetLine(category="control_overflow", **common))
    with pytest.raises(SourceObservationUnavailable, match="Bounded exact ingestion lineage"):
        read_county_budget_record_ids(factory, ingestion_id=job)


def test_selector_distinguishes_completed_empty_lineage_from_invalid_job(stored, monkeypatch):
    from seeding.generation_dispatch import dispatch_committed_generation
    factory, (record, job, _, _) = stored
    with factory.begin() as db:
        db.get(BudgetLine, record).provenance = [{"ingestion_job_id": True}]
    assert read_county_budget_record_ids(factory, ingestion_id=job) == ()
    monkeypatch.setenv("SOCIAL_GENERATION_HOOK_ENABLED", "true")
    out = dispatch_committed_generation(factory, domain="counties_budget", ingestion_id=job, dry_run=False)
    assert out["state"] == "completed" and out["reason"] == "no_new_record_lineage" and out["processed"] == 0
    with factory.begin() as db:
        db.get(IngestionJob, job).status = IngestionStatus.FAILED
    with pytest.raises(SourceObservationUnavailable):
        read_county_budget_record_ids(factory, ingestion_id=job)


def test_reader_limits_preserve_stricter_inherited_timeouts(pg):
    from seeding.source_observations import _read_limits
    from sqlalchemy.exc import DBAPIError
    factory, _ = pg
    with factory() as db:
        db.execute(text("SET LOCAL statement_timeout='50ms'"))
        db.execute(text("SET LOCAL lock_timeout='25ms'"))
        _read_limits(db)
        assert db.scalar(text("SHOW statement_timeout")) == "50ms"
        assert db.scalar(text("SHOW lock_timeout")) == "25ms"
        with pytest.raises(DBAPIError, match="statement timeout"):
            db.execute(text("SELECT pg_sleep(0.2)"))
    with factory() as db:
        db.execute(text("SET LOCAL statement_timeout=0"))
        db.execute(text("SET LOCAL lock_timeout=0"))
        _read_limits(db)
        assert db.scalar(text("SHOW statement_timeout")) == "5s"
        assert db.scalar(text("SHOW lock_timeout")) == "2s"
