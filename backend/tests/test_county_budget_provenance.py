"""The provenance note has to name the source the reader is actually looking at.

The county pages carry a standing amber note whose first clause read:

    "County budget allocations are a modelled estimate -- not official
     Controller of Budget figures -- using the Commission on Revenue
     Allocation (CRA) equitable-share formula."

That was true when county budgets were derived from the CRA formula. It is not
true now: ``seeding/domains/counties_budget`` parses the Controller of Budget's
County Budget Implementation Review Report, and all 47 counties carry CBIRR
Total / Development / Recurrent rows reconciling to the printed 633,303.87m.
Baringo's page prints KES 9.54B straight off that parse while the note tells
the reader it is a model.

Both kinds of period still exist in the database, though -- see
``test_county_period_agreement``: CBIRR-reported periods carrying the
classification rows, and CRA equitable-share PROJECTION periods seeded with
modelled spend, which a reader still reaches via ``?fiscal_year=``. So the note
cannot simply be reworded; the API has to say which one this response used, and
the page has to follow it.

These pin the API half of that: the endpoints report a machine-readable
provenance code for the rows they actually summed, and the prose label agrees
with it.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod


@pytest.fixture()
def county_reported_and_projected(db_session, seed_country, seed_source_doc):
    """One county, both period shapes -- the real production layout.

    FY2024/25 carries the CBIRR classification rows (this is what the page
    shows by default). FY2025/26 is the CRA equitable-share projection:
    modelled sector rows with modelled spend and no classification.
    """
    entity = Entity(
        id=530,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-county",
    )
    db_session.add(entity)
    db_session.flush()

    reported = FiscalPeriod(
        id=5300,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    projected = FiscalPeriod(
        id=5301,
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([reported, projected])
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
            # CBIRR: the Controller of Budget's own aggregates. Baringo's real
            # FY2024/25 figures, to the million.
            bl(reported, "Total", 9_542_000_000, 4_092_000_000),
            bl(reported, "Development", 3_748_000_000, 640_000_000),
            bl(reported, "Recurrent", 5_794_000_000, 3_452_000_000),
            # ...alongside the modelled per-sector split, in the same period.
            bl(reported, "Health Services", 1_704_000_000, 1_687_000_000),
            bl(reported, "Education", 1_364_000_000, 1_309_000_000),
            # CRA projection period: sector rows only, no classification.
            bl(projected, "Health Services", 1_782_000_000, 1_069_000_000),
            bl(projected, "Education", 1_426_000_000, 855_000_000),
        ]
    )
    db_session.commit()
    return entity


def _comprehensive(client, entity_id: int, fiscal_year: str | None = None):
    url = f"/api/v1/counties/{entity_id}/comprehensive"
    if fiscal_year:
        url += f"?fiscal_year={fiscal_year}"
    resp = client.get(url)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── /counties/{id}/comprehensive ──────────────────────────────────────────


def test_comprehensive_reports_cbirr_provenance_for_the_reported_period(
    client, county_reported_and_projected
):
    """The default view is the CBIRR period, and must say so."""
    detail = _comprehensive(client, county_reported_and_projected.id)

    # Guard: we really are looking at the CoB Total row, not the projection.
    assert detail["budget"]["total_allocated"] == pytest.approx(9_542_000_000)

    assert detail["budget"]["source"] == "cob_cbirr", (
        "the headline came from the Controller of Budget's CBIRR "
        "classification rows; the API must report that, because the page's "
        "provenance note is rendered from it"
    )


def test_comprehensive_reports_cra_provenance_for_the_projection_period(
    client, county_reported_and_projected
):
    """A projection period is still a model, and must still say so.

    Without this the fix degenerates into hardcoding the other string, which
    would be the same defect pointed the other way.
    """
    detail = _comprehensive(client, county_reported_and_projected.id, "2025/26")

    assert detail["budget"]["total_allocated"] == pytest.approx(3_208_000_000)
    assert detail["budget"]["source"] == "cra_model"


def test_prose_label_agrees_with_the_provenance_code(
    client, county_reported_and_projected
):
    """``data_sources.budget`` is rendered verbatim under the headline figure.

    It must not call the CBIRR figure modelled, nor claim the Controller of
    Budget published the projection.
    """
    eid = county_reported_and_projected.id

    reported = _comprehensive(client, eid)["data_sources"]["budget"]
    assert "Controller of Budget" in reported
    assert not reported.lower().startswith("modelled")

    projected = _comprehensive(client, eid, "2025/26")["data_sources"]["budget"]
    assert projected.lower().startswith("modelled")
    assert "CRA" in projected


# ── /counties (list, compare, map) ────────────────────────────────────────


def test_list_row_carries_the_same_provenance(client, county_reported_and_projected):
    """The list and compare pages carry the same note, from the same rows.

    ``GET /counties`` pins every county to the global newest CBIRR period, so
    it resolves the same way the detail page does -- and has to report it, or
    the note on those pages stays unconditional.
    """
    resp = client.get("/api/v1/counties")
    assert resp.status_code == 200, resp.text
    rows = [
        c for c in resp.json() if str(c.get("name", "")).lower().startswith("baringo")
    ]
    assert rows, f"Baringo missing: {[c.get('name') for c in resp.json()]}"

    assert rows[0]["total_budget"] == pytest.approx(9_542_000_000)
    assert rows[0]["budget_source"] == "cob_cbirr"


# ── Absence is not a provenance ───────────────────────────────────────────


def test_a_county_with_no_budget_rows_claims_no_provenance(
    client, db_session, seed_country
):
    """No figure means no source -- not a default to either label.

    Falling back to "modelled" here would print a provenance note about a
    budget the page never showed.
    """
    entity = Entity(
        id=531,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Isiolo County",
        slug="isiolo-county",
    )
    db_session.add(entity)
    db_session.commit()

    detail = _comprehensive(client, entity.id)
    assert detail["budget"]["total_allocated"] in (0, None)
    assert detail["budget"]["source"] is None
