"""A county nobody has counted is served as absent, not as zero residents.

The county-detail endpoint stopped publishing 0 for a missing census row when
the modelled `entity.meta` figures were deleted; the list endpoint
(`/api/v1/counties`, which feeds the County Explorer table, the map and the
compare page) and the single-county endpoint (`/api/v1/counties/{id}`) kept
`pop_data.total_population if pop_data else 0`.

Zero is a claim — that a county has no residents — and it is a claim the
downstream consumers act on: the Explorer's "Population (High → Low)" sort
ranks it as the smallest county in Kenya, and the compare page's per-capita
row divides by it.

All 47 counties currently carry a KNBS 2019 census row, so nothing in
production reaches this today. That is the reason to pin it: the day an
extractor drops a county, the site would answer "0 residents" with a straight
face instead of "we do not know".
"""

from datetime import datetime

import pytest
from models import (
    BudgetLine,
    Entity,
    EntityType,
    FiscalPeriod,
    PopulationData,
)

# The census figure KNBS published for Nairobi in 2019. Used only so the
# "counted" county is distinguishable from the uncounted one.
NAIROBI_CENSUS_2019 = 4_397_073


@pytest.fixture()
def counted_and_uncounted_counties(db_session, seed_country, seed_source_doc):
    """Nairobi has a census row; Kwale has none.

    Kwale is the one under test. Nairobi is the control: a fix that nulls
    every county's population would satisfy the absence assertion and break
    the site, so both directions are pinned.
    """
    nairobi = Entity(
        id=101,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-county",
    )
    kwale = Entity(
        id=102,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kwale County",
        slug="kwale-county",
    )
    db_session.add_all([nairobi, kwale])
    db_session.flush()

    fp = FiscalPeriod(
        id=101,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    db_session.add(
        PopulationData(
            entity_id=nairobi.id,
            year=2019,
            total_population=NAIROBI_CENSUS_2019,
            source_document_id=seed_source_doc.id,
        )
    )
    # Kwale deliberately gets no PopulationData row.

    for entity in (nairobi, kwale):
        db_session.add(
            BudgetLine(
                entity_id=entity.id,
                period_id=fp.id,
                category="Health",
                allocated_amount=8_000_000,
                actual_spent=6_000_000,
                currency="KES",
                source_document_id=seed_source_doc.id,
            )
        )

    db_session.commit()
    return {"nairobi": nairobi, "kwale": kwale}


def _row(payload, county_id):
    """The list row for one county id, or a readable failure."""
    matches = [r for r in payload if r.get("id") == county_id]
    assert matches, (
        f"county {county_id!r} missing from the list payload; "
        f"got {[r.get('id') for r in payload]}"
    )
    return matches[0]


class TestCountyListPopulationAbsence:
    """GET /api/v1/counties — the payload behind the list, map and compare."""

    def test_uncounted_county_is_served_as_null(
        self, client, counted_and_uncounted_counties
    ):
        response = client.get("/api/v1/counties")
        assert response.status_code == 200, response.text

        kwale = _row(response.json(), "002")
        assert kwale["population"] is None, (
            "a county with no PopulationData row was published as "
            f"population={kwale['population']!r}; 0 states that nobody lives "
            "there, which is a claim no source made"
        )

    def test_counted_county_still_reports_its_census(
        self, client, counted_and_uncounted_counties
    ):
        response = client.get("/api/v1/counties")
        assert response.status_code == 200, response.text

        nairobi = _row(response.json(), "001")
        assert nairobi["population"] == NAIROBI_CENSUS_2019


class TestCountyDetailPopulationAbsence:
    """GET /api/v1/counties/{county_id} — the same field, one county at a time."""

    def test_uncounted_county_is_served_as_null(
        self, client, counted_and_uncounted_counties
    ):
        response = client.get("/api/v1/counties/002")
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["name"] == "Kwale"
        assert body["population"] is None, (
            "a county with no PopulationData row was published as "
            f"population={body['population']!r}"
        )

    def test_counted_county_still_reports_its_census(
        self, client, counted_and_uncounted_counties
    ):
        response = client.get("/api/v1/counties/001")
        assert response.status_code == 200, response.text
        assert response.json()["population"] == NAIROBI_CENSUS_2019
