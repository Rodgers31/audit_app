"""A source refusal remains identifiable after the county publication boundary."""
import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from main import _county_revenue_for_lines
from models import BudgetLine, Entity, EntityType, FiscalPeriod

MANIFEST = json.loads(
    (
        Path(__file__).parents[2]
        / "docs/verification/2026-10-01-round11-county-source-manifest.json"
    ).read_text()
)
CASES = MANIFEST["cash"]["cases"]
SOURCE = MANIFEST["source"]


@pytest.fixture
def refusal_rows(db_session, seed_country, seed_source_doc):
    seed_source_doc.publisher = "Office of the Controller of Budget"
    seed_source_doc.title = "Controller of Budget County BIRR FY2025/26"
    seed_source_doc.url = SOURCE["url"]
    seed_source_doc.meta = {"sha256": SOURCE["sha256"]}
    period = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    db_session.add(period)
    db_session.flush()
    rows = {}
    for case in CASES:
        name = case["county"]
        entity = Entity(
            country_id=seed_country.id,
            canonical_name=name + " County",
            slug=name.lower() + "-county",
            type=EntityType.COUNTY,
        )
        db_session.add(entity)
        db_session.flush()
        coverage = dict(
            status="withheld",
            reason=case["parser_refusal"],
            pages=case["pdf_pages"],
            basis="cash_receipts_including_opening_balance",
        )
        row = BudgetLine(
            entity_id=entity.id,
            period_id=period.id,
            category="Total",
            allocated_amount=10_000_000,
            actual_spent=7_000_000,
            currency="KES",
            source_document_id=seed_source_doc.id,
            provenance=[
                dict(
                    data_quality="official",
                    source_label=seed_source_doc.title,
                    artifact_sha256=SOURCE["sha256"],
                    revenue_coverage=coverage,
                )
            ],
        )
        db_session.add(row)
        rows[name] = row
    db_session.flush()
    return rows


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["county"])
def test_refusal_survives_reader_and_public_county_routes(client, refusal_rows, case):
    name = case["county"]
    for route in [
        f"/api/v1/counties/{name.lower()}-county",
        f"/api/v1/counties/{name.lower()}-county/comprehensive",
    ]:
        response = client.get(route)
        assert response.status_code == 200, response.text
        revenue = response.json()["revenue"]
        assert revenue["total_revenue"] is None
        assert revenue["streams"] == []
        assert revenue["total_revenue_absent_reason"] == case["parser_refusal"]
        assert revenue["fiscal_year"] == "FY2025/26"
        assert revenue["total_revenue_absence_source"]["url"] == SOURCE["url"]
        assert revenue["total_revenue_absence_source"]["pages"] == case["pdf_pages"]
    listed = next(c for c in client.get("/api/v1/counties").json() if c["name"] == name)
    assert listed["revenue"]["total_revenue_absent_reason"] == case["parser_refusal"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "garbage",
        "dict",
        "wrong_basis",
        "wrong_status",
        "wrong_source",
        "wrong_currency",
        "conflicting",
        "old_only",
        "bad_pages",
    ],
)
def test_unsupported_coverage_cannot_be_named_as_current_cash_refusal(
    refusal_rows, mutation
):
    row = refusal_rows["Kwale"]
    provenance = copy.deepcopy(row.provenance)
    if mutation == "missing":
        provenance = []
    elif mutation == "garbage":
        provenance = "garbage"
    elif mutation == "dict":
        provenance = provenance[0]
    elif mutation == "wrong_basis":
        provenance[0]["revenue_coverage"]["basis"] = "accrual"
    elif mutation == "wrong_status":
        provenance[0]["revenue_coverage"]["status"] = "reconciled"
    elif mutation == "wrong_source":
        provenance[0]["source_label"] = "An older edition"
    elif mutation == "wrong_currency":
        row.currency = "USD"
    elif mutation == "conflicting":
        newer = copy.deepcopy(provenance[0])
        newer["revenue_coverage"]["reason"] = "unobserved_receipts_cell"
        provenance.append(newer)
    elif mutation == "old_only":
        provenance.append(dict(data_quality="official"))
    elif mutation == "bad_pages":
        provenance[0]["revenue_coverage"]["pages"] = [True]
    row.provenance = provenance
    result = _county_revenue_for_lines([row])
    assert result["total_revenue"] is None
    assert result["total_revenue_absent_reason"] == "no_reconciled_cbirr_revenue_table"
    assert result.get("total_revenue_absence_source") is None


def _receipt(total, name, actual, source_id=None):
    return SimpleNamespace(
        category="Revenue Receipts",
        subcategory=name,
        actual_spent=actual,
        allocated_amount=actual,
        entity_id=total.entity_id,
        period_id=total.period_id,
        currency="KES",
        source_document_id=source_id or total.source_document_id,
        period=total.period,
        source_document=total.source_document,
        page_ref="PDF p. 42",
    )


def test_present_cash_keeps_zero_and_does_not_inherit_refusal(refusal_rows):
    total = refusal_rows["Kwale"]
    result = _county_revenue_for_lines(
        [total, _receipt(total, "Own Source Revenue", 0), _receipt(total, "Total", 0)]
    )
    assert result["total_revenue"] == result["local_revenue"] == 0
    assert result["total_revenue_absent_reason"] is None
    assert result.get("total_revenue_absence_source") is None


def test_refusal_does_not_attach_to_a_summary_from_another_source(refusal_rows):
    total = refusal_rows["Kwale"]
    summary = _receipt(total, None, 50, source_id=999)
    summary.category = "Own Source Revenue"
    result = _county_revenue_for_lines([total, summary])
    assert result["local_revenue"] == 50
    assert result["total_revenue_absent_reason"] == "no_reconciled_cbirr_revenue_table"
    assert result.get("total_revenue_absence_source") is None


@pytest.mark.parametrize("sha", ["0" * 64, None, True, "not-a-digest"])
def test_stale_or_absent_linked_source_digest_does_not_relabel_cash_absence(
    client, refusal_rows, db_session, sha
):
    row = refusal_rows["Kwale"]
    row.source_document.meta = {"sha256": sha}
    db_session.flush()
    result = client.get("/api/v1/counties/kwale-county/comprehensive")
    assert result.status_code == 200, result.text
    revenue = result.json()["revenue"]
    assert revenue["total_revenue"] is None
    assert revenue["total_revenue_absent_reason"] == "no_reconciled_cbirr_revenue_table"
    assert revenue.get("total_revenue_absence_source") is None
