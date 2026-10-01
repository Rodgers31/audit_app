"""#400: retired identity padding must not republish findings or sourced zero."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import main
from database import get_db
from models import (
    Audit, Base, Country, DocumentStatus, DocumentType, Entity, EntityType,
    Extraction, FiscalPeriod, Severity, SourceDocument,
)
from services.publication_gate import (
    backfill_publishable_audits, count_withheld_audits, count_withheld_by_reason,
    publishable_audit_criterion, retired_audit_fixture_criterion,
)


@pytest.fixture(params=("sqlite", "postgresql"))
def origin_db(request, db_session):
    """Actual JSONB in an owned schema; SQLite also stays in the default suite."""
    if request.param == "sqlite":
        db = db_session
        yield db
        return
    url = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to disposable local PostgreSQL")
    if make_url(url).host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Retired-origin tests require disposable local PostgreSQL")
    schema = f"round7_s2_origin_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine)() as db:
            yield db
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def origin_case(origin_db, monkeypatch):
    db = origin_db
    country = Country(iso_code="KEN", name="Kenya", currency="KES",
                      timezone="Africa/Nairobi", default_locale="en_KE")
    db.add(country)
    db.flush()
    entity = Entity(country_id=country.id, type=EntityType.COUNTY,
                    canonical_name="Mombasa County", slug="mombasa-county", meta={"code": "001"})
    period = FiscalPeriod(country_id=country.id, label="FY2024/25",
                          start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30))
    # ID 1836 is deliberately retained; identity policy is not an ID blacklist.
    doc = SourceDocument(id=1836, country_id=country.id, publisher="Synthetic OAG",
                         title="Synthetic cited report", url="https://example.invalid/audit.pdf",
                         fetch_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
                         doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE)
    db.add_all([entity, period, doc])
    db.flush()
    audit = Audit(entity_id=entity.id, period_id=period.id, source_document_id=doc.id,
                  page_ref="p.7", finding_text="Synthetic cited finding", severity=Severity.WARNING,
                  amount=Decimal("0"), audit_year=2024, query_type="Irregular Expenditure",
                  provenance={"reference": "LOCAL-S2-ONLY"})
    db.add(audit)
    db.commit()

    def test_db():
        # main readers close their Session via a context manager; use a separate
        # reader on the fixture connection so the writer objects stay attached.
        with sessionmaker(bind=db.connection())() as reader:
            yield reader

    monkeypatch.setattr(main, "get_db", test_db)
    previous = main.app.dependency_overrides.copy()
    main.app.dependency_overrides[get_db] = test_db
    client = TestClient(main.app, raise_server_exceptions=False)

    def read(path):
        main.clear_all_caches()
        response = client.get(path)
        assert response.status_code == 200, response.text
        return response.json()

    try:
        yield db, doc, audit, entity, read
    finally:
        main.app.dependency_overrides = previous
        main.clear_all_caches()


@pytest.mark.parametrize("marker,retired", [
    ("oag_audit_data.json", True),
    (" oag_audit_data.json ", True),
    ("\toag_audit_data.json\t", True),
    ("\noag_audit_data.json\r\n", True),
    ("\f\voag_audit_data.json\v\f", True),
    ("oag_national_audit_data.json", True),
    (" \t\noag_national_audit_data.json\r\f\v ", True),
    # Filenames/dataset identifiers are case-sensitive; no arbitrary substring retirement.
    ("OAG_AUDIT_DATA.JSON", False),
    ("official-oag_audit_data.json", False),
    ("https://example.invalid/oag_audit_data.json", False),
    ("oag_ audit_data.json", False),
    (None, False), ("", False), (" \t\n", False),
    (True, False), (0, False), ([], False), ({}, False),
    (["oag_audit_data.json"], False), ({"name": "oag_audit_data.json"}, False),
    ("oag_county_volume", False), ("oag_blue_book", False),
])
def test_retired_marker_cannot_publish_sourced_zero_through_real_consumers(origin_case, marker, retired):
    db, doc, audit, entity, read = origin_case
    doc.meta = {"source": marker}
    db.commit()
    expected = 0 if retired else 1
    stats = read("/api/v1/audits/statistics")
    assert stats["total_findings"] == stats["counties_audited"] == expected
    assert stats["total_amount_flagged"] == (None if retired else 0)
    assert db.query(Audit).filter(retired_audit_fixture_criterion()).count() == int(retired)
    assert db.query(Audit).filter(publishable_audit_criterion()).count() == expected
    assert read("/api/v1/audit/findings")["total"] == expected
    assert read("/api/v1/audit/summary")["total_findings"] == expected
    trends = read("/api/v1/audit/trends")
    assert trends["findings_per_year"] == ({"2024": 1} if not retired else {})
    assert trends["amount_per_year"].get("2024") == (None if retired else 0)
    for path in (
        f"/api/v1/counties/{entity.id}/money-flow?year=FY2024%2F25",
        "/api/v1/money-flow/all-counties?year=FY2024%2F25",
        "/api/v1/audit/money-flow/national?year=FY2024%2F25",
    ):
        body = read(path)
        if isinstance(body, list):
            body = next(row for row in body if row["county_id"] == entity.id)
        flagged = next(stage for stage in body["stages"] if stage["stage"] == "Flagged")
        assert flagged["amount"] == (None if retired else 0)
        assert body["audit_amount_coverage"]["total_findings"] == expected
    assert count_withheld_audits(db) == 0
    assert sum(count_withheld_by_reason(db).values()) == 0
    backfill_publishable_audits(db)
    db.refresh(audit)
    assert audit.publishable is (not retired)
    assert audit.quarantine_reason == ("retired_legacy_fixture" if retired else None)
    assert db.query(Audit).count() == 1
    db.refresh(doc)
    assert doc.meta == {"source": marker}


@pytest.mark.parametrize("meta", [None, {}, [], "oag_audit_data.json", True, 42])
def test_metadata_shape_is_not_a_retired_identity(origin_case, meta):
    db, doc, _, _, read = origin_case
    doc.meta = meta
    db.commit()
    assert db.query(Audit).filter(retired_audit_fixture_criterion()).count() == 0
    assert read("/api/v1/audits/statistics")["total_amount_flagged"] == 0


def test_real_extraction_on_retired_origin_preserves_citation_positive_and_zero(origin_case):
    db, doc, fixture, entity, read = origin_case
    doc.meta = {"source": "\t oag_national_audit_data.json\n"}
    ext = Extraction(source_document_id=doc.id, extractor="oag_blue_book", page_number=8,
                     extracted_json={"finding_text": "Synthetic extracted finding", "pdf_page": 8})
    db.add(ext)
    db.flush()
    for amount in (Decimal("5.25"), Decimal("0"), None):
        db.add(Audit(entity_id=entity.id, period_id=fixture.period_id, source_document_id=doc.id,
                     extraction_id=ext.id, page_ref="p.8", severity=Severity.WARNING,
                     finding_text="Synthetic extracted finding", audit_year=2024, amount=amount))
    db.commit()
    data = read("/api/v1/audits/statistics")
    assert data["total_findings"] == 3
    assert data["total_amount_flagged"] == 5.25
    assert data["findings_with_amount"] == 2
    assert data["findings_without_amount"] == 1
    items = read("/api/v1/audit/findings")["items"]
    assert {item["page_ref"] for item in items} == {"p.8"}
    assert {item["source_document_url"] for item in items} == {doc.url + "#page=8"}
    backfill_publishable_audits(db)
    db.refresh(fixture)
    assert fixture.publishable is False
    assert fixture.quarantine_reason == "retired_legacy_fixture"
    assert db.query(Audit).count() == 4
    assert count_withheld_audits(db) == 0


@pytest.mark.parametrize("container", ["dict", "list"])
@pytest.mark.parametrize("dataset,publishable", [
    ("oag-audit-aq0001", False), (" \toag-audit-aq0001\n", False),
    ("oag_blue_book", True), ("official-oag-audit-aq0001", True),
    (None, True), (False, True), ([], True), ({}, True),
])
def test_python_display_guard_retains_typed_dataset_identity(container, dataset, publishable):
    entry = {"dataset_id": dataset, "data_quality": "official"}
    provenance = entry if container == "dict" else [entry]
    assert main._audit_is_display_grade(SimpleNamespace(provenance=provenance)) is publishable


def test_python_guard_reaches_real_county_signal(origin_case):
    from services.county_financial_health import county_audit_signals
    db, doc, audit, entity, read = origin_case
    doc.meta = {"source": "oag_blue_book", "extraction_stats": {"volume_kind": "executives"}}
    audit.provenance = {"dataset_id": " \toag-audit-aq0001\n", "data_quality": "official"}
    db.commit()
    signals = county_audit_signals(db, [entity.id], display_grade=main._audit_is_display_grade)
    assert signals[entity.id]["absent_reason"] == "no_publishable_audit_signal"
    assert read(f"/api/v1/counties/{entity.id}/comprehensive")["audit"]["findings_count"] == 0
    audit.provenance = {"dataset_id": "oag_blue_book", "data_quality": "official"}
    db.commit()
    assert county_audit_signals(db, [entity.id], display_grade=main._audit_is_display_grade)[entity.id]["source_url"] == doc.url
    result = read(f"/api/v1/counties/{entity.id}/comprehensive")["audit"]
    assert result["findings_count"] == 1
    assert result["findings"][0]["source_url"] == doc.url + "#page=7"


@pytest.mark.parametrize("quality", ["fixture", " Fixture ", "\tSyNtHeTiC\n", "modelled", " demo\r"])
def test_python_quality_marker_cannot_republish_retired_rows(quality):
    assert main._audit_is_display_grade(SimpleNamespace(provenance={"data_quality": quality})) is False


def test_statistics_query_count_does_not_grow_with_padded_fixtures(origin_case):
    db, doc, audit, entity, read = origin_case
    doc.meta = {"source": " oag_audit_data.json "}
    db.commit()
    queries = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            queries.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        first = read("/api/v1/audits/statistics")
        initial = len(queries)
        assert initial > 0
        for _ in range(30):
            db.add(Audit(entity_id=entity.id, period_id=audit.period_id,
                         source_document_id=doc.id, page_ref="p.7",
                         finding_text="Synthetic retired finding", severity=Severity.WARNING,
                         amount=Decimal("0")))
        db.commit()
        queries.clear()
        final = read("/api/v1/audits/statistics")
        assert first["total_findings"] == final["total_findings"] == 0
        assert len(queries) == initial
    finally:
        event.remove(bind, "before_cursor_execute", capture)
