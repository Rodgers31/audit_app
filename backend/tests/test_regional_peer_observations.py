"""Regional percentages require the declared measure, a year and a provider."""
from datetime import datetime, timezone

import httpx
import pytest
import main
from models import ImfWeoObservation


@pytest.fixture(autouse=True)
def isolated_peers(monkeypatch):
    monkeypatch.setattr(
        main, "_peers_cache", {"ts": 0.0, "data": None, "reference_year": None}
    )


def providers(monkeypatch, imf=None, wb=None, fail=None):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if fail and fail in url:
            raise httpx.ConnectError("synthetic provider unavailable")
        if "imf.org" in url:
            body = {"values": {"GGXWDG_NGDP": imf or {}}}
        else:
            indicator = url.split("/indicator/")[1].split("?")[0]
            body = [
                {"pages": 1},
                [
                    {"indicator": {"id": indicator}, **row}
                    for row in (wb or {}).get(indicator, [])
                ],
            ]
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(main.httpx, "get", get)
    return calls


def observation(iso, value, year="2024"):
    return {"countryiso3code": iso, "value": value, "date": year}


def test_empty_providers_publish_reasoned_absence_not_static_percentages(monkeypatch):
    providers(monkeypatch)
    rows = main._get_regional_peers(reference_year=2025)
    assert len(rows) == 5
    for row in rows:
        for column in main._PEER_COLUMN_BASIS:
            assert row[column] is None
            assert row[column + "_absent_reason"] == "no_observation"
            assert row[column + "_source"] is None
            assert row[column + "_year"] is None


def test_supported_partial_observations_keep_years_sources_and_zero(monkeypatch):
    calls = providers(
        monkeypatch,
        imf={"KEN": {"2025": 99}, "RWA": {"2025": 0, "2031": 88}},
        wb={
            "GC.XPN.INTP.RV.ZS": [
                observation("RWA", 0),
                observation("KEN", 12, "2023"),
            ],
            "DT.DOD.DECT.GN.ZS": [observation("RWA", 2, "2025")],
            "GC.DOD.TOTL.GD.ZS": [observation("ETH", 43, "2025")],
        },
    )
    rows = main._get_regional_peers(kenya_debt_to_gdp=0, reference_year=2025)
    kenya, ethiopia, _, _, rwanda = rows
    assert kenya["debt_to_gdp"] == rwanda["debt_to_gdp"] == 0
    assert kenya["debt_to_gdp_source"]["origin"] == "accepted_kenya_anchor"
    assert rwanda["debt_to_gdp_source"]["indicator"] == "GGXWDG_NGDP"
    assert rwanda["debt_to_gdp_year"] == 2025
    assert rwanda["interest_payments_pct_revenue"] == 0
    assert rwanda["interest_payments_pct_revenue_year"] == 2024
    assert rwanda["external_debt_pct_gni_year"] == 2025
    assert ethiopia["debt_to_gdp"] is None  # WB central govt is another measure.
    assert not any("GC.DOD.TOTL.GD.ZS" in url for url in calls)


def test_no_reference_year_does_not_fetch_or_publish_debt_even_with_anchor(monkeypatch):
    calls = providers(monkeypatch)
    rows = main._get_regional_peers(0)
    assert all(row["debt_to_gdp"] is None for row in rows)
    assert all(row["debt_to_gdp_absent_reason"] == "no_reference_year" for row in rows)
    assert not any("imf.org" in url for url in calls)


def test_success_cache_copies_rows_and_never_stores_request_anchor(monkeypatch):
    calls = providers(monkeypatch, imf={"KEN": {"2025": 23}, "RWA": {"2025": 0}})
    first = main._get_regional_peers(45, 2025)
    first[0]["debt_to_gdp_source"]["publisher"] = "mutated by consumer"
    first[0]["country"] = "mutated by consumer"
    second = main._get_regional_peers(None, 2025)
    assert second[0]["country"] == "Kenya"
    assert second[0]["debt_to_gdp"] == 23
    assert second[0]["debt_to_gdp_source"]["publisher"] == "IMF World Economic Outlook"
    assert len(calls) == 3


def test_failed_provider_retries_without_using_expired_success(monkeypatch):
    providers(monkeypatch, imf={"KEN": {"2025": 23}})
    main._get_regional_peers(reference_year=2025)
    monkeypatch.setitem(main._peers_cache, "ts", 0)
    providers(monkeypatch, fail="imf.org")
    failed = main._get_regional_peers(reference_year=2025)
    assert failed[0]["debt_to_gdp"] is None
    assert failed[0]["debt_to_gdp_absent_reason"] == "provider_unavailable"
    providers(monkeypatch, imf={"KEN": {"2025": 0}})
    assert main._get_regional_peers(reference_year=2025)[0]["debt_to_gdp"] == 0


