"""County audit list citations from synthetic published findings."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Severity,
    SourceDocument,
)


PDF_URL = "https://example.invalid/synthetic-county-audit.pdf?download=1#page=9&zoom=100"


def test_named_locators_are_conservative_and_stale_page_cleanup_is_opt_in():
    from services.audit_citations import citation_page, report_page_url

    assert citation_page(" Annex   VII ") == "Annex VII"
    assert citation_page("Appendix A") == "Appendix A"
    for invalid in ("p.0", "p.-3", "p.38 garbage 73", "Annex 0", "garbage"):
        assert citation_page(invalid) is None
    assert report_page_url(PDF_URL, None) == PDF_URL
    assert report_page_url(PDF_URL, None, clear_stale_page=True) == (
        "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100"
    )
    assert report_page_url(
        "https://example.invalid/report.pdf#Page=9&zoom=100&view=Fit",
        "Annex VII",
        clear_stale_page=True,
    ) == "https://example.invalid/report.pdf#zoom=100&view=Fit"


def test_county_audit_list_carries_only_parseable_pages_and_preserves_gates(
    client, db_session, seed_country, seed_fiscal_period
):
    nairobi = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-citation-fixture",
    )
    other = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kisumu County",
        slug="kisumu-citation-fixture",
    )
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic OAG",
        title="Synthetic Nairobi audit FY2024/25",
        url=PDF_URL,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add_all([nairobi, other, doc])
    db_session.flush()

    cases = [
        ("single", "p. 2", nairobi),
        ("range", "pp. 38-39", nairobi),
        ("annex", "Annex VII", nairobi),
        ("malformed", "p.38 garbage 73", nairobi),
        ("negative", "p.-3", nairobi),
        ("zero", "p.0", nairobi),
        ("absent", None, nairobi),
        ("blank", "   ", nairobi),
        ("other institution", "p.4", other),
    ]
    for label, page_ref, entity in cases:
        db_session.add(
            Audit(
                entity_id=entity.id,
                period_id=seed_fiscal_period.id,
                finding_text=f"Synthetic {label} finding",
                severity=Severity.WARNING,
                source_document_id=doc.id,
                page_ref=page_ref,
            )
        )
    db_session.commit()

    response = client.get("/api/v1/counties/001/audits/list?year=FY2024/25")
    assert response.status_code == 200, response.text
    data = response.json()
    by_label = {
        item["description"].removeprefix("Synthetic ").removesuffix(" finding"): item
        for item in data["items"]
    }
    assert data["total"] == 6
    assert set(by_label) == {"single", "range", "annex", "malformed", "negative", "zero"}
    assert all(item["fiscal_year"] == "FY2024/25" for item in by_label.values())

    for label, expected_page in (("single", 2), ("range", 38)):
        source = by_label[label]["source"]
        assert source["title"] == doc.title
        assert source["url"] == PDF_URL
        assert source["page"] == expected_page
        assert source["page_url"] == (
            "https://example.invalid/synthetic-county-audit.pdf?download=1"
            f"#zoom=100&page={expected_page}"
        )
    assert by_label["annex"]["source"]["page"] == "Annex VII"
    assert by_label["annex"]["source"]["page_url"] == (
        "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100"
    )
    for label in ("malformed", "negative", "zero"):
        source = by_label[label]["source"]
        assert source["page"] is None
        assert source["page_url"] == (
            "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100"
        )

    wrong_period = client.get("/api/v1/counties/001/audits/list?year=FY2023/24")
    assert wrong_period.status_code == 200
    assert wrong_period.json()["items"] == []


def test_county_audit_list_fallback_uses_the_same_page_contract(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "DATABASE_AVAILABLE", False)
    monkeypatch.setattr(
        main.InternalAPIClient,
        "get_county_audit_queries",
        AsyncMock(return_value=[
            {
                "id": "range",
                "description": "Synthetic range finding",
                "source": {"title": "Synthetic PDF", "url": PDF_URL, "page": "pp. 38–39"},
            },
            {
                "id": "invalid",
                "description": "Synthetic invalid page",
                "source": {"title": "Synthetic PDF", "url": PDF_URL, "page": "p.-3"},
            },
            {
                "id": "annex",
                "description": "Synthetic annex locator",
                "source": {"title": "Synthetic PDF", "url": PDF_URL, "page": "Annex VII"},
            },
            {
                "id": "unsafe-url",
                "description": "Synthetic invalid URL",
                "source": {"title": "Synthetic PDF", "url": "javascript:alert(1)", "page": "p. 2"},
            },
        ]),
    )

    response = client.get("/api/v1/counties/001/audits/list")
    assert response.status_code == 200, response.text
    items = {item["id"]: item["source"] for item in response.json()["items"]}
    assert items["range"]["page"] == 38
    assert items["range"]["page_url"] == (
        "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100&page=38"
    )
    assert items["annex"]["page"] == "Annex VII"
    assert items["annex"]["page_url"] == (
        "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100"
    )
    assert items["invalid"]["page"] is None
    assert items["invalid"]["page_url"] == (
        "https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100"
    )
    assert items["unsafe-url"]["page"] == 2
    assert items["unsafe-url"]["page_url"] is None
