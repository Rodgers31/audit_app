"""A fiscal year the API cannot serve must not be answered with another one's figures.

``GET /counties?fiscal_year=`` resolved the requested label like this::

    period_ids = None
    if fiscal_year:
        try:
            canonical = _nlbl(fiscal_year)
            period_ids = [fp.id for fp in db.query(_FP).all()
                          if fp.label == canonical] or None
        except (ValueError, IndexError):
            pass  # Ignore bad fiscal_year format, return unfiltered
    ...
    if period_ids:
        bl_query = bl_query.filter(DBBudgetLine.period_id.in_(period_ids))

A label that matched no period -- a typo, a stale bookmark, a year not yet
ingested -- left ``period_ids`` at None, so the period filter was skipped
entirely and EVERY period was summed into one row. The response then published
a cross-year total under no label at all.

In production this was masked: only FY2024/25 carries CBIRR ``Total`` rows, and
``_split_classification_and_sector_lines`` prefers that single row, so
``?fiscal_year=banana`` happened to return the right headline. The development
and recurrent splits and the sector breakdown were already cross-year sums, and
the headline joins them the moment a second CBIRR year lands. The fixture below
is that second year.

``/counties/{id}`` carried the same block. ``/comprehensive`` was milder -- it
fell through to auto-resolve, publishing a different period than the caller
asked for, correctly labelled -- but silently ignoring the parameter is the
same class of defect.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod

UNSEEDED_YEAR = "2019/20"     # well-formed, no data behind it
MALFORMED_YEAR = "banana"     # not a fiscal year at all


@pytest.fixture()
def county_with_two_reported_years(db_session, seed_country, seed_source_doc):
    """Two CBIRR-reported periods, so a cross-year sum is visible."""
    entity = Entity(
        id=550,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-county",
    )
    db_session.add(entity)
    db_session.flush()

    older = FiscalPeriod(
        id=5500,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    newer = FiscalPeriod(
        id=5501,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add_all([older, newer])
    db_session.flush()

    def bl(period, category, allocated, spent):
        return BudgetLine(
            entity_id=entity.id,
            period_id=period.id,
            category=category,
            allocated_amount=allocated,
            actual_spent=spent,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )

    db_session.add_all(
        [
            bl(older, "Total", 8_000_000_000, 3_000_000_000),
            bl(older, "Development", 3_000_000_000, 500_000_000),
            bl(older, "Recurrent", 5_000_000_000, 2_500_000_000),
            bl(newer, "Total", 9_542_000_000, 4_092_000_000),
            bl(newer, "Development", 3_748_000_000, 640_000_000),
            bl(newer, "Recurrent", 5_794_000_000, 3_452_000_000),
        ]
    )
    db_session.commit()
    return entity


# The sums that must never be published as one year's budget.
BOTH_YEARS_TOTAL = 17_542_000_000
BOTH_YEARS_DEVELOPMENT = 6_748_000_000
NEWER_TOTAL = 9_542_000_000


def _row(payload, prefix="baringo"):
    rows = [c for c in payload if str(c.get("name", "")).lower().startswith(prefix)]
    assert rows, f"county missing: {[c.get('name') for c in payload]}"
    return rows[0]


# ── GET /counties ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("year", [UNSEEDED_YEAR, MALFORMED_YEAR])
def test_list_does_not_publish_a_cross_year_sum(
    client, county_with_two_reported_years, year
):
    """The headline defect: two years added together and served as one."""
    resp = client.get(f"/api/v1/counties?fiscal_year={year}")
    if resp.status_code == 200:
        row = _row(resp.json())
        assert row["total_budget"] != pytest.approx(BOTH_YEARS_TOTAL), (
            "the API summed every fiscal period into one row and published it "
            "as the budget for a year it holds no data for"
        )
        assert row["development_budget"] != pytest.approx(BOTH_YEARS_DEVELOPMENT)


@pytest.mark.parametrize("year", [UNSEEDED_YEAR, MALFORMED_YEAR])
def test_list_refuses_a_year_it_cannot_serve(
    client, county_with_two_reported_years, year
):
    """Say so, rather than answering with something else.

    Returning another period's figures under the requested year's name is the
    same defect the cross-year sum is -- just harder to notice.
    """
    resp = client.get(f"/api/v1/counties?fiscal_year={year}")
    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"]
    # The caller needs to know what it CAN ask for.
    assert "FY2024/25" in str(detail) and "FY2023/24" in str(detail)


def test_list_still_serves_a_year_it_has(client, county_with_two_reported_years):
    """The guard must not swallow valid requests -- both label forms."""
    for label in ("FY2023/24", "2023/24"):
        resp = client.get(f"/api/v1/counties?fiscal_year={label}")
        assert resp.status_code == 200, f"{label}: {resp.text}"
        assert _row(resp.json())["total_budget"] == pytest.approx(8_000_000_000)


def test_list_default_is_untouched(client, county_with_two_reported_years):
    """No fiscal_year still means "resolve it from the data"."""
    resp = client.get("/api/v1/counties")
    assert resp.status_code == 200, resp.text
    assert _row(resp.json())["total_budget"] == pytest.approx(NEWER_TOTAL)


# ── GET /counties/{id} ────────────────────────────────────────────────────


def test_detail_row_refuses_a_year_it_cannot_serve(
    client, county_with_two_reported_years
):
    resp = client.get(f"/api/v1/counties/550?fiscal_year={UNSEEDED_YEAR}")
    assert resp.status_code == 404, resp.text


# ── GET /counties/{id}/comprehensive ──────────────────────────────────────


def test_comprehensive_does_not_silently_substitute_a_period(
    client, county_with_two_reported_years
):
    """Asking for FY2019/20 used to return FY2024/25's figures."""
    resp = client.get(f"/api/v1/counties/550/comprehensive?fiscal_year={UNSEEDED_YEAR}")
    assert resp.status_code == 404, (
        "the endpoint answered a request for a year it holds no data for with "
        f"another period's budget: {resp.text[:300]}"
    )


def test_comprehensive_still_serves_a_year_it_has(
    client, county_with_two_reported_years
):
    resp = client.get("/api/v1/counties/550/comprehensive?fiscal_year=2023/24")
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["total_allocated"] == pytest.approx(8_000_000_000)
    assert resp.json()["budget"]["fiscal_year"] == "FY2023/24"
