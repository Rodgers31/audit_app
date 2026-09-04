"""One county, one period, one budget (credibility audit F7).

GET /counties and GET /counties/{id}/comprehensive resolved a county's fiscal
period by DIFFERENT rules, so the site published two budgets for every county:

    endpoint                          Mombasa budget   utilisation   pending bills
    /counties (map, list, compare)    KES 14.63B       49.8%         KES 783M
    /counties/047/comprehensive       KES  9.42B       32.0%         KES 4.65B

Nairobi differed by 23x on pending bills. A reader comparing two counties saw
one set of figures, clicked a county name, and landed on another.

The cause was not the frontend passing a fiscal year (it did, from a wall-clock
guess, but removing that changed nothing). It was the fallbacks:

  * /counties preferred the newest period carrying CoB BIRR classification rows
    -- Total / Development / Recurrent -- which exist only where the live
    Controller of Budget parse landed.
  * /comprehensive preferred the newest period with ANY actual_spent > 0, which
    cannot tell real execution from a modelled one, because the
    equitable-share PROJECTION periods were seeded with estimated spend too.

So the two walked to different periods whenever a projection period existed
alongside a reported one -- which is the normal state mid-year.

This pins them together. The fixture below reproduces exactly that shape: an
older period with CoB classification rows, and a newer projection period with
modelled spend and no classification rows.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod


@pytest.fixture()
def county_with_projection_and_reported(db_session, seed_country, seed_source_doc):
    """A county whose newest period is a projection, not a CoB report."""
    entity = Entity(
        id=470,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa County",
        slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    reported = FiscalPeriod(
        id=4700,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    projected = FiscalPeriod(
        id=4701,
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([reported, projected])
    db_session.flush()

    # Reported period: carries the CoB BIRR classification rows.
    db_session.add_all(
        [
            BudgetLine(
                entity_id=entity.id, period_id=reported.id, category="Development",
                allocated_amount=4_000_000_000, actual_spent=2_000_000_000, currency="KES", source_document_id=seed_source_doc.id,
            ),
            BudgetLine(
                entity_id=entity.id, period_id=reported.id, category="Recurrent",
                allocated_amount=10_000_000_000, actual_spent=5_000_000_000, currency="KES", source_document_id=seed_source_doc.id,
            ),
        ]
    )
    # Projection period: modelled spend, NO classification rows. This is the
    # row that used to win on the detail page.
    db_session.add(
        BudgetLine(
            entity_id=entity.id, period_id=projected.id, category="Health",
            allocated_amount=9_000_000_000, actual_spent=3_000_000_000, currency="KES",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()
    return entity


def _list_row_by_name(client, name_prefix: str):
    resp = client.get("/api/v1/counties")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    rows = [
        c for c in payload
        if str(c.get("name", "")).lower().startswith(name_prefix.lower())
    ]
    assert rows, (
        f"county {name_prefix!r} missing from the list endpoint — payload names: "
        f"{[c.get('name') for c in payload]}"
    )
    return rows[0]


def _list_row(client, entity_id: int):
    return _list_row_by_name(client, "mombasa")


def _comprehensive(client, entity_id: int):
    resp = client.get(f"/api/v1/counties/{entity_id}/comprehensive")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_list_and_detail_report_the_same_budget(
    client, county_with_projection_and_reported
):
    eid = county_with_projection_and_reported.id
    row = _list_row(client, eid)
    detail = _comprehensive(client, eid)["budget"]

    assert row["total_budget"] == pytest.approx(detail["total_allocated"]), (
        "the list and the county's own page must not publish different budgets "
        "for the same county"
    )
    assert row["total_spent"] == pytest.approx(detail["total_spent"])
    assert row["budget_utilization"] == pytest.approx(
        detail["utilization_rate"], abs=0.1
    )


def test_both_resolve_to_the_reported_period_not_the_projection(
    client, county_with_projection_and_reported
):
    """The agreed figure must be the REPORTED one, not merely a shared wrong one.

    Two endpoints agreeing on a projection would satisfy the test above while
    still publishing a modelled number as an actual.
    """
    eid = county_with_projection_and_reported.id
    detail = _comprehensive(client, eid)["budget"]
    # Development 4.0B + Recurrent 10.0B from the CoB-classified period.
    assert detail["total_allocated"] == pytest.approx(14_000_000_000)
    # NOT the 9.0B projection row.
    assert detail["total_allocated"] != pytest.approx(9_000_000_000)


def test_an_explicit_fiscal_year_still_overrides(
    client, county_with_projection_and_reported
):
    """Pinning a period by hand must keep working — that is the escape hatch."""
    eid = county_with_projection_and_reported.id
    resp = client.get(f"/api/v1/counties/{eid}/comprehensive?fiscal_year=2025/26")
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["total_allocated"] == pytest.approx(9_000_000_000)


# ── The aggregation rule, not just the period ─────────────────────────────

@pytest.fixture()
def county_with_cob_total_and_sectors(db_session, seed_country, seed_source_doc):
    """The real CoB shape: a Total/Development/Recurrent classification AND
    modelled per-sector rows, in the SAME period.

    They describe the same money two ways. Summing both triples the budget.
    This is the shape the period fix moved the detail page onto, so it has to
    be covered or the fix trades one wrong number for a worse one.
    """
    entity = Entity(
        id=471,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nakuru County",
        slug="nakuru-county",
    )
    db_session.add(entity)
    db_session.flush()
    fp = FiscalPeriod(
        id=4710,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    def bl(category, allocated, spent, subcategory=None):
        return BudgetLine(
            entity_id=entity.id,
            period_id=fp.id,
            category=category,
            subcategory=subcategory,
            allocated_amount=allocated,
            actual_spent=spent,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )

    db_session.add_all(
        [
            bl("Total", 20_000_000_000, 12_000_000_000),
            bl("Development", 6_000_000_000, 3_000_000_000),
            bl("Recurrent", 14_000_000_000, 9_000_000_000),
            # A sub-row under Recurrent: part of the classification, not an
            # extra aggregate.
            bl("Recurrent", 8_000_000_000, 5_000_000_000, subcategory="Personnel"),
            # Modelled sector split of the same money.
            bl("Health Services", 5_000_000_000, 3_000_000_000),
            bl("Education", 4_000_000_000, 2_400_000_000),
        ]
    )
    db_session.commit()
    return entity


def test_classification_and_sector_rows_are_not_double_counted(
    client, county_with_cob_total_and_sectors
):
    eid = county_with_cob_total_and_sectors.id
    detail = _comprehensive(client, eid)["budget"]

    # The CoB "Total" row wins. Not 20 + 6 + 14 + 8 + 5 + 4 = 57B, and not
    # 20 + 6 + 14 = 40B.
    assert detail["total_allocated"] == pytest.approx(20_000_000_000)
    assert detail["total_spent"] == pytest.approx(12_000_000_000)


def test_classification_rows_do_not_appear_as_spending_sectors(
    client, county_with_cob_total_and_sectors
):
    """"Recurrent" is an economic classification, not a sector a county spends on."""
    eid = county_with_cob_total_and_sectors.id
    sectors = _comprehensive(client, eid)["budget"]["sector_breakdown"]
    assert "Health Services" in sectors
    for classification in ("Total", "Development", "Recurrent"):
        assert classification not in sectors, (
            f"{classification} is a CoB economic classification and must not be "
            "rendered as a spending sector"
        )


def test_both_endpoints_agree_on_the_cob_total_shape(
    client, county_with_cob_total_and_sectors
):
    eid = county_with_cob_total_and_sectors.id
    row = _list_row_by_name(client, "nakuru")
    detail = _comprehensive(client, eid)["budget"]
    assert row["total_budget"] == pytest.approx(detail["total_allocated"])
    assert row["total_spent"] == pytest.approx(detail["total_spent"])


# ── Partial ingest: the same defect through a different door ───────────────

@pytest.fixture()
def two_counties_one_ingested(db_session, seed_country, seed_source_doc):
    """A half-ingested CoB report: the newest period covers only one county.

    The list endpoint resolves ONE period globally, so it pins every county to
    the newest period carrying CoB rows anywhere. If the detail endpoint
    resolves per-county instead, the county missing from that report falls back
    to its own older period and publishes a budget the list does not show —
    two budgets again.
    """
    old = FiscalPeriod(
        id=4800, country_id=seed_country.id, label="FY2024/25",
        start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30),
    )
    new = FiscalPeriod(
        id=4801, country_id=seed_country.id, label="FY2025/26",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([old, new])
    db_session.flush()

    ingested = Entity(
        id=480, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    missing = Entity(
        id=481, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    db_session.add_all([ingested, missing])
    db_session.flush()

    def _cob(entity_id, period_id, dev, rec):
        return [
            BudgetLine(
                entity_id=entity_id, period_id=period_id, category="Development",
                allocated_amount=dev, actual_spent=dev / 2, currency="KES",
                source_document_id=seed_source_doc.id,
            ),
            BudgetLine(
                entity_id=entity_id, period_id=period_id, category="Recurrent",
                allocated_amount=rec, actual_spent=rec / 2, currency="KES",
                source_document_id=seed_source_doc.id,
            ),
        ]

    # Nairobi made it into the newest report; Mombasa did not.
    db_session.add_all(_cob(ingested.id, new.id, 5_000_000_000, 11_000_000_000))
    db_session.add_all(_cob(missing.id, old.id, 4_000_000_000, 10_000_000_000))
    db_session.commit()
    return missing


def test_a_county_missing_from_the_newest_report_does_not_get_its_own_period(
    client, two_counties_one_ingested
):
    eid = two_counties_one_ingested.id

    row = _list_row_by_name(client, "mombasa")
    detail = _comprehensive(client, eid)["budget"]

    assert row["total_budget"] == pytest.approx(detail["total_allocated"]), (
        "Mombasa is absent from the newest CoB report. The list pins it to that "
        "period; the detail page must not fall back to Mombasa's own older "
        f"period and publish a different budget "
        f"(list={row['total_budget']}, detail={detail['total_allocated']})"
    )


# ── The economic split must come from the CoB aggregates, not a re-derivation ──

@pytest.fixture()
def county_with_full_cob_shape(db_session, seed_country, seed_source_doc):
    """The shape a real CoB BIRR period has: a Total row, the two economic
    classification rows, a sub-row under Recurrent, and modelled sector rows
    that restate the same money."""
    period = FiscalPeriod(
        id=4900, country_id=seed_country.id, label="FY2024/25",
        start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30),
    )
    db_session.add(period)
    db_session.flush()

    entity = Entity(
        id=490, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    def _bl(category, allocated, spent, subcategory=None):
        return BudgetLine(
            entity_id=entity.id, period_id=period.id, category=category,
            subcategory=subcategory, allocated_amount=allocated,
            actual_spent=spent, currency="KES",
            source_document_id=seed_source_doc.id,
        )

    db_session.add_all([
        _bl("Total", 20_000_000_000, 12_000_000_000),
        _bl("Development", 6_000_000_000, 3_000_000_000),
        _bl("Recurrent", 14_000_000_000, 9_000_000_000),
        # Sub-row under Recurrent — part of it, not additional to it.
        _bl("Recurrent", 8_000_000_000, 5_000_000_000, subcategory="Personnel Emoluments"),
        # Modelled sector rows restating the same envelope a second way.
        _bl("Health", 5_000_000_000, 3_000_000_000),
        _bl("Infrastructure", 4_000_000_000, 2_000_000_000),
        _bl("Education", 3_000_000_000, 2_000_000_000),
    ])
    db_session.commit()
    return entity


def test_development_and_recurrent_come_from_the_cob_classification(
    client, county_with_full_cob_shape
):
    """dev + recurrent must equal the CoB Total, not exceed it.

    Re-deriving the split by keyword over every row counted the aggregates,
    their sub-rows and the sector rows that restate them, and dropped the CoB
    "Total" row into recurrent (the old guard tested for "total budget", but
    the BIRR row is labelled "Total").
    """
    budget = _comprehensive(client, county_with_full_cob_shape.id)["budget"]

    total = budget["total_allocated"]
    dev = budget["development_budget"]
    rec = budget["recurrent_budget"]

    assert total == pytest.approx(20_000_000_000)
    assert dev == pytest.approx(6_000_000_000), f"expected the CoB Development row, got {dev}"
    assert rec == pytest.approx(14_000_000_000), f"expected the CoB Recurrent row, got {rec}"
    assert dev + rec == pytest.approx(total), (
        f"the economic split must sum to the published total: "
        f"{dev} + {rec} != {total}"
    )


def test_provenance_names_cob_when_the_headline_came_from_cob(
    client, county_with_full_cob_shape
):
    """The provenance string must track the rows actually used.

    It used to hardcode "Modelled from the CRA equitable-share formula — NOT
    read from Controller of Budget CBIRR tables", which denied the provenance
    of a headline this endpoint reads straight out of a published BIRR.
    """
    body = _comprehensive(client, county_with_full_cob_shape.id)
    label = body["data_sources"]["budget"]

    assert "Controller of Budget" in label, label
    assert "NOT\nread from Controller of Budget" not in label
    # The modelled part must still be declared, not quietly dropped.
    assert "modelled" in label.lower() and "sector" in label.lower(), label


def test_provenance_still_says_modelled_when_there_are_no_cob_rows(
    client, county_with_projection_and_reported, db_session
):
    """Positive control: the label must be able to say "modelled" too."""
    from models import BudgetLine

    # Strip the CoB classification rows, leaving only the modelled sector row.
    for bl in db_session.query(BudgetLine).filter(
        BudgetLine.category.in_(["Development", "Recurrent", "Total"])
    ):
        db_session.delete(bl)
    db_session.commit()

    body = _comprehensive(client, county_with_projection_and_reported.id)
    label = body["data_sources"]["budget"]
    assert "Modelled from the CRA equitable-share formula" in label, label
