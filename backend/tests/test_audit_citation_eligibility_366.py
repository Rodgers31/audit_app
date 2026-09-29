"""Issue #366: execute the audit publication gate on both database dialects."""

import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from models import (
    Audit, Base, Country, DocumentStatus, DocumentType, Entity, EntityType,
    FiscalPeriod, Severity, SourceDocument,
)
from services.audit_citations import citation_page, page_number, report_page_url, safe_source_url
from services.publication_gate import (
    _has_page_locator, backfill_publishable_audits, count_withheld_by_reason,
    file_source_provenance_failure,
    publishable_audit_criterion,
)


@pytest.fixture(params=("sqlite", "postgresql"))
def citation_session(request, db_session, seed_country, seed_fiscal_period):
    if request.param == "sqlite":
        yield db_session, seed_country.id, seed_fiscal_period.id
        return

    url = os.getenv("CITATION_TEST_POSTGRES_URL")
    if not url:
        candidate = os.getenv("DATABASE_URL", "")
        if candidate.startswith("postgresql"):
            url = candidate
    if not url:
        pytest.skip("PostgreSQL citation test needs CITATION_TEST_POSTGRES_URL")

    schema = f"citation_{uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        country = Country(iso_code="KEN", name="Kenya", currency="KES",
                          timezone="Africa/Nairobi", default_locale="en")
        session.add(country)
        session.flush()
        period = FiscalPeriod(country_id=country.id, label="FY2024/25",
                              start_date=datetime(2024, 7, 1),
                              end_date=datetime(2025, 6, 30))
        session.add(period)
        session.flush()
        yield session, country.id, period.id
    finally:
        if "session" in locals():
            session.close()
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_actual_publication_expression_matches_rendering_and_reasons(citation_session):
    db, country_id, period_id = citation_session
    entity = Entity(country_id=country_id, type=EntityType.COUNTY,
                    canonical_name="Synthetic County", slug="citation-366")
    db.add(entity)
    db.flush()

    good = "https://example.invalid/audit.pdf#page=9&zoom=100"
    cases = [
        ("p. 2", good, None),
        ("pp. 38–39", good, None),
        ("Annex VII", good, None),
        ("Schedule XL", good, None),
        ("Appendix MCMXCIV", good, None),
        ("p. 5", "http://example.invalid:8080/audit.pdf", None),
        ("p. 6", "https://example.invalid/audit%20report.pdf", None),
        ("p.0", good, "no_page_reference"),
        ("p.-3", good, "no_page_reference"),
        ("p.38 garbage 73", good, "no_page_reference"),
        ("pp. 39-38", good, "no_page_reference"),
        ("Annex IIV", good, "no_page_reference"),
        ("Annex VII\u00a0", good, "no_page_reference"),
        ("Annex K", good, "no_page_reference"),
        (None, good, "no_page_reference"),
        ("p. 2", "javascript:alert(1)", "source_document_has_invalid_url"),
        ("p. 2", "https://bad host/audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https://example.invalid:99999/audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https:///audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https://user:pass@example.invalid/audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https://example.invalid/audit.pdf\n", "source_document_has_invalid_url"),
        ("p. 2", "https://ı/audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https://K/audit.pdf", "source_document_has_invalid_url"),
        ("p. 2", "https://example.invalid/audit%zz.pdf", "source_document_has_invalid_url"),
        ("p. 2", None, "source_document_has_no_url"),
        ("p. 2", " \t\n", "source_document_has_no_url"),
    ]
    expected = {}
    for index, (locator, url, reason) in enumerate(cases):
        doc = SourceDocument(country_id=country_id, publisher="Synthetic OAG",
                             title=f"Synthetic report {index}", url=url,
                             fetch_date=datetime(2025, 1, 1),
                             doc_type=DocumentType.AUDIT,
                             status=DocumentStatus.AVAILABLE)
        db.add(doc)
        db.flush()
        row = Audit(entity_id=entity.id, period_id=period_id,
                    finding_text=f"Synthetic finding {index}",
                    severity=Severity.WARNING, source_document_id=doc.id,
                    page_ref=locator)
        db.add(row)
        db.flush()
        expected[row.id] = reason
        assert (citation_page(locator) is not None and safe_source_url(url)) is (reason is None)
        if url is not None and not safe_source_url(url):
            assert report_page_url(url, locator) is None
    db.commit()

    published = set(db.scalars(select(Audit.id).where(publishable_audit_criterion())))
    assert published == {row_id for row_id, reason in expected.items() if reason is None}
    reasons = count_withheld_by_reason(db)
    assert reasons == {
        "source_document_has_no_url": 2,
        "source_document_has_invalid_url": 9,
        "finding_text_unreadable_cid": 0,
        "no_page_reference": 8,
    }
    assert backfill_publishable_audits(db) == {"published": 7, "withheld": 19}
    db.expire_all()
    for row in db.scalars(select(Audit)):
        assert row.publishable is (expected[row.id] is None)
        assert row.quarantine_reason == expected[row.id]
    assert report_page_url(good, "Annex VII", clear_stale_page=True) == (
        "https://example.invalid/audit.pdf#zoom=100"
    )
    assert report_page_url(good, "pp. 38–39", clear_stale_page=True) == (
        "https://example.invalid/audit.pdf#zoom=100&page=38"
    )


def test_descriptive_pdf_references_keep_their_explicit_exception():
    # Fiscal and budget-line records can contain labeled PDF page citations;
    # an audit finding needs a direct locator that its UI can render.
    for value in ("PDF pp. 7", "PDF pp. 7, 9", "voted total PDF p.11; CFS summary PDF p.1193"):
        assert _has_page_locator(value, allow_descriptive=True)
        assert not _has_page_locator(value)
    assert not _has_page_locator("PDF pp. 0, 9", allow_descriptive=True)


@pytest.mark.parametrize(
    "locator,number,citation,has_locator",
    [
        (999_999_999, 999_999_999, 999_999_999, True),
        ("999999999", 999_999_999, 999_999_999, True),
        (1_000_000_000, None, None, False),
        ("1000000000", None, None, False),
        (True, None, None, False),
        (False, None, None, False),
        (0, None, None, False),
        (-1, None, None, False),
        ("0", None, None, False),
        ("-1", None, None, False),
        ("Annex VII", None, "Annex VII", True),
    ],
)
@pytest.mark.parametrize("surface", ("number", "citation", "gate", "url", "url_clear"))
def test_numeric_page_limit_is_the_same_for_integer_and_string_locators(
    locator, number, citation, has_locator, surface
):
    url = "https://example.invalid/audit.pdf#page=9&zoom=100"
    if surface == "number":
        assert page_number(locator) == number
    elif surface == "citation":
        assert citation_page(locator) == citation
    elif surface == "gate":
        assert _has_page_locator(locator) is has_locator
    elif surface == "url":
        assert report_page_url(url, locator) == (
            f"https://example.invalid/audit.pdf#zoom=100&page={number}"
            if number is not None else url
        )
    else:
        assert report_page_url(url, locator, clear_stale_page=True) == (
            f"https://example.invalid/audit.pdf#zoom=100&page={number}"
            if number is not None else "https://example.invalid/audit.pdf#zoom=100"
        )


def test_file_source_requires_a_safe_document_url_and_page():
    meta = {"source_url": "https://example.invalid/report.pdf", "page_ref": "p. 14"}
    assert file_source_provenance_failure(meta) is None
    for bad in ("javascript:alert(1)", "httpx://example.invalid/report.pdf",
                "https://example.invalid/report.pdf\n"):
        assert file_source_provenance_failure({**meta, "source_url": bad}) == "source_url_is_invalid"