def test_reference_year_changes_invalidate_success_cache(monkeypatch):
    calls = providers(monkeypatch, imf={"KEN": {"2024": 10, "2025": 0}})
    assert main._get_regional_peers(reference_year=2024)[0]["debt_to_gdp"] == 10
    assert main._get_regional_peers(reference_year=2025)[0]["debt_to_gdp"] == 0
    assert len(calls) == 6


@pytest.mark.parametrize(
    "bad", [True, "12", -1, float("nan"), float("inf"), float("-inf"), {}, []]
)
def test_invalid_provider_numbers_are_absent_and_do_not_poison_http(
    monkeypatch, bad, client
):
    # NaN/inf are accepted by Python's JSON parser but must never reach JSON output.
    # httpx disallows constructing nonfinite JSON; use content for those cases.
    import json

    def transport(url, **kwargs):
        body = (
            {"values": {"GGXWDG_NGDP": {"RWA": {"2025": bad}, "KEN": {"2025": 0}}}}
            if "imf.org" in url
            else [
                {"pages": 1},
                [
                    {
                        **observation("RWA", bad),
                        "indicator": {"id": url.split("/indicator/")[1].split("?")[0]},
                    },
                    {
                        **observation("KEN", 0),
                        "indicator": {"id": url.split("/indicator/")[1].split("?")[0]},
                    },
                ],
            ]
        )
        return httpx.Response(
            200, content=json.dumps(body), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(main.httpx, "get", transport)
    monkeypatch.setattr(
        main, "_latest_imf_debt_to_gdp", lambda db: (0, 2025, "synthetic")
    )
    monkeypatch.setattr(
        main, "_published_debt_projections", lambda db: ([], None, "synthetic")
    )
    response = client.get("/api/v1/debt/sustainability")
    assert response.status_code == 200, response.text
    kenya, _, _, _, rwanda = response.json()["regional_peers"]
    for column in main._PEER_COLUMN_BASIS:
        assert rwanda[column] is None
        assert rwanda[column + "_absent_reason"] == "invalid_observation"
        assert kenya[column] == 0


def test_actual_registered_http_no_data_then_provider_recovery(monkeypatch, client):
    providers(monkeypatch, fail="worldbank.org")
    first = client.get("/api/v1/debt/sustainability")
    assert first.status_code == 200 and first.json()["status"] == "no_data"
    assert all(row["debt_to_gdp"] is None for row in first.json()["regional_peers"])
    assert (
        first.json()["regional_peers"][0]["interest_payments_pct_revenue_absent_reason"]
        == "provider_unavailable"
    )
    providers(monkeypatch, wb={"GC.XPN.INTP.RV.ZS": [observation("KEN", 0)]})
    second = client.get("/api/v1/debt/sustainability")
    assert second.status_code == 200
    assert second.json()["regional_peers"][0]["interest_payments_pct_revenue"] == 0


def test_actual_registered_http_populated_kenya_anchor(monkeypatch, client, db_session):
    db_session.add(
        ImfWeoObservation(
            country_code="KEN",
            indicator="GGXWDG_NGDP",
            year=2025,
            value=0,
            is_projection=False,
            vintage=datetime(2026, 9, 1, tzinfo=timezone.utc),
            source="imf_datamapper",
        )
    )
    db_session.commit()
    providers(monkeypatch, imf={"KEN": {"2025": 44}, "RWA": {"2025": 0}})
    response = client.get("/api/v1/debt/sustainability")
    body = response.json()
    assert response.status_code == 200 and body["status"] == "success", body
    assert body["debt_to_gdp"]["value"] == body["regional_peers"][0]["debt_to_gdp"] == 0
    assert body["regional_peers"][0]["debt_to_gdp_year"] == 2025
    assert body["regional_peers"][4]["debt_to_gdp"] == 0


def test_wrong_world_bank_indicator_is_withheld_in_registered_http(monkeypatch, client):
    providers(
        monkeypatch,
        wb={
            "GC.XPN.INTP.RV.ZS": [
                {**observation("KEN", 42), "indicator": {"id": "GC.DOD.TOTL.GD.ZS"}}
            ],
            "DT.DOD.DECT.GN.ZS": [
                {**observation("KEN", 0), "indicator": {"id": "DT.DOD.DECT.GN.ZS"}}
            ],
        },
    )
    response = client.get("/api/v1/debt/sustainability")
    assert response.status_code == 200
    row = response.json()["regional_peers"][0]
    assert row["interest_payments_pct_revenue"] is None
    assert (
        row["interest_payments_pct_revenue_absent_reason"]
        == "invalid_provider_response"
    )
    assert row["external_debt_pct_gni"] == 0


@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {"unexpected": "schema"},
        {"values": {}},
        {"values": {"GGXWDG_NGDP": {"KEN": False}}},
    ],
)
def test_malformed_imf_response_is_not_cached_as_no_observation(monkeypatch, malformed):
    def get(url, **kwargs):
        body = malformed if "imf.org" in url else [{"pages": 1}, []]
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(main.httpx, "get", get)
    first = main._get_regional_peers(reference_year=2025)
    assert first[0]["debt_to_gdp_absent_reason"] == "invalid_provider_response"
    calls = providers(monkeypatch, imf={"KEN": {"2025": 0}})
    assert main._get_regional_peers(reference_year=2025)[0]["debt_to_gdp"] == 0
    assert calls


