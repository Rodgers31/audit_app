"""/budget/enhanced economic_context: newest national row, row-declared label.

Issue #232. Growth and unemployment were read from
``db.query(EconomicIndicator).all()`` with no ORDER BY and no entity scope, so
the year shown was whichever row came back last; production served
unemployment 5.7 against a newest observation of 5.4. The inflation caption
was the literal "KNBS Consumer Price Index" whatever row was read.

SQLite returns an unordered SELECT in insertion order, so inserting the
NEWEST row first reproduces "last row wins" deterministically.
"""

from __future__ import annotations

from datetime import datetime

from models import EconomicIndicator, Entity, EntityType

WB = "World Bank, World Development Indicators"
CBK = "KNBS CPI, via Central Bank of Kenya"


def _ind(kind, day, value, *, label=None, measure=None, entity_id=None):
    meta = {}
    if label:
        meta["source_label"] = label
    if measure:
        meta["measure"] = measure
    return EconomicIndicator(
        indicator_type=kind,
        indicator_date=datetime.fromisoformat(day),
        value=value,
        entity_id=entity_id,
        unit="percent",
        meta=meta,
    )


def _ctx(client):
    resp = client.get("/api/v1/budget/enhanced")
    assert resp.status_code == 200
    return resp.json()["economic_context"]


def test_gdp_growth_is_the_newest_year_not_the_last_row(client, db_session):
    db_session.add_all(
        [
            _ind("gdp_growth_rate", "2025-12-31", 4.6, label=WB),
            _ind("gdp_growth_rate", "2024-12-31", 4.7, label=WB),
        ]
    )
    db_session.commit()
    ec = _ctx(client)
    assert ec["gdp_growth_pct"] == 4.6
    assert ec["gdp_growth_as_of"].startswith("2025-12-31")
    assert ec["gdp_growth_source"] == WB


def test_unemployment_is_the_newest_year_not_the_last_row(client, db_session):
    db_session.add_all(
        [
            _ind("unemployment_rate", "2025-12-31", 5.4, label=WB),
            _ind("unemployment_rate", "2021-12-31", 5.7, label=WB),
        ]
    )
    db_session.commit()
    assert _ctx(client)["unemployment_pct"] == 5.4


def test_a_county_row_never_stands_in_for_the_national_figure(
    client, db_session, seed_country
):
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kisumu",
        slug="kisumu",
    )
    db_session.add(county)
    db_session.flush()
    db_session.add_all(
        [
            _ind("gdp_growth_rate", "2025-12-31", 4.6, label=WB),
            _ind("gdp_growth_rate", "2026-06-30", 9.9, entity_id=county.id),
        ]
    )
    db_session.commit()
    assert _ctx(client)["gdp_growth_pct"] == 4.6


def test_inflation_caption_is_the_rows_own_label(client, db_session):
    db_session.add(
        _ind(
            "inflation_rate",
            "2025-12-31",
            4.1,
            label=WB,
            measure="CPI inflation, annual average",
        )
    )
    db_session.commit()
    ec = _ctx(client)
    assert ec["inflation_pct"] == 4.1
    assert ec["inflation_source"] == WB
    assert ec["inflation_measure"] == "CPI inflation, annual average"


def test_monthly_headline_beats_an_older_annual_average(client, db_session):
    db_session.add_all(
        [
            _ind("inflation_rate", "2025-12-31", 4.1, label=WB),
            _ind(
                "inflation_rate_12m",
                "2026-08-31",
                6.59,
                label=CBK,
                measure="12-month CPI inflation",
            ),
        ]
    )
    db_session.commit()
    ec = _ctx(client)
    assert ec["inflation_pct"] == 6.59
    assert ec["inflation_as_of"].startswith("2026-08-31")
    assert ec["inflation_source"] == CBK
    assert ec["inflation_measure"] == "12-month CPI inflation"


def test_on_the_same_date_the_monthly_headline_wins(client, db_session):
    # Dec 2025: 12-month 4.49 vs the World Bank's annual average 4.07.
    db_session.add_all(
        [
            _ind("inflation_rate", "2025-12-31", 4.07, label=WB),
            _ind("inflation_rate_12m", "2025-12-31", 4.49, label=CBK),
        ]
    )
    db_session.commit()
    assert _ctx(client)["inflation_pct"] == 4.49


def test_a_newer_annual_figure_is_not_hidden_behind_a_stalled_monthly_one(
    client, db_session
):
    db_session.add_all(
        [
            _ind("inflation_rate_12m", "2026-03-31", 4.39, label=CBK),
            _ind("inflation_rate", "2026-12-31", 5.1, label=WB),
        ]
    )
    db_session.commit()
    ec = _ctx(client)
    assert ec["inflation_pct"] == 5.1
    assert ec["inflation_source"] == WB


def test_an_undeclared_source_is_absent_not_guessed(client, db_session):
    db_session.add_all(
        [
            _ind("inflation_rate", "2025-12-31", 4.1),
            _ind("total_national_gdp", "2025-12-31", 17577557),
        ]
    )
    db_session.commit()
    ec = _ctx(client)
    assert ec["inflation_pct"] == 4.1
    assert ec["inflation_source"] is None
    assert ec["gdp_source"] is None
