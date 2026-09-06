"""Follow the Money summed the CoB classification rows AND the sector split.

The Controller of Budget's implementation reports carry whole-budget ECONOMIC
classification rows -- Total / Development / Recurrent -- alongside the
(modelled) per-sector rows. They describe the same money two ways, so summing
both double- or triple-counts a county's budget.

``_split_classification_and_sector_lines`` was written for exactly this and is
applied by ``GET /counties`` and ``/comprehensive``. The money-flow router
never got it::

    allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)

For Baringo FY2024/25 that is 19,084,060,000 of classification rows plus
7,469,628,217 of sector rows = 26,553,688,217 -- published as the county's
budget allocation while the county's own Budget tab, two clicks away, showed
the Controller of Budget's figure of 9,542,030,000. A 2.78x overstatement of
one county's budget, on the page whose whole purpose is tracing that money.

All three money-flow endpoints carried the same naive sum: the per-county
waterfall, the national aggregate, and the batched all-counties feed.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import Audit, BudgetLine, Entity, EntityType, FiscalPeriod, Severity

# Baringo's real FY2024/25 rows, to the million.
COB_TOTAL_ALLOCATED = 9_542_030_000
COB_TOTAL_SPENT = 4_092_380_000
NAIVE_ALLOCATED = 26_553_688_217   # what every row added together comes to
NAIVE_SPENT = 14_810_132_144


@pytest.fixture()
def county_with_cob_and_sector_rows(db_session, seed_country, seed_source_doc):
    """The real CBIRR shape: classification aggregates AND a sector split."""
    entity = Entity(
        id=560,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-county",
    )
    db_session.add(entity)
    db_session.flush()

    fp = FiscalPeriod(
        id=5600,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    def bl(category, allocated, spent):
        return BudgetLine(
            entity_id=entity.id,
            period_id=fp.id,
            category=category,
            allocated_amount=allocated,
            actual_spent=spent,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )

    rows = [
        # The Controller of Budget's own aggregates.
        bl("Total", COB_TOTAL_ALLOCATED, COB_TOTAL_SPENT),
        bl("Development", 3_748_000_000, 640_000_000),
        bl("Recurrent", 5_794_030_000, 3_452_380_000),
        # ...and the modelled per-sector split of the SAME money.
        bl("Administration", 477_101_500, 444_000_000),
        bl("Agriculture", 545_259_000, 507_000_000),
        bl("Education", 1_363_147_500, 1_309_000_000),
        bl("Environment", 272_629_500, 229_000_000),
        bl("Health Services", 1_703_934_400, 1_687_000_000),
        bl("Other", 204_472_100, 178_000_000),
        bl("Roads and Public Works", 1_022_360_600, 849_000_000),
        bl("Social Services", 204_472_100, 182_000_000),
        bl("Trade and Industry", 340_786_800, 300_000_000),
        bl("Water and Sanitation", 682_182_717, 614_000_000),
        # Money the county RAISED, stored in the same table. Never expenditure.
        bl("Own Source Revenue", 653_282_000, 327_000_000),
    ]
    db_session.add_all(rows)
    db_session.add(
        Audit(
            entity_id=entity.id,
            period_id=fp.id,
            finding_text="Unsupported accounts payable",
            severity=Severity.CRITICAL,
            amount=1_200_000,
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()
    return entity


def _stage(payload, name):
    return next(s for s in payload["stages"] if s["stage"] == name)


# ── The per-county waterfall (the Follow the Money tab) ───────────────────


def test_county_waterfall_uses_the_cob_total_not_every_row(
    client, county_with_cob_and_sector_rows
):
    resp = client.get(
        f"/api/v1/counties/{county_with_cob_and_sector_rows.id}/money-flow"
        "?year=FY2024/25"
    )
    assert resp.status_code == 200, resp.text
    allocated = _stage(resp.json(), "Allocated")["amount"]

    assert allocated != pytest.approx(NAIVE_ALLOCATED), (
        "the waterfall added the Controller of Budget's Total/Development/"
        "Recurrent aggregates to the per-sector split of the same money"
    )
    assert allocated == pytest.approx(COB_TOTAL_ALLOCATED)


def test_county_waterfall_spend_is_not_triple_counted(
    client, county_with_cob_and_sector_rows
):
    """A tripled numerator and denominator hid this in the efficiency score."""
    resp = client.get(
        f"/api/v1/counties/{county_with_cob_and_sector_rows.id}/money-flow"
        "?year=FY2024/25"
    )
    spent = _stage(resp.json(), "Spent")["amount"]
    assert spent != pytest.approx(NAIVE_SPENT)
    assert spent == pytest.approx(COB_TOTAL_SPENT)


def test_the_two_tabs_on_one_page_report_one_budget(
    client, county_with_cob_and_sector_rows
):
    """Follow the Money and Budget & Debt sit on the same county page.

    This is the property that matters: a reader clicking between them must not
    be shown two different budgets for the same county and year.
    """
    eid = county_with_cob_and_sector_rows.id
    flow = client.get(f"/api/v1/counties/{eid}/money-flow?year=FY2024/25").json()
    detail = client.get(f"/api/v1/counties/{eid}/comprehensive").json()

    assert _stage(flow, "Allocated")["amount"] == pytest.approx(
        detail["budget"]["total_allocated"]
    )
    assert _stage(flow, "Spent")["amount"] == pytest.approx(
        detail["budget"]["total_spent"]
    )


def test_own_source_revenue_is_not_counted_as_expenditure(
    client, county_with_cob_and_sector_rows
):
    """Money the county RAISED shares the table but is not money it spent."""
    resp = client.get(
        f"/api/v1/counties/{county_with_cob_and_sector_rows.id}/money-flow"
        "?year=FY2024/25"
    )
    allocated = _stage(resp.json(), "Allocated")["amount"]
    assert allocated == pytest.approx(COB_TOTAL_ALLOCATED)
    assert allocated != pytest.approx(COB_TOTAL_ALLOCATED + 653_282_000)


# ── The other two endpoints on the same rule ──────────────────────────────


def test_national_aggregate_is_not_triple_counted(
    client, county_with_cob_and_sector_rows
):
    resp = client.get("/api/v1/audit/money-flow/national?year=FY2024/25")
    assert resp.status_code == 200, resp.text
    allocated = _stage(resp.json(), "Allocated")["amount"]
    assert allocated != pytest.approx(NAIVE_ALLOCATED)
    assert allocated == pytest.approx(COB_TOTAL_ALLOCATED)


def test_all_counties_feed_agrees_with_the_per_county_endpoint(
    client, county_with_cob_and_sector_rows
):
    """The batched feed drives the map; it must not disagree with the tab."""
    eid = county_with_cob_and_sector_rows.id
    batch = client.get("/api/v1/money-flow/all-counties?year=FY2024/25")
    assert batch.status_code == 200, batch.text
    row = next(r for r in batch.json() if r["county_id"] == eid)
    single = client.get(f"/api/v1/counties/{eid}/money-flow?year=FY2024/25").json()

    assert _stage(row, "Allocated")["amount"] == pytest.approx(COB_TOTAL_ALLOCATED)
    assert _stage(row, "Allocated")["amount"] == pytest.approx(
        _stage(single, "Allocated")["amount"]
    )
    assert _stage(row, "Spent")["amount"] == pytest.approx(
        _stage(single, "Spent")["amount"]
    )
