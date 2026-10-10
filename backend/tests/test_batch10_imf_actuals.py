"""Actual-only IMF headlines through real SQL queries and FastAPI callers.

All amounts and citations below are synthetic. SQLite normalizes some hostile
values, so those cases retain the value in the real ORM identity map with
autoflush disabled. No IMF/provider transport or application startup is used.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal

import pytest
from models import (
    Base,
    DebtCategory,
    DebtTimeline,
    Entity,
    EntityType,
    FiscalSummary,
    GDPData,
    ImfWeoObservation,
    Loan,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

VINTAGE = datetime(2026, 10, 1)
OLDER = datetime(2026, 4, 1)


@pytest.fixture()
def db_session(tmp_path):
    """This module owns a separate file database per case, including API cases."""
    path = tmp_path / "batch10-imf-actuals.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def inert_peers(monkeypatch):
    # Retain the real peer orchestration/reference-year behavior; replace only
    # external provider readers and isolate the shared cache between cases.
    import main

    monkeypatch.setattr(main, "_imf_fetch_debt_to_gdp", lambda *a, **kw: {})
    monkeypatch.setattr(main, "_wb_fetch_indicator", lambda *a, **kw: {})
    main._peers_cache.update(ts=0.0, data=None)
    yield
    main._peers_cache.update(ts=0.0, data=None)


def observation(db, year=2028, value=69.3, projection=True, **kwargs):
    fields = dict(
        country_code="KEN",
        indicator="GGXWDG_NGDP",
        year=year,
        value=value,
        is_projection=projection,
        vintage=VINTAGE,
        source="imf_datamapper",
    )
    fields.update(kwargs)
    row = ImfWeoObservation(**fields)
    db.add(row)
    db.commit()
    return row


def fiscal(db):
    db.add(
        FiscalSummary(
            fiscal_year="FY 2025/26",
            appropriated_budget=100,
            total_revenue=70,
            total_borrowing=30,
            county_allocation=10,
            unit="KES",
            page_ref="PDF p.1",
        )
    )
    db.commit()


def register(db, country, source):
    entity = Entity(
        country_id=country.id,
        type=EntityType.NATIONAL,
        canonical_name="Synthetic National Treasury",
        slug="batch10-imf-national",
    )
    db.add(entity)
    db.flush()
    db.add(
        Loan(
            entity_id=entity.id,
            lender="Synthetic Treasury Bonds",
            debt_category=DebtCategory.DOMESTIC_BONDS,
            principal=60,
            outstanding=60,
            issue_date=datetime(2025, 1, 1),
            currency="KES",
            source_document_id=source.id,
        )
    )
    db.commit()


def response(client, route):
    result = client.get(f"/api/v1/{route}")
    assert result.status_code == 200, result.text
    return result.json()


def test_projection_only_helper_is_absent(db_session):
    import main

    observation(db_session)
    assert main._latest_imf_debt_to_gdp(db_session) is None


def test_projection_only_fiscal_api_is_absent(client, db_session):
    fiscal(db_session)
    observation(db_session)
    body = response(client, "fiscal/summary")
    assert body["status"] == "success"
    anchor = body["debt_anchor"]
    assert anchor["debt_to_gdp_pct"] is None
    assert anchor["debt_to_gdp_year"] is None
    assert anchor["above_anchor"] is None
    assert anchor["comparison_absent_reason"]
    assert anchor["debt_to_gdp_vintage"] is None
    assert anchor["debt_to_gdp_source"] is None
    assert anchor["debt_to_gdp_absent_reason"]


@pytest.mark.parametrize("ratio", [Decimal("61.24"), Decimal("0")])
def test_valid_actual_tuple_and_newest_year(db_session, ratio):
    import main

    # Deliberately insert the greatest year first, then older actuals and a
    # forecast: order is provided by the real SQL query, not this input list.
    observation(db_session, year=2025, value=ratio, projection=False)
    observation(db_session, year=2028)
    observation(db_session, year=2023, value=50, projection=False)
    assert main._latest_imf_debt_to_gdp(db_session) == (
        round(float(ratio), 1),
        2025,
        VINTAGE.isoformat(),
    )


def test_newest_vintage_never_substitutes_older_actual(db_session):
    import main

    observation(db_session, year=2025, value=61.2, projection=False, vintage=OLDER)
    observation(db_session)
    assert main._latest_imf_debt_to_gdp(db_session) is None


@pytest.mark.parametrize("shape", ["empty", "other_country", "other_indicator"])
def test_no_matching_rows_are_absent(db_session, shape):
    import main

    if shape == "other_country":
        observation(db_session, country_code="UGA", projection=False)
    elif shape == "other_indicator":
        observation(db_session, indicator="NGDPD", projection=False)
    assert main._latest_imf_debt_to_gdp(db_session) is None


def test_vintage_selection_remains_country_wide(db_session):
    import main

    observation(db_session, year=2025, projection=False, vintage=OLDER)
    observation(db_session, indicator="NGDPD")
    assert main._latest_imf_debt_to_gdp(db_session) is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        float("nan"),
        float("inf"),
        float("-inf"),
        -1,
        True,
        False,
        "61.2",
        "bad",
        {},
        [],
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_actual_is_absent_in_real_helper(db_session, value):
    import main

    row = observation(db_session, year=2025, value=61.2, projection=False)
    row.value = value
    assert main._latest_imf_debt_to_gdp(db_session) is None


@pytest.mark.parametrize("flag", [None, 0, 1, "", "false", "true", [], {}])
def test_unknown_projection_flags_are_not_actuals(db_session, flag):
    import main

    row = observation(db_session, year=2025, projection=False)
    row.is_projection = flag
    assert main._latest_imf_debt_to_gdp(db_session) is None


def test_invalid_newest_actual_keeps_valid_older_actual_in_same_vintage(db_session):
    import main

    observation(db_session, year=2024, value=61.2, projection=False)
    row = observation(db_session, year=2025, value=62.2, projection=False)
    row.value = float("nan")
    assert main._latest_imf_debt_to_gdp(db_session) == (61.2, 2024, VINTAGE.isoformat())


@pytest.mark.parametrize("query_number", [1, 2])
def test_query_failure_is_absent_and_logged(
    db_session, monkeypatch, caplog, query_number
):
    import main

    observation(db_session)
    real_query = db_session.query
    count = 0

    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == query_number:
            raise RuntimeError("batch10-imf synthetic query failure")
        return real_query(*args, **kwargs)

    monkeypatch.setattr(db_session, "query", fail)
    assert main._latest_imf_debt_to_gdp(db_session) is None
    assert "IMF debt-to-GDP lookup failed" in caplog.text
    assert "synthetic query failure" in caplog.text


def test_projection_only_sustainability_keeps_published_series(client, db_session):
    observation(db_session)
    body = response(client, "debt/sustainability")
    assert body["debt_to_gdp"] is None
    assert body["debt_to_gdp_absent_reason"]
    assert body["projections"] == [
        {"year": 2028, "projected_debt_to_gdp": 69.3, "is_published_projection": True}
    ]
    assert body["projections_source"] == "IMF World Economic Outlook (GGXWDG_NGDP)"
    assert body["projections_absent_reason"] is None
    assert body["regional_peers_basis"]["debt_to_gdp"]["reference_year"] is None


def test_projection_only_sustainability_uses_declared_cbk_fallback(client, db_session):
    observation(db_session)
    db_session.add(
        DebtTimeline(
            year=2024, external=20, domestic=40, total=60, gdp_ratio=60, unit="KES"
        )
    )
    db_session.commit()
    body = response(client, "debt/sustainability")
    ratio = body["debt_to_gdp"]
    assert (ratio["value"], ratio["year"], ratio["vintage"]) == (60, 2024, None)
    assert "Central government" in ratio["basis"]
    assert ratio["source"] == "CBK Annual Reports / National Treasury BPS"
    assert "present-value" in ratio["assessment"]
    assert body["regional_peers_basis"]["debt_to_gdp"]["reference_year"] is None


def test_projection_only_national_uses_declared_world_bank_fallback(
    client, db_session, seed_country, seed_source_doc
):
    register(db_session, seed_country, seed_source_doc)
    observation(db_session)
    db_session.add(GDPData(year=2024, gdp_value=100))
    db_session.commit()
    body = response(client, "debt/national")["data"]
    assert body["debt_to_gdp_ratio"] == 60
    assert body["debt_to_gdp_year"] == 2024
    assert body["debt_to_gdp_source"] == "CBK / World Bank"
    assert "approximate" in body["debt_to_gdp_basis"]
    assert "World Bank, 2024" in body["debt_to_gdp_basis"]
    assert body["debt_to_gdp_vintage"] is None
    assert body["debt_to_gdp_absent_reason"] is None


def test_projection_only_national_without_gdp_is_absent(
    client, db_session, seed_country, seed_source_doc
):
    register(db_session, seed_country, seed_source_doc)
    observation(db_session)
    body = response(client, "debt/national")["data"]
    assert body["debt_to_gdp_ratio"] is None
    assert body["debt_to_gdp_year"] is None
    assert body["debt_to_gdp_source"] is None
    assert body["debt_to_gdp_vintage"] is None
    assert body["debt_to_gdp_absent_reason"]


def test_actual_consistency_across_all_three_apis(
    client, db_session, seed_country, seed_source_doc
):
    register(db_session, seed_country, seed_source_doc)
    fiscal(db_session)
    observation(db_session, year=2024, value=61.2, projection=False)
    observation(db_session)
    anchor = response(client, "fiscal/summary")["debt_anchor"]
    national = response(client, "debt/national")["data"]
    sustain = response(client, "debt/sustainability")
    assert (anchor["debt_to_gdp_pct"], anchor["debt_to_gdp_year"]) == (61.2, 2024)
    assert (national["debt_to_gdp_ratio"], national["debt_to_gdp_year"]) == (61.2, 2024)
    assert (sustain["debt_to_gdp"]["value"], sustain["debt_to_gdp"]["year"]) == (
        61.2,
        2024,
    )
    assert sustain["debt_to_gdp"]["vintage"] == VINTAGE.isoformat()
    assert national["debt_to_gdp_source"] == "IMF World Economic Outlook"
    assert anchor["debt_to_gdp_source"] == "IMF World Economic Outlook"
    assert (
        anchor["debt_to_gdp_vintage"]
        == national["debt_to_gdp_vintage"]
        == VINTAGE.isoformat()
    )
    assert anchor["debt_to_gdp_absent_reason"] is None
    assert national["debt_to_gdp_absent_reason"] is None
    assert sustain["debt_to_gdp_absent_reason"] is None
    assert anchor["above_anchor"] is None
    assert anchor["comparison_absent_reason"]
    assert sustain["regional_peers_basis"]["debt_to_gdp"]["reference_year"] == 2024
    assert sustain["regional_peers"][0]["debt_to_gdp"] == 61.2
    assert sustain["projections"][0]["year"] == 2028


def test_concurrent_reads_select_same_actual(db_session):
    import main

    observation(db_session, year=2025, value=61.2, projection=False)
    observation(db_session)
    factory = sessionmaker(bind=db_session.get_bind())

    def read(_):
        with factory() as session:
            return main._latest_imf_debt_to_gdp(session)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(read, range(9)))
    assert results == [(61.2, 2025, VINTAGE.isoformat())] * 9


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_actual_fiscal_direct_call_is_absent(db_session, value):
    import main

    fiscal(db_session)
    row = observation(db_session, year=2025, value=61.2, projection=False)
    row.value = value
    body = asyncio.run(main.get_fiscal_summary(db_session))
    assert body["debt_anchor"]["debt_to_gdp_pct"] is None


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_invalid_fallback_gdp_is_absent(
    client, db_session, seed_country, seed_source_doc, value
):
    register(db_session, seed_country, seed_source_doc)
    observation(db_session)
    row = GDPData(year=2024, gdp_value=100)
    db_session.add(row)
    db_session.commit()
    row.gdp_value = value
    body = response(client, "debt/national")["data"]
    assert body["debt_to_gdp_ratio"] is None
    assert body["debt_to_gdp_absent_reason"]


def test_finite_positive_gdp_overflow_is_absent(
    client, db_session, seed_country, seed_source_doc
):
    register(db_session, seed_country, seed_source_doc)
    observation(db_session)
    row = GDPData(year=2024, gdp_value=100)
    db_session.add(row)
    db_session.commit()
    row.gdp_value = Decimal("1e-320")
    body = response(client, "debt/national")["data"]
    assert body["debt_to_gdp_ratio"] is None
    assert body["debt_sustainability"]["debt_to_gdp"] is None
    assert body["debt_to_gdp_absent_reason"]


def test_missing_imf_table_preserves_sustainability_no_data(client, db_session):
    ImfWeoObservation.__table__.drop(db_session.get_bind())
    body = response(client, "debt/sustainability")
    assert body["status"] == "no_data"
    assert body["debt_to_gdp"] is None
    assert body["debt_to_gdp_absent_reason"]
    assert body["projections"] == []
    assert body["projections_absent_reason"] == "no_published_projection_seeded"


def test_catalog_failure_is_still_an_api_error(client, monkeypatch):
    import sqlalchemy

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic catalog failure")

    monkeypatch.setattr(sqlalchemy, "inspect", fail)
    result = client.get("/api/v1/debt/sustainability")
    assert result.status_code == 500


def test_missing_all_series_has_explicit_absence(client):
    body = response(client, "debt/sustainability")
    assert body["status"] == "no_data"
    assert body["debt_to_gdp"] is None
    assert body["debt_to_gdp_absent_reason"]
    assert body["projections"] == []
    assert body["projections_absent_reason"] == "no_published_projection_seeded"
    national = response(client, "debt/national")["data"]
    assert national["debt_to_gdp_ratio"] is None
    assert national["debt_to_gdp_year"] is None
    assert national["debt_to_gdp_vintage"] is None
    assert national["debt_to_gdp_absent_reason"] == "not_yet_seeded"


def test_broader_series_keeps_its_declared_forecast(db_session):
    import main

    observation(db_session)
    observation(db_session, indicator="NGDPD", value=100)
    body = asyncio.run(
        main._get_debt_broader_cached(
            db=db_session, vintage=VINTAGE.isoformat() + "+00:00"
        )
    )
    assert body["timeseries"][0]["debt_to_gdp"] == 69.3
    assert body["timeseries"][0]["is_projection"] is True
    assert body["latest"]["is_projection"] is True
    assert body["vintage"] == VINTAGE.isoformat() + "+00:00"