def test_unrepresentable_provider_integer_withholds_only_that_cell(monkeypatch, client):
    import json

    def get(url, **kwargs):
        body = (
            {"values": {"GGXWDG_NGDP": {"RWA": {"2025": 10**400}}}}
            if "imf.org" in url
            else [{"pages": 1}, []]
        )
        return httpx.Response(
            200, content=json.dumps(body), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(main.httpx, "get", get)
    monkeypatch.setattr(
        main, "_latest_imf_debt_to_gdp", lambda db: (0, 2025, "synthetic")
    )
    monkeypatch.setattr(
        main, "_published_debt_projections", lambda db: ([], None, "synthetic")
    )
    response = client.get("/api/v1/debt/sustainability")
    assert response.status_code == 200, response.text
    kenya, _, _, _, rwanda = response.json()["regional_peers"]
    assert kenya["debt_to_gdp"] == 0
    assert rwanda["debt_to_gdp"] is None
    assert rwanda["debt_to_gdp_absent_reason"] == "invalid_observation"


def test_legacy_static_cache_is_not_a_supported_observation(monkeypatch):
    monkeypatch.setattr(
        main,
        "_peers_cache",
        {
            "ts": main.time.time(),
            "reference_year": 2025,
            "data": [
                {"country": "Kenya", "debt_to_gdp": 68.0, "debt_to_gdp_year": None}
            ],
        },
    )
    calls = providers(monkeypatch)
    rows = main._get_regional_peers(reference_year=2025)
    assert len(rows) == 5 and rows[0]["debt_to_gdp"] is None
    assert len(calls) == 3


def test_successful_empty_read_is_cached_until_ttl_then_refetched(monkeypatch):
    calls = providers(monkeypatch)
    first = main._get_regional_peers(reference_year=2025)
    assert first[0]["debt_to_gdp_absent_reason"] == "no_observation"
    main._get_regional_peers(reference_year=2025)
    assert len(calls) == 3
    monkeypatch.setitem(
        main._peers_cache, "ts", main.time.time() - main._PEERS_CACHE_TTL
    )
    calls = providers(monkeypatch, imf={"KEN": {"2025": 0}})
    assert main._get_regional_peers(reference_year=2025)[0]["debt_to_gdp"] == 0
    assert len(calls) == 3


def test_complete_http_cells_all_carry_their_measure_year_and_source(
    monkeypatch, client
):
    monkeypatch.setattr(
        main, "_latest_imf_debt_to_gdp", lambda db: (0, 2025, "synthetic")
    )
    monkeypatch.setattr(
        main, "_published_debt_projections", lambda db: ([], None, "synthetic")
    )
    providers(
        monkeypatch,
        imf={iso: {"2025": i} for i, iso in enumerate(main._EAC_COUNTRIES)},
        wb={
            indicator: [
                observation(iso, i) for i, iso in enumerate(main._EAC_COUNTRIES)
            ]
            for indicator in main._WB_INDICATORS.values()
        },
    )
    response = client.get("/api/v1/debt/sustainability")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    for row in body["regional_peers"]:
        for column, basis in body["regional_peers_basis"].items():
            assert row[column] is not None
            assert row[column + "_absent_reason"] is None
            assert row[column + "_year"] == (2025 if column == "debt_to_gdp" else 2024)
            assert row[column + "_source"]["indicator"] == basis["indicator"]
            assert row[column + "_source"]["publisher"] == basis["publisher"]


@pytest.mark.parametrize("missing", ["countryiso3code", "value"])
def test_world_bank_missing_required_row_field_is_not_cached(monkeypatch, missing):
    malformed = observation("KEN", 12)
    del malformed[missing]
    providers(monkeypatch, wb={"GC.XPN.INTP.RV.ZS": [malformed]})
    first = main._get_regional_peers(reference_year=2025)
    assert (
        first[0]["interest_payments_pct_revenue_absent_reason"]
        == "invalid_provider_response"
    )
    calls = providers(monkeypatch, wb={"GC.XPN.INTP.RV.ZS": [observation("KEN", 0)]})
    assert (
        main._get_regional_peers(reference_year=2025)[0][
            "interest_payments_pct_revenue"
        ]
        == 0
    )
    assert calls
