"""``source_document_url`` on ``/api/v1/audit/findings`` must be a link to the
document, never one assembled from an internal key.

The endpoint preferred ``Audit.external_reference`` over the joined
``source_documents.url`` and, when the reference was not a URL, pasted it onto
``https://www.oagkenya.go.ke/wp-content/uploads/``. The loader writes keys like
``OAG-BB-2024/2025-V2091-P11`` there, and all 2,311 production findings carry
one, so every "source" link on the site pointed at a path that does not exist.
Verified 2026-09-26: production finding 1715 published
``https://www.oagkenya.go.ke/wp-content/uploads/OAG-BB-2024/2025-V2091-P11``
and that URL returns 404.
"""

from datetime import datetime, timezone

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

OAG_KEY = "OAG-BB-2024/2025-V2091-P11"
DOC_URL = (
    "https://www.oagkenya.go.ke/wp-content/uploads/2025/12/Blue-Book-2024-2025.pdf"
)


@pytest.fixture()
def county(db_session, seed_country):
    db_session.add(
        FiscalPeriod(
            id=700,
            country_id=seed_country.id,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
    )
    entity = Entity(
        id=700,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nakuru County",
        slug="nakuru-source-url",
    )
    db_session.add(entity)
    db_session.commit()
    return entity


def _finding(db_session, seed_country, county, doc_url, external_reference):
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Office of the Auditor-General",
        title="Blue Book FY2024/25",
        url=doc_url,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        Audit(
            entity_id=county.id,
            period_id=700,
            source_document_id=doc.id,
            finding_text="Expenditure could not be confirmed.",
            severity=Severity.CRITICAL,
            status="published_report",
            audit_year=2024,
            page_ref="p.11",
            external_reference=external_reference,
        )
    )
    db_session.commit()


def _source_urls(client):
    items = client.get("/api/v1/audit/findings").json()["items"]
    assert len(items) == 1, "the fixture finding must pass the publication gate"
    return items[0]["source_document_url"]


def test_internal_key_is_not_turned_into_a_url(
    client, db_session, seed_country, county
):
    """The production shape. Old code: the fabricated wp-content/uploads URL."""
    _finding(db_session, seed_country, county, DOC_URL, OAG_KEY)
    assert _source_urls(client) == DOC_URL + "#page=11"


def test_document_url_outranks_a_linkable_reference(
    client, db_session, seed_country, county
):
    """The document the finding was extracted from is the citation."""
    _finding(db_session, seed_country, county, DOC_URL, "https://example.org/other.pdf")
    assert _source_urls(client) == DOC_URL + "#page=11"


def test_linkable_reference_is_used_when_the_document_url_is_not_a_link(
    client, db_session, seed_country, county
):
    """The control for the fallback: an http(s) reference still comes through."""
    ref = "https://www.oagkenya.go.ke/wp-content/uploads/2025/12/Nakuru.pdf"
    _finding(db_session, seed_country, county, "fixture://oag/blue-book", ref)
    assert _source_urls(client) == ref + "#page=11"


def test_no_url_is_published_when_nothing_is_a_link(
    client, db_session, seed_country, county
):
    """Neither value opens in a browser, so the honest answer is None — not a
    URL built from the key. Old code published the fabricated one here too."""
    _finding(db_session, seed_country, county, "fixture://oag/blue-book", OAG_KEY)
    assert _source_urls(client) is None


def test_finding_keeps_auditee_separate_from_county(
    client, db_session, seed_country, county
):
    from models import Extraction

    _finding(db_session, seed_country, county, DOC_URL, OAG_KEY)
    audit = db_session.query(Audit).one()
    ext = Extraction(
        source_document_id=audit.source_document_id,
        extractor="oag_county_volume",
        page_number=11,
        extracted_json={
            "entity_name": "County Assembly of Nakuru",
            "volume_kind": "assemblies",
        },
    )
    db_session.add(ext)
    db_session.flush()
    audit.extraction_id = ext.id
    db_session.commit()
    row = client.get("/api/v1/audit/findings").json()["items"][0]
    assert row["audited_entity_name"] == "County Assembly of Nakuru"
    assert row["county_name"] == "Nakuru County"
    assert row["county_slug"] == county.slug
    assert row["page_ref"] == "p.11"


@pytest.mark.parametrize(
    "page_ref,expected",
    [
        ("p.38", 38),
        ("pp.38-39", 38),
        ("page 38", 38),
        ("p.0", None),
        ("p.-3", None),
        ("p.38 garbage 73", None),
        (True, None),
        (float("nan"), None),
        ("38-12", None),
    ],
)
def test_page_locator_does_not_concatenate_or_invent_numbers(page_ref, expected):
    from services.audit_citations import page_number

    assert page_number(page_ref) == expected


def test_link_preserves_query_and_replaces_existing_page():
    from services.audit_citations import report_page_url

    assert (
        report_page_url(DOC_URL + "?download=1#page=2&zoom=100", "p.38")
        == DOC_URL + "?download=1#zoom=100&page=38"
    )
    assert (
        report_page_url("https://oagkenya.go.ke/reports/", "p.38")
        == "https://oagkenya.go.ke/reports/"
    )
    assert report_page_url("javascript:alert(1)", "p.38") is None


def test_county_detail_shows_the_same_institution_and_report_page(
    client, db_session, seed_country, county
):
    from models import Extraction

    _finding(db_session, seed_country, county, DOC_URL, OAG_KEY)
    a = db_session.query(Audit).one()
    x = Extraction(
        source_document_id=a.source_document_id,
        extractor="oag_county_volume",
        page_number=11,
        extracted_json={
            "entity_name": "County Assembly of Nakuru",
            "volume_kind": "assemblies",
            "title": "Unresolved prior year matters",
        },
    )
    db_session.add(x)
    db_session.flush()
    a.extraction_id = x.id
    db_session.commit()
    response = client.get(f"/api/v1/counties/{county.slug}/comprehensive")
    assert response.status_code == 200, response.text
    finding = response.json()["audit"]["findings"][0]
    assert finding.get("audited_entity_name") == "County Assembly of Nakuru"
    assert finding.get("source_url") == DOC_URL + "#page=11"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "entity_name": "County Assembly of Nairobi",
            "auditee": "County Assembly of Nakuru",
        },
        {
            "entity_name": "County Executive of Nairobi",
            "auditee": "County Executive of Nakuru",
        },
        {"entity_name": "County Assembly of Nairobi and County Executive of Nairobi"},
    ],
)
def test_conflicting_extracted_institutions_leave_the_label_unknown(payload):
    from services.audit_citations import audited_institution

    assert audited_institution(payload, county_name="Nairobi County") is None


def test_unbounded_page_integer_is_not_a_locator():
    from services.audit_citations import page_number

    assert page_number("9" * 5000) is None
