"""The county explorer's year picker must come from the data, not the calendar.

``CountiesPageClient`` seeded its fiscal-year dropdown with
``getLatestReportedFiscalYear()``, a label computed from ``new Date()``:

    const startYear = now.getMonth() >= 6 ? now.getFullYear() - 1 : ...

On 2026-09-05 that returns "2025/26" and the explorer asked
``GET /counties?fiscal_year=2025/26`` -- the CRA equitable-share PROJECTION
period. The detail page had already been fixed to send nothing and let the
backend resolve the period from the rows that exist
(``_latest_county_actuals_period_ids``), so the two disagreed:

    /counties?fiscal_year=2025/26   Baringo  KES 7.13B   (modelled)
    /counties/030/comprehensive     Baringo  KES 9.54B   (CBIRR)

A reader landing on a county page directly saw one figure; the explorer showed
another. That is credibility audit F7 returning through the frontend's explicit
``fiscal_year``, which the endpoint-default tests cannot catch.

This pins the replacement: an endpoint that reports which fiscal years county
budget data actually exists for, and which one the API resolves to by default.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod


@pytest.fixture()
def counties_across_periods(db_session, seed_country, seed_source_doc):
    """Two counties over three periods, in the production layout.

    FY2024/25 is the CBIRR report (classification rows). FY2025/26 is the newer
    CRA projection -- newest by date, and what a wall-clock guess picks.
    FY2019/20 holds no county budget rows at all, so it must not be offered.
    """
    entities = []
    for eid, name in ((540, "Baringo County"), (541, "Mombasa County")):
        e = Entity(
            id=eid,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=name,
            slug=name.lower().replace(" ", "-"),
        )
        db_session.add(e)
        entities.append(e)
    db_session.flush()

    periods = {}
    for pid, label, start in (
        (5400, "FY2024/25", datetime(2024, 7, 1)),
        (5401, "FY2025/26", datetime(2025, 7, 1)),
        (5402, "FY2019/20", datetime(2019, 7, 1)),
    ):
        fp = FiscalPeriod(
            id=pid,
            country_id=seed_country.id,
            label=label,
            start_date=start,
            end_date=datetime(start.year + 1, 6, 30),
        )
        db_session.add(fp)
        periods[label] = fp
    db_session.flush()

    def bl(entity, label, category, allocated, spent):
        return BudgetLine(
            entity_id=entity.id,
            period_id=periods[label].id,
            category=category,
            allocated_amount=allocated,
            actual_spent=spent,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )

    rows = []
    for e in entities:
        rows += [
            bl(e, "FY2024/25", "Total", 9_542_000_000, 4_092_000_000),
            bl(e, "FY2024/25", "Development", 3_748_000_000, 640_000_000),
            bl(e, "FY2024/25", "Recurrent", 5_794_000_000, 3_452_000_000),
            bl(e, "FY2025/26", "Health Services", 1_782_000_000, 1_069_000_000),
            bl(e, "FY2025/26", "Education", 1_426_000_000, 855_000_000),
        ]
    db_session.add_all(rows)
    db_session.commit()
    return entities


def _fiscal_years(client):
    resp = client.get("/api/v1/counties/fiscal-years")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_default_is_the_reported_year_not_the_newest(client, counties_across_periods):
    """The wall-clock guess picks FY2025/26. The data says FY2024/25."""
    payload = _fiscal_years(client)
    assert payload["default"] == "FY2024/25", (
        "the default must be the period the API actually resolves to -- the one "
        "carrying Controller of Budget classification rows -- not the newest "
        "period on the calendar"
    )


def test_default_matches_what_the_unfiltered_list_returns(
    client, counties_across_periods
):
    """The picker's default and the unparameterised list must agree.

    This is the property that matters: the explorer shows the default year's
    label above figures it fetched. If the two are resolved by different rules
    they drift apart again, and the label starts lying about the figures.
    """
    default = _fiscal_years(client)["default"]

    unfiltered = client.get("/api/v1/counties")
    assert unfiltered.status_code == 200, unfiltered.text
    pinned = client.get(f"/api/v1/counties?fiscal_year={default}")
    assert pinned.status_code == 200, pinned.text

    by_name = lambda rows: {r["name"]: r["total_budget"] for r in rows}
    assert by_name(unfiltered.json()) == by_name(pinned.json())
    # ...and it is the CBIRR figure, not the projection.
    assert by_name(unfiltered.json())["Baringo"] == pytest.approx(9_542_000_000)


def test_only_years_with_county_budget_data_are_offered(
    client, counties_across_periods
):
    """A dropdown entry is a claim that the year has something to show."""
    labels = [y["label"] for y in _fiscal_years(client)["years"]]
    assert "FY2024/25" in labels
    assert "FY2025/26" in labels
    assert "FY2019/20" not in labels, (
        "FY2019/20 has no county budget rows; offering it would send the reader "
        "to an empty page"
    )


def test_years_are_newest_first_and_carry_their_provenance(
    client, counties_across_periods
):
    """The picker can then say which years are reported and which are modelled."""
    years = _fiscal_years(client)["years"]
    assert [y["label"] for y in years] == ["FY2025/26", "FY2024/25"]
    by_label = {y["label"]: y for y in years}
    assert by_label["FY2024/25"]["source"] == "cob_cbirr"
    assert by_label["FY2025/26"]["source"] == "cra_model"


def test_the_route_is_not_swallowed_by_the_county_id_route(
    client, counties_across_periods
):
    """`/counties/{county_id}` would match "fiscal-years" as an id.

    Declaration order is load-bearing here and nothing else would catch it
    being moved -- the endpoint would just start 404ing or, worse, return a
    county-shaped payload.
    """
    resp = client.get("/api/v1/counties/fiscal-years")
    assert resp.status_code == 200, resp.text
    assert "years" in resp.json() and "default" in resp.json()


def test_no_county_budget_data_reports_no_years_and_no_default(
    client, db_session, seed_country
):
    """Absence is reported as absence -- not as a plausible-looking year.

    Returning a calendar-derived label here would put the site back where it
    started: a year on screen that nothing in the database supports.
    """
    payload = _fiscal_years(client)
    assert payload["years"] == []
    assert payload["default"] is None
