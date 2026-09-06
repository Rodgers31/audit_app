"""The Allocated stage named a source the figure no longer comes from.

``routers/money_flow.py`` hardcoded, at five call sites::

    source="CRA Allocation + Conditional Grants"

That was true while the stage's AMOUNT was a sum over the modelled sector
rows. Since the classification-split fix (``test_money_flow_classification_split``)
the amount is the Controller of Budget's own CBIRR aggregate — Baringo
FY2024/25 reads KES 9.54B there, straight off the parsed report — so one
Follow the Money card contradicted itself:

    ALLOCATED  KES 9.54B
    Source: CRA Allocation + Conditional Grants
    ...
    SOURCE     Controller of Budget County BIRR 2024/25

Both kinds of period are still in the database, so the string cannot simply be
swapped for a CBIRR one: a CRA equitable-share PROJECTION period carries only
the modelled sector split, and a reader reaches one through the year picker.
``services/county_budget.budget_provenance`` already answers "which rows
produced this figure" for ``/comprehensive`` and ``GET /counties``; these pin
the money-flow endpoints to the same answer, and pin the caption to it.

All three endpoints are covered because all three carried the hardcoded string:
the per-county waterfall, the national aggregate, and the batched map feed that
the /transparency page and the county map render.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod

# Baringo's real FY2024/25 CBIRR figures, to the million.
COB_TOTAL_ALLOCATED = 9_542_000_000
COB_TOTAL_SPENT = 4_092_000_000


def _stage(payload, name):
    return next(s for s in payload["stages"] if s["stage"] == name)


def _bl(entity, period, category, allocated, spent, doc):
    return BudgetLine(
        entity_id=entity.id,
        period_id=period.id,
        category=category,
        allocated_amount=allocated,
        actual_spent=spent,
        currency="KES",
        source_document_id=doc.id,
    )


@pytest.fixture()
def periods(db_session, seed_country):
    """The two period shapes that coexist in production."""
    reported = FiscalPeriod(
        id=5400,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    projected = FiscalPeriod(
        id=5401,
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([reported, projected])
    db_session.flush()
    return reported, projected


@pytest.fixture()
def baringo(db_session, seed_country, seed_source_doc, periods):
    """One county carrying both period shapes — the production layout.

    FY2024/25 has the Controller of Budget's Total/Development/Recurrent
    classification rows *alongside* the modelled sector split of the same
    money. FY2025/26 is the CRA equitable-share projection: sector rows only.
    """
    reported, projected = periods
    entity = Entity(
        id=540,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-county",
    )
    db_session.add(entity)
    db_session.flush()

    db_session.add_all(
        [
            _bl(entity, reported, "Total", COB_TOTAL_ALLOCATED, COB_TOTAL_SPENT, seed_source_doc),
            _bl(entity, reported, "Development", 3_748_000_000, 640_000_000, seed_source_doc),
            _bl(entity, reported, "Recurrent", 5_794_000_000, 3_452_000_000, seed_source_doc),
            _bl(entity, reported, "Health Services", 1_704_000_000, 1_687_000_000, seed_source_doc),
            _bl(entity, reported, "Education", 1_364_000_000, 1_309_000_000, seed_source_doc),
            # The CRA projection: no classification rows at all.
            _bl(entity, projected, "Health Services", 1_782_000_000, 1_069_000_000, seed_source_doc),
            _bl(entity, projected, "Education", 1_426_000_000, 855_000_000, seed_source_doc),
        ]
    )
    db_session.commit()
    return entity


@pytest.fixture()
def isiolo_modelled_only(db_session, seed_country, seed_source_doc, periods):
    """A second county the CBIRR parse has NOT reached, in the same period.

    This is what a partially-ingested report looks like, and it is the only
    shape in which a national aggregate spans both provenances at once.
    """
    reported, _projected = periods
    entity = Entity(
        id=541,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Isiolo County",
        slug="isiolo-county",
    )
    db_session.add(entity)
    db_session.flush()
    db_session.add_all(
        [
            _bl(entity, reported, "Health Services", 900_000_000, 500_000_000, seed_source_doc),
            _bl(entity, reported, "Education", 700_000_000, 400_000_000, seed_source_doc),
        ]
    )
    db_session.commit()
    return entity


# ── The per-county waterfall (the Follow the Money tab) ───────────────────


def test_cbirr_period_allocated_stage_is_not_labelled_as_the_cra_model(client, baringo):
    """The defect, stated as the reader sees it.

    The card prints the Controller of Budget's own 9.54B and captions it
    "Source: CRA Allocation + Conditional Grants", three lines above a footer
    crediting the County BIRR. One of the two is wrong about the same number.
    """
    resp = client.get(f"/api/v1/counties/{baringo.id}/money-flow?year=FY2024/25")
    assert resp.status_code == 200, resp.text
    allocated = _stage(resp.json(), "Allocated")

    # Guard: this really is the CBIRR aggregate, not the sector sum.
    assert allocated["amount"] == pytest.approx(COB_TOTAL_ALLOCATED)

    assert "CRA" not in (allocated.get("source") or ""), (
        "the Allocated stage carries the Controller of Budget's CBIRR "
        "aggregate but captions it as the CRA equitable-share model — the "
        f"same card's footer credits the CBIRR. Got: {allocated.get('source')!r}"
    )
    assert "Controller of Budget" in (allocated.get("source") or "")


def test_county_waterfall_reports_the_provenance_code(client, baringo):
    """Machine-readable, so the caption and the frontend cannot drift apart.

    Same vocabulary as ``/comprehensive``'s ``budget.source`` and the county
    list's ``budget_source``.
    """
    payload = client.get(
        f"/api/v1/counties/{baringo.id}/money-flow?year=FY2024/25"
    ).json()
    assert payload.get("budget_source") == "cob_cbirr"


def test_projection_period_is_still_labelled_a_model(client, baringo):
    """Without this the fix degenerates into hardcoding the other string.

    FY2025/26 has no classification rows; its figure IS the CRA model, and
    crediting the Controller of Budget for it would be the same defect pointed
    the other way.
    """
    payload = client.get(
        f"/api/v1/counties/{baringo.id}/money-flow?year=FY2025/26"
    ).json()
    allocated = _stage(payload, "Allocated")

    assert allocated["amount"] == pytest.approx(3_208_000_000)
    assert payload.get("budget_source") == "cra_model"
    assert "CRA" in (allocated.get("source") or "")
    assert "Controller of Budget" not in (allocated.get("source") or "").replace(
        "not Controller of Budget", ""
    )


def test_money_flow_provenance_agrees_with_the_county_page(client, baringo):
    """The two tabs sit on one page and must not disagree about the source.

    ``test_money_flow_classification_split`` pinned the two to one AMOUNT;
    this pins them to one SOURCE for that amount.
    """
    flow = client.get(f"/api/v1/counties/{baringo.id}/money-flow?year=FY2024/25").json()
    detail = client.get(f"/api/v1/counties/{baringo.id}/comprehensive").json()

    assert flow.get("budget_source") == detail["budget"]["source"]


# ── Absence is not a provenance ───────────────────────────────────────────


def test_a_period_with_no_budget_claims_no_source(client, baringo):
    """No figure means no source — not a default to either label.

    The no-data branch captioned its empty stage "Source: CRA Allocation +
    Conditional Grants", a provenance claim about a figure the card never
    showed.
    """
    payload = client.get(
        f"/api/v1/counties/{baringo.id}/money-flow?year=FY2019/20"
    ).json()
    allocated = _stage(payload, "Allocated")

    assert allocated["amount"] is None
    assert allocated.get("data_unavailable") is True
    assert not allocated.get("source"), (
        "an unpublished figure was captioned with a source: "
        f"{allocated.get('source')!r}"
    )
    assert payload.get("budget_source") is None


def test_a_county_with_no_rows_claims_no_source_in_the_batched_feed(
    client, baringo, isiolo_modelled_only, db_session, seed_country
):
    """Same rule on the feed that drives the map."""
    empty = Entity(
        id=542,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Lamu County",
        slug="lamu-county",
    )
    db_session.add(empty)
    db_session.commit()

    rows = client.get("/api/v1/money-flow/all-counties?year=FY2024/25").json()
    row = next(r for r in rows if r["county_id"] == empty.id)
    allocated = _stage(row, "Allocated")

    assert allocated["amount"] is None
    assert not allocated.get("source")
    assert row.get("budget_source") is None


# ── The batched map feed ──────────────────────────────────────────────────


def test_batched_feed_labels_each_county_from_its_own_rows(
    client, baringo, isiolo_modelled_only
):
    """One period, two counties, two provenances — a half-ingested CBIRR.

    A single hardcoded caption is wrong for one of them whichever string it
    holds, so the feed has to answer per county.
    """
    rows = client.get("/api/v1/money-flow/all-counties?year=FY2024/25").json()
    cbirr = next(r for r in rows if r["county_id"] == baringo.id)
    modelled = next(r for r in rows if r["county_id"] == isiolo_modelled_only.id)

    assert cbirr.get("budget_source") == "cob_cbirr"
    assert "Controller of Budget" in (_stage(cbirr, "Allocated").get("source") or "")

    assert modelled.get("budget_source") == "cra_model"
    assert "CRA" in (_stage(modelled, "Allocated").get("source") or "")


def test_batched_feed_agrees_with_the_per_county_endpoint(client, baringo):
    """The map and the tab must not caption the same figure differently."""
    rows = client.get("/api/v1/money-flow/all-counties?year=FY2024/25").json()
    row = next(r for r in rows if r["county_id"] == baringo.id)
    single = client.get(
        f"/api/v1/counties/{baringo.id}/money-flow?year=FY2024/25"
    ).json()

    assert row.get("budget_source") == single.get("budget_source")
    assert _stage(row, "Allocated").get("source") == _stage(single, "Allocated").get(
        "source"
    )


# ── The national aggregate (the /transparency page) ───────────────────────


def test_national_aggregate_of_cbirr_counties_is_not_labelled_a_model(client, baringo):
    """/transparency's hero waterfall captions this same stage."""
    payload = client.get("/api/v1/audit/money-flow/national?year=FY2024/25").json()
    allocated = _stage(payload, "Allocated")

    assert allocated["amount"] == pytest.approx(COB_TOTAL_ALLOCATED)
    assert payload.get("budget_source") == "cob_cbirr"
    assert "CRA" not in (allocated.get("source") or "")


def test_national_aggregate_spanning_both_sources_says_so(
    client, baringo, isiolo_modelled_only
):
    """A pooled figure that is half CBIRR and half model is neither.

    Naming one source would be wrong about the other half of the money, in one
    direction or the other — the same reason the county list carries a mixed
    clause.
    """
    payload = client.get("/api/v1/audit/money-flow/national?year=FY2024/25").json()
    allocated = _stage(payload, "Allocated")

    assert allocated["amount"] == pytest.approx(COB_TOTAL_ALLOCATED + 1_600_000_000)
    assert payload.get("budget_source") == "mixed"
    source = allocated.get("source") or ""
    assert "Controller of Budget" in source and "CRA" in source


def test_national_aggregate_with_no_periods_claims_no_source(client, baringo):
    payload = client.get("/api/v1/audit/money-flow/national?year=FY2019/20").json()
    allocated = _stage(payload, "Allocated")

    assert allocated["amount"] is None
    assert not allocated.get("source")
    assert payload.get("budget_source") is None
