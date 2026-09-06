"""A county nobody has counted is absent from the census, not a county of zero.

Companion to ``test_county_list_population_absence.py``, which pinned the same
rule on ``/api/v1/counties`` and ``/api/v1/counties/{id}``. Three call sites in
``main.py`` were left behind by that change, and each of them turns a missing
``PopulationData`` row into the number 0:

* ``GET /api/v1/counties/{id}/summary`` published ``population: 0``;
* ``_compute_accountability`` (behind ``/accountability`` and ``/summary``)
  bucketed the same 0 into ``"<500k"``, so an uncounted county was filed in
  Kenya's smallest population bracket and then told, on the county page, that
  it sits above or below "the bracket average" — a comparison against a peer
  group it was never shown to belong to. The peer side of that bracket had the
  mirror-image defect: a peer with no census row also bucketed at 0, so
  counties of unknown size were averaged into ``<500k``'s flagged amounts;
* ``transform_county_data_for_frontend`` — the enhanced-API fallback for
  ``/api/v1/counties/{id}`` — returned ``population or 0``.

All 47 counties carry a KNBS 2019 census row today, so none of this is
reachable in production. That is the reason to pin it: the path is walked the
day an extractor drops a county, and the site would answer with a straight
face.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from models import (
    Audit,
    BudgetLine,
    Entity,
    EntityType,
    FiscalPeriod,
    PopulationData,
    Severity,
)

# KNBS 2019. Used only so a counted county is distinguishable from an
# uncounted one, and so the counted one lands in a bracket that is plainly
# not the "<500k" an absent row would have been bucketed into.
NAIROBI_CENSUS_2019 = 4_397_073
LAMU_CENSUS_2019 = 143_920


def _entity(seed_country, *, eid: int, name: str) -> Entity:
    return Entity(
        id=eid,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name=f"{name} County",
        slug=f"{name.lower().replace(' ', '-')}-county",
    )


def _audit(entity_id: int, period_id: int, doc_id: int, amount: int) -> Audit:
    """A finding that clears the publication gate, so its amount is published.

    ``seed_source_doc`` carries a real URL, which is what
    ``publishable_audit_criterion()`` requires.
    """
    return Audit(
        entity_id=entity_id,
        period_id=period_id,
        finding_text=f"Unsupported expenditure KES {amount:,}",
        severity=Severity.CRITICAL,
        source_document_id=doc_id,
        query_type="financial_audit",
        amount=Decimal(amount),
        status="Unresolved",
        audit_year=2024,
    )


@pytest.fixture()
def period(db_session, seed_country) -> FiscalPeriod:
    fp = FiscalPeriod(
        id=401,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()
    return fp


@pytest.fixture()
def counted_and_uncounted(db_session, seed_country, seed_source_doc, period):
    """Kwale has no census row; Nairobi and Lamu do.

    Kwale ("002") is the county under test. Nairobi ("001") is the control — a
    fix that nulled every county's population would satisfy the absence
    assertions and break the site. Lamu ("005") exists so that the "<500k"
    bracket Kwale used to be filed under has a real member with a published
    flagged amount: without it, ``population_bracket_avg`` would be ``None``
    before the fix as well as after, and the assertion would not be able to
    tell the two apart.
    """
    nairobi = _entity(seed_country, eid=401, name="Nairobi")
    kwale = _entity(seed_country, eid=402, name="Kwale")
    lamu = _entity(seed_country, eid=405, name="Lamu")
    db_session.add_all([nairobi, kwale, lamu])
    db_session.flush()

    db_session.add_all(
        [
            PopulationData(
                entity_id=nairobi.id,
                year=2019,
                total_population=NAIROBI_CENSUS_2019,
                source_document_id=seed_source_doc.id,
            ),
            PopulationData(
                entity_id=lamu.id,
                year=2019,
                total_population=LAMU_CENSUS_2019,
                source_document_id=seed_source_doc.id,
            ),
            # Kwale deliberately gets no PopulationData row.
        ]
    )

    # A published flagged amount for the one real member of "<500k".
    db_session.add(
        _audit(lamu.id, period.id, seed_source_doc.id, 25_000_000)
    )

    for entity in (nairobi, kwale, lamu):
        db_session.add(
            BudgetLine(
                entity_id=entity.id,
                period_id=period.id,
                category="Health",
                allocated_amount=8_000_000,
                actual_spent=6_000_000,
                currency="KES",
                source_document_id=seed_source_doc.id,
            )
        )

    db_session.commit()
    return {"nairobi": nairobi, "kwale": kwale, "lamu": lamu}


class TestCountySummaryPopulationAbsence:
    """GET /api/v1/counties/{id}/summary."""

    def test_uncounted_county_is_served_as_null(self, client, counted_and_uncounted):
        response = client.get("/api/v1/counties/002/summary")
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["county_name"] == "Kwale"
        assert body["population"] is None, (
            "a county with no PopulationData row was summarised as "
            f"population={body['population']!r}; 0 states that nobody lives "
            "there, which is a claim no source made"
        )

    def test_counted_county_still_reports_its_census(
        self, client, counted_and_uncounted
    ):
        response = client.get("/api/v1/counties/001/summary")
        assert response.status_code == 200, response.text
        assert response.json()["population"] == NAIROBI_CENSUS_2019


class TestAccountabilityPopulationBracket:
    """GET /api/v1/counties/{id}/accountability — peer_comparison."""

    def test_uncounted_county_has_no_bracket(self, client, counted_and_uncounted):
        response = client.get("/api/v1/counties/002/accountability")
        assert response.status_code == 200, response.text

        peer = response.json()["peer_comparison"]
        assert peer["population_bracket"] is None, (
            "a county with no PopulationData row was placed in bracket "
            f"{peer['population_bracket']!r}. Bucketing on 0 files an "
            "uncounted county under Kenya's smallest bracket, and the county "
            "page then prints 'vs <500k Average' over it"
        )

    def test_bracket_average_is_withheld_with_the_bracket(
        self, client, counted_and_uncounted
    ):
        """No bracket means no peer group, so there is no average to publish."""
        response = client.get("/api/v1/counties/002/accountability")
        assert response.status_code == 200, response.text

        peer = response.json()["peer_comparison"]
        assert peer["population_bracket_avg"] is None, (
            "an uncounted county was compared against the average flagged "
            f"amount of {peer['population_bracket_avg']!r} — the average of a "
            "peer group it was assigned to on the strength of a 0"
        )

    def test_counted_county_still_gets_its_bracket(
        self, client, counted_and_uncounted
    ):
        response = client.get("/api/v1/counties/001/accountability")
        assert response.status_code == 200, response.text
        assert response.json()["peer_comparison"]["population_bracket"] == ">2M"


@pytest.fixture()
def uncounted_peer(db_session, seed_country, seed_source_doc, period):
    """Lamu is counted and small; one of its "peers" has no census row at all.

    Kwale here is a genuine "<500k" peer with a published flagged amount of
    KES 1M. Tana River has no PopulationData row and a flagged amount of
    KES 99M — two orders of magnitude apart, so whether it is counted into
    Lamu's bracket average is unmistakable in the number.
    """
    lamu = _entity(seed_country, eid=505, name="Lamu")
    kwale = _entity(seed_country, eid=502, name="Kwale")
    tana = _entity(seed_country, eid=504, name="Tana River")
    db_session.add_all([lamu, kwale, tana])
    db_session.flush()

    db_session.add_all(
        [
            PopulationData(
                entity_id=lamu.id,
                year=2019,
                total_population=LAMU_CENSUS_2019,
                source_document_id=seed_source_doc.id,
            ),
            PopulationData(
                entity_id=kwale.id,
                year=2019,
                total_population=200_000,
                source_document_id=seed_source_doc.id,
            ),
            # Tana River deliberately gets no PopulationData row.
        ]
    )
    db_session.add_all(
        [
            _audit(kwale.id, period.id, seed_source_doc.id, 1_000_000),
            _audit(tana.id, period.id, seed_source_doc.id, 99_000_000),
        ]
    )
    db_session.commit()
    return {"lamu": lamu, "kwale": kwale, "tana": tana}


class TestBracketPeersExcludeUncountedCounties:
    """The other side of the same bucket: peers whose size is unknown."""

    def test_uncounted_peer_does_not_join_the_smallest_bracket(
        self, client, uncounted_peer
    ):
        response = client.get("/api/v1/counties/005/accountability")
        assert response.status_code == 200, response.text

        peer = response.json()["peer_comparison"]
        assert peer["population_bracket"] == "<500k"
        assert peer["population_bracket_avg"] == 1_000_000, (
            "the '<500k' bracket average was "
            f"{peer['population_bracket_avg']!r}. A peer with no census row "
            "bucketed at 0 and joined the smallest bracket, so a county of "
            "unknown size was averaged into the figure Lamu is measured "
            "against"
        )


class TestEnhancedFallbackPopulation:
    """``transform_county_data_for_frontend`` — the enhanced-API fallback.

    Reached only when the DB path in ``/api/v1/counties/{id}`` raises. The
    endpoint's DB path already answers ``null`` for an uncounted county; the
    fallback answered 0, so one endpoint had two conventions for absence.
    """

    def test_absent_population_is_not_zero(self):
        from main import transform_county_data_for_frontend

        mapped = transform_county_data_for_frontend(
            {
                "county": "Kwale",
                "basic_info": {"budget_2025": 3_900_690_000},
                "financial_metrics": {},
                "audit_information": {},
            },
            "002",
        )
        assert mapped["population"] is None, (
            "the fallback manufactured "
            f"population={mapped['population']!r} for a payload that carries "
            "no population at all"
        )

    def test_present_population_is_passed_through(self):
        from main import transform_county_data_for_frontend

        mapped = transform_county_data_for_frontend(
            {
                "county": "Kwale",
                "basic_info": {"population": 866_820},
                "financial_metrics": {},
                "audit_information": {},
            },
            "002",
        )
        assert mapped["population"] == 866_820

    def test_endpoint_serves_the_fallback_when_the_db_path_raises(self, client):
        """Proves the null reaches the wire, not just the transform."""
        from unittest.mock import patch

        async def _fake_county_data(county_name: str):
            return {
                "county": county_name,
                "basic_info": {"budget_2025": 3_900_690_000},
                "financial_metrics": {},
                "audit_information": {},
            }

        def _boom():
            raise RuntimeError("DB path unavailable")

        with patch("main.get_db", _boom), patch(
            "main.InternalAPIClient.get_county_data", _fake_county_data
        ):
            response = client.get("/api/v1/counties/002")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "Kwale"
        assert body["population"] is None, (
            "the enhanced-API fallback served "
            f"population={body['population']!r} from a payload with no "
            "population; the DB path on this same endpoint serves null"
        )
