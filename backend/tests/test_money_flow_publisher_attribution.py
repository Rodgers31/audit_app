"""Money-flow attribution must follow the selected document, not row shape.

These are HTTP regressions using the shared SQLite fixtures. A Treasury Total
can establish an allocation; being a Total cannot turn its publisher into CoB.
"""
from datetime import datetime, timezone

import pytest
from models import BudgetLine, DocumentStatus, DocumentType, Entity, EntityType, SourceDocument


@pytest.fixture()
def published_county(db_session, seed_country, seed_fiscal_period):
    def add(*, entity_id=501, publisher="Kenya National Treasury", cob=False,
            allocation=100, spending=70):
        entity = Entity(
            id=entity_id,
            country_id=seed_country.id,
            canonical_name="Mombasa County" if entity_id == 501 else "Nairobi County",
            type=EntityType.COUNTY,
            slug="mombasa-county" if entity_id == 501 else "nairobi-county",
        )
        doc = SourceDocument(
            country_id=seed_country.id,
            publisher=publisher,
            title=("County Budget Implementation Review Report FY2024/25" if cob
                   else "FY2024/25 County Budget Estimates"),
            url=(f"https://cob.go.ke/reports/cbirr-{entity_id}.pdf" if cob
                 else f"https://treasury.go.ke/budgets/county-{entity_id}.pdf"),
            fetch_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
            doc_type=DocumentType.BUDGET,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add_all([entity, doc])
        db_session.flush()
        db_session.add(BudgetLine(
            entity_id=entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=allocation,
            actual_spent=spending,
            currency="KES",
            source_document_id=doc.id,
            page_ref="p.42",
        ))
        db_session.commit()
        return doc

    return add


def response_for(client, surface):
    path = {
        "county": "/api/v1/counties/501/money-flow?year=2024%2F25",
        "batch": "/api/v1/money-flow/all-counties?year=2024%2F25",
        "national": "/api/v1/audit/money-flow/national?year=2024%2F25",
    }[surface]
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    return next(row for row in body if row["county_id"] == 501) if surface == "batch" else body


def stage(body):
    return next(row for row in body["stages"] if row["stage"] == "Allocated")


@pytest.mark.parametrize("surface", ["county", "batch", "national"])
@pytest.mark.parametrize("allocation,spending", [(100, 70), (0, 0)])
def test_non_cob_total_keeps_its_amount_without_inventing_cob_attribution(
    client, published_county, surface, allocation, spending,
):
    doc = published_county(allocation=allocation, spending=spending)
    body = response_for(client, surface)
    allocated = stage(body)
    assert allocated["amount"] == allocation
    assert next(s for s in body["stages"] if s["stage"] == "Spent")["amount"] == spending
    assert body.get("budget_source") != "cob_cbirr"
    assert "controller of budget" not in (allocated.get("source") or "").lower()
    assert "cbirr" not in (allocated.get("source") or "").lower()
    if surface != "batch":
        assert body["source_document_url"] == doc.url
        assert allocated["source_doc"] == doc.url
    if surface == "county":
        assert body["source_document_title"] == doc.title


@pytest.mark.parametrize("surface", ["county", "batch", "national"])
def test_cob_document_remains_attributed_to_cob(client, published_county, surface):
    doc = published_county(publisher="Controller of Budget", cob=True)
    body = response_for(client, surface)
    allocated = stage(body)
    assert allocated["amount"] == 100
    assert body.get("budget_source") == "cob_cbirr"
    assert "Controller of Budget" in allocated["source"]
    if surface != "batch":
        assert body["source_document_url"] == doc.url


@pytest.mark.parametrize("surface", ["county", "batch", "national"])
@pytest.mark.parametrize("publisher,cob", [
    ("Controller of Budget", False),
    ("Kenya National Treasury", True),
])
def test_cbirr_attribution_needs_both_publisher_and_report_series(
    client, published_county, surface, publisher, cob,
):
    """A publisher alone, or a similar document title alone, is insufficient."""
    published_county(publisher=publisher, cob=cob)
    body = response_for(client, surface)
    assert stage(body)["amount"] == 100
    assert body.get("budget_source") != "cob_cbirr"
    assert stage(body).get("source") != "Controller of Budget — County Budget Implementation Review Report"


def test_national_aggregate_does_not_credit_cob_for_a_second_publishers_total(
    client, published_county,
):
    published_county(publisher="Controller of Budget", cob=True)
    published_county(entity_id=502, allocation=200, spending=120)
    body = response_for(client, "national")
    allocated = stage(body)
    assert allocated["amount"] == 300
    assert next(s for s in body["stages"] if s["stage"] == "Spent")["amount"] == 190
    assert body.get("budget_source") != "cob_cbirr"
    assert allocated.get("source") != "Controller of Budget — County Budget Implementation Review Report"
    assert "CRA" not in (allocated.get("source") or "")
    assert body["source_document_url"] is None


def test_batch_keeps_each_publishers_attribution_separate(client, published_county):
    published_county(publisher="Controller of Budget", cob=True)
    published_county(entity_id=502, allocation=200, spending=120)
    response = client.get("/api/v1/money-flow/all-counties?year=2024%2F25")
    assert response.status_code == 200, response.text
    bodies = {row["county_id"]: row for row in response.json()}
    assert stage(bodies[501])["amount"] == 100
    assert bodies[501]["budget_source"] == "cob_cbirr"
    assert stage(bodies[502])["amount"] == 200
    assert bodies[502]["budget_source"] != "cob_cbirr"
    assert "Controller of Budget" not in (stage(bodies[502]).get("source") or "")


@pytest.mark.parametrize("surface", ["list", "detail", "comprehensive"])
@pytest.mark.parametrize("cob", [False, True])
def test_county_surfaces_attribute_the_same_selected_document(
    client, published_county, surface, cob,
):
    """The companion county views cannot restore a claim removed in money flow."""
    doc = published_county(
        cob=cob,
        publisher="Office of the Controller of Budget" if cob else "Kenya National Treasury",
    )
    path = {
        "list": "/api/v1/counties?limit=50",
        "detail": "/api/v1/counties/501",
        "comprehensive": "/api/v1/counties/501/comprehensive",
    }[surface]
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    if surface == "list":
        assert len(body) == 1
        body = body[0]
    if surface == "comprehensive":
        assert body["budget"]["total_allocated"] == 100
        sources = body["budget"]["sources"]
        code = body["budget"].get("source")
        label = body["data_sources"].get("budget") or ""
        assert ("Controller of Budget" in label) is cob
    else:
        assert body["total_budget"] == 100
        sources = body["financial_summary"]["sources"]
        code = body.get("budget_source")
    assert len(sources) == 1
    assert sources[0]["url"] == doc.url
    assert sources[0]["publisher"] == doc.publisher
    assert (code == "cob_cbirr") is cob
