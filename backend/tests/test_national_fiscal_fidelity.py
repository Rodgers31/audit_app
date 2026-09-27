"""Publisher-table reconciliation and period selection (#297/#320)."""
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod, FiscalSummary
from seeding.domains.fiscal_summary import fiscal_framework as ff
from seeding.domains.fiscal_summary.fetcher import _apply_fiscal_framework


def edition():
    data = json.loads((Path(__file__).parent / "fixtures/budget_summary/fy2026_27.json").read_text())
    pages = [data["pages"].get(str(i), "") for i in range(1, data["_source"]["page_count"] + 1)]
    return ff.read_edition(pages, fiscal_year="FY 2026/27")


@pytest.mark.parametrize("fy,revenue,column", [("FY 2023/24", 2288.9, "Actual"),
                                               ("FY 2024/25", 2420.2, "Preliminary"),
                                               ("FY 2025/26", 2784.4, "Supplementary I"),
                                               ("FY 2026/27", 2985.7, "Approved")])
def test_framework_preserves_printed_column(fy, revenue, column):
    split = ff.split_for_fiscal_year(edition(), fy, known_ordinary_revenue=revenue)
    assert ff.framework_payload(split, source_url="https://treasury.go.ke/book.pdf", page=63)["source"]["column"] == column


@pytest.mark.parametrize("fy,revenue,expenditure,balance,financing", [
    ("FY 2026/27", 2985.7, 4785.2, -1111.8, 1111.8),
    ("FY 2023/24", 2288.9, 3605.2, -880.5, 818.3),
])
def test_outturns_use_published_framework(client, db_session, seed_source_doc, fy, revenue, expenditure, balance, financing):
    split = ff.split_for_fiscal_year(edition(), fy, known_ordinary_revenue=revenue)
    framework = ff.framework_payload(split, source_url="https://treasury.go.ke/book.pdf", page=63)
    db_session.add(FiscalSummary(fiscal_year=fy, total_revenue=revenue*1e9,
                                recurrent_spending=float(split.values["recurrent"])*1e9,
                                development_spending=float(split.values["development"])*1e9,
                                unit="KES", page_ref="Annex 2a p63", source_document_id=seed_source_doc.id,
                                meta={"fiscal_framework": framework}))
    db_session.commit()
    row = client.get("/api/v1/dashboards/national/fiscal-outturns").json()["series"][0]
    assert row["expenditure"] == expenditure
    assert row["revenue"] == framework["total_revenue_incl_aia_billion"]
    assert row["balance"] == pytest.approx(balance)
    assert row["financing"] == financing
    assert row["source"]["page"] == "Annex Table 2a, PDF p.63"


def test_outturns_withhold_legacy_balance(client, db_session, seed_source_doc):
    db_session.add(FiscalSummary(fiscal_year="FY 2025/26", total_revenue=100e9,
                                recurrent_spending=60e9, development_spending=30e9,
                                unit="KES", page_ref="p1", source_document_id=seed_source_doc.id))
    db_session.commit()
    row = client.get("/api/v1/dashboards/national/fiscal-outturns").json()["series"][0]
    assert row["balance"] is None
    assert row["expenditure"] is None
    assert row["absent_reason"]


def test_latest_national_period_prefers_longest_then_stable_id(db_session, seed_country, seed_source_doc):
    from main import _latest_national_period
    entity = Entity(country_id=seed_country.id, type=EntityType.NATIONAL, canonical_name="National", slug="national")
    db_session.add(entity)
    db_session.flush()
    for id_, end in [(1, date(2026, 3, 31)), (2, date(2026, 6, 30)), (3, date(2026, 6, 30))]:
        period = FiscalPeriod(id=id_, country_id=seed_country.id, label=f"period {id_}", start_date=date(2025, 7, 1), end_date=end)
        db_session.add(period)
        db_session.flush()
        db_session.add(BudgetLine(entity_id=entity.id, period_id=id_, category="Total", allocated_amount=100, currency="KES", source_document_id=seed_source_doc.id))
    db_session.commit()
    assert _latest_national_period(db_session) == 3


@pytest.mark.parametrize("printed", [date(2026, 10, 5), date(2026, 9, 20), None])
def test_tbill_printed_date_never_becomes_observation_date(printed):
    from seeding.domains.national_debt.fetcher import _tbill_yield_terms
    from types import SimpleNamespace
    terms = _tbill_yield_terms({"outstanding": 100}, {
        "rate": SimpleNamespace(rate_pct=8.778, cbk_date=printed, cbk_date_text=str(printed or "")),
        "source_title": "Key Rates", "source_url": "https://www.centralbank.go.ke/",
        "retrieved_at": "2026-09-27T12:00:00+00:00",
    })
    source = terms["rate_source"]
    assert source.get("as_of") is None
    assert source["publisher_date"] == (printed.isoformat() if printed else None)
    assert source["retrieved_at"] == "2026-09-27T12:00:00+00:00"
    assert source["date_basis"] == "publisher_date_meaning_unconfirmed"
