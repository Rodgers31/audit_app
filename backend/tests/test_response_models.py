"""
Tests for Pydantic response models defined in main.py.

Validates serialization/deserialization of the API response schemas.
"""

import pytest


def test_country_response_serialization():
    """CountryResponse should serialize correctly."""
    from main import CountryResponse

    cr = CountryResponse(
        id=1,
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        summary={"total_entities": 47, "transparency_score": 75.5},
    )
    data = cr.model_dump()
    assert data["name"] == "Kenya"
    assert data["summary"]["total_entities"] == 47


def test_entity_response_serialization():
    """EntityResponse should handle optional fields."""
    from main import EntityResponse

    er = EntityResponse(
        id=1,
        canonical_name="Ministry of Health",
        type="ministry",
        slug="moh",
        meta={},
    )
    data = er.model_dump()
    assert data["canonical_name"] == "Ministry of Health"
    assert data["financial_summary"] is None
    assert data["audit_findings_count"] == 0


def test_entity_detail_response():
    """EntityDetailResponse should contain nested structures."""
    from main import EntityDetailResponse

    edr = EntityDetailResponse(
        entity={"id": 1, "name": "Treasury"},
        financial_time_series=[{"year": 2024, "amount": 1e12}],
        recent_budget_lines=[],
        audit_findings=[],
        source_documents=[],
    )
    data = edr.model_dump()
    assert len(data["financial_time_series"]) == 1


def test_budget_line_response():
    """BudgetLineResponse should handle currency and amounts."""
    from main import BudgetLineResponse

    blr = BudgetLineResponse(
        id=1,
        category="Health",
        allocated_amount=5_000_000,
        actual_spent=3_200_000,
        currency="KES",
        entity_id=10,
    )
    data = blr.model_dump()
    assert data["currency"] == "KES"
    assert data["allocated_amount"] == 5_000_000


def test_search_response():
    """SearchResponse should paginate results."""
    from main import SearchResponse

    sr = SearchResponse(
        results=[{"id": 1, "title": "Budget Report"}],
        total_count=1,
        page=1,
        per_page=20,
    )
    data = sr.model_dump()
    assert data["total_count"] == 1


def test_audit_list_response():
    """AuditListResponse paginates audit items."""
    from main import AuditListItem, AuditListResponse

    items = [
        AuditListItem(
            id=1,
            description="Missing funds",
            severity="critical",
            source={"publisher": "OAG"},
        )
    ]
    alr = AuditListResponse(total=1, page=1, limit=20, items=items)
    data = alr.model_dump()
    assert data["items"][0]["severity"] == "critical"


def test_document_response():
    """DocumentResponse should serialize document metadata."""
    from main import DocumentResponse

    dr = DocumentResponse(
        id=1,
        title="FY2024/25 Budget Estimates",
        url="https://treasury.go.ke",
        doc_type="budget",
        meta={},
    )
    data = dr.model_dump()
    assert data["title"] == "FY2024/25 Budget Estimates"
