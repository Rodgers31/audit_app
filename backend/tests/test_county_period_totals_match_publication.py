"""Sum a county period and compare it to the published total (#238 §4).

The Controller of Budget's CBIRR for the first nine months of FY2025/26 prints
county budgets of KSh 633.30B in total. In the database each county carries
that budget three ways — Total, Recurrent and Development — beside its
own-source revenue and, now, its revenue receipts. ``/budget/overview``,
``/countries/{id}/summary`` and ``/budget/utilization`` summed every row except
the literal category "Total Budget", so a CBIRR period came out as
633.30 + 398.97 + 234.33 + 100.13 = KSh 1,366.7B.

The fixture is two counties with their published CBIRR figures; the published
total for the pair is their two "Total" rows.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod

# CBIRR 9M FY2025/26, Table 2.4 (KSh) and Table 2.1 (own-source revenue).
PUBLISHED = {
    "Nairobi County": {
        "Total": (44_620_890_000, 32_122_660_000),
        "Recurrent": (31_203_190_000, 27_067_600_000),
        "Development": (13_417_700_000, 5_055_060_000),
        "Own Source Revenue": (21_178_050_000, 10_789_420_000),
    },
    "Baringo County": {
        "Total": (9_542_030_000, 4_092_380_000),
        "Recurrent": (5_793_600_000, 3_647_480_000),
        "Development": (3_748_430_000, 444_900_000),
        "Own Source Revenue": (651_940_000, 326_510_000),
    },
}
PUBLISHED_TOTAL = sum(c["Total"][0] for c in PUBLISHED.values())  # 54,162,920,000
PUBLISHED_SPENT = sum(c["Total"][1] for c in PUBLISHED.values())


@pytest.fixture()
def cbirr_period(db_session, seed_country, seed_source_doc):
    period = FiscalPeriod(
        id=9101, country_id=seed_country.id, label="FY2025/26 9M",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 3, 31),
    )
    db_session.add(period)
    db_session.flush()
    for i, (name, rows) in enumerate(PUBLISHED.items()):
        entity = Entity(
            id=910 + i, country_id=seed_country.id, type=EntityType.COUNTY,
            canonical_name=name, slug=name.lower().replace(" ", "-"),
        )
        db_session.add(entity)
        db_session.flush()
        for category, (allocated, spent) in rows.items():
            db_session.add(BudgetLine(
                entity_id=entity.id, period_id=period.id, category=category,
                allocated_amount=allocated, actual_spent=spent, currency="KES",
                source_document_id=seed_source_doc.id,
            ))
        # The county's revenue receipts are money in, never budget.
        db_session.add(BudgetLine(
            entity_id=entity.id, period_id=period.id, category="Revenue Receipts",
            subcategory="Total", allocated_amount=rows["Total"][0],
            actual_spent=rows["Total"][1] // 2, currency="KES",
            source_document_id=seed_source_doc.id,
        ))
    db_session.commit()
    return period


def _get(client, path):
    from main import clear_all_caches

    clear_all_caches()
    response = client.get(path)
    assert response.status_code == 200, response.text[:300]
    return response.json()


def test_budget_overview_sums_to_the_published_total(client, cbirr_period):
    """RED before #238: 2.4x the published total (every category summed)."""
    summary = _get(client, "/api/v1/budget/overview")["summary"]

    assert summary["total_budget"] == pytest.approx(PUBLISHED_TOTAL)
    assert summary["total_spent"] == pytest.approx(PUBLISHED_SPENT)


def test_country_summary_sums_to_the_published_total(client, cbirr_period):
    body = _get(client, "/api/v1/countries/1/summary")
    allocation = _find(body, "total_allocation")
    assert allocation is not None, str(body)[:400]
    assert allocation["value"] == pytest.approx(PUBLISHED_TOTAL)


def test_budget_utilization_is_per_county_published_totals(client, cbirr_period):
    rows = {r["entity"]: r for r in _get(client, "/api/v1/budget/utilization")["data"]}

    for name, published in PUBLISHED.items():
        assert rows[name]["allocated"] == pytest.approx(published["Total"][0]), name
        assert rows[name]["spent"] == pytest.approx(published["Total"][1]), name


def test_the_list_agrees_with_the_overview(client, cbirr_period):
    """One rule: GET /counties and /budget/overview publish the same sum."""
    listed = _get(client, "/api/v1/counties")
    overview = _get(client, "/api/v1/budget/overview")["summary"]

    assert sum(c["total_budget"] for c in listed) == pytest.approx(overview["total_budget"])


def test_sector_spending_carries_no_classification_rows(client, cbirr_period):
    body = _get(client, "/api/v1/sectors/spending")
    assert body.get("total_allocated") in (0, 0.0, None)


@pytest.mark.parametrize("full_year_first", [True, False])
@pytest.mark.parametrize("full_id, part_id", [(9100, 9102), (9102, 9100)])
def test_a_full_year_beats_its_part_year_report_on_a_shared_start_date(
    db_session, seed_country, seed_source_doc, full_year_first, full_id, part_id
):
    """``_latest_county_period`` ordered on start_date alone; FY2025/26 and
    FY2025/26 9M share one, so which period the overview summed depended on
    row and id order. Every order is tried: the full year — later end date —
    wins in each."""
    import main

    entity = Entity(
        id=920, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    full = FiscalPeriod(
        id=full_id, country_id=seed_country.id, label="FY2025/26",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30),
    )
    part = FiscalPeriod(
        id=part_id, country_id=seed_country.id, label="FY2025/26 9M",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 3, 31),
    )
    db_session.add_all([entity, full, part])
    db_session.flush()
    order = [full, part] if full_year_first else [part, full]
    for period in order:
        db_session.add(BudgetLine(
            entity_id=entity.id, period_id=period.id, category="Total",
            allocated_amount=1, actual_spent=0, currency="KES",
            source_document_id=seed_source_doc.id,
        ))
        db_session.flush()
    db_session.commit()

    assert main._latest_county_period(db_session) == full.id


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, key)
            if found is not None:
                return found
    return None


def test_a_year_that_is_not_there_sums_nothing(client, cbirr_period, db_session, seed_country, seed_source_doc):
    """``/budget/utilization?fiscal_year=`` with an unknown year left the
    period unresolved, and an unresolved period summed EVERY period into one
    figure per county. A second period makes that visible."""
    other = FiscalPeriod(
        id=9103, country_id=seed_country.id, label="FY2023/24",
        start_date=datetime(2023, 7, 1), end_date=datetime(2024, 6, 30),
    )
    db_session.add(other)
    db_session.flush()
    db_session.add(BudgetLine(
        entity_id=910, period_id=other.id, category="Total",
        allocated_amount=40_000_000_000, actual_spent=1, currency="KES",
        source_document_id=seed_source_doc.id,
    ))
    db_session.commit()

    rows = _get(client, "/api/v1/budget/utilization?fiscal_year=1999/00")["data"]
    assert rows == []
