"""Independent hostile-input checks of session 3 sustainability changes."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from models import DebtTimeline, FiscalSummary, ImfWeoObservation


@pytest.fixture(autouse=True)
def no_peer_network(monkeypatch):
    import main

    monkeypatch.setattr(main, "_get_regional_peers", lambda **kwargs: [])


def read_response(client):
    import main

    main.clear_all_caches()
    return client.get("/api/v1/debt/sustainability")


def seed_timeline(db_session, source_id=None, **values):
    fields = dict(year=2025, total=100, external=40, domestic=60,
                  gdp_ratio=70, unit="KES", source_document_id=source_id)
    fields.update(values)
    row = DebtTimeline(**fields)
    db_session.add(row)
    db_session.commit()
    return row


def seed_fiscal(db_session, source_id=None, **values):
    fields = dict(fiscal_year="FY 2025/26", total_revenue=100,
                  debt_service_cost=20, page_ref="p.1", unit="KES",
                  source_document_id=source_id, meta=fiscal_input_sources())
    fields.update(values)
    row = FiscalSummary(**fields)
    db_session.add(row)
    db_session.commit()
    return row


def fiscal_input_sources():
    """Synthetic citations, independent for each operand of the test ratio."""
    return {
        "debt_service_source": {
            "title": "Test debt-service report", "url": "https://example.org/debt-service.pdf",
            "page": "p.2",
        },
        "revenue_source": {
            "title": "Test revenue report", "url": "https://example.org/revenue.pdf",
            "page": "p.3",
        },
    }


def test_weo_only_database_is_not_no_data(client, db_session):
    db_session.add_all([
        ImfWeoObservation(country_code="KEN", indicator="GGXWDG_NGDP",
                          year=2025, value=69.3, is_projection=False,
                          vintage=datetime(2026, 4, 1, tzinfo=timezone.utc),
                          source="imf_datamapper"),
        ImfWeoObservation(country_code="KEN", indicator="GGXWDG_NGDP",
                          year=2026, value=71.6, is_projection=True,
                          vintage=datetime(2026, 4, 1, tzinfo=timezone.utc),
                          source="imf_datamapper"),
    ])
    db_session.commit()
    body = read_response(client).json()
    assert body["status"] == "success", body
    assert body["debt_to_gdp"]["value"] == 69.3
    assert body["projections"][0]["projected_debt_to_gdp"] == 71.6


@pytest.mark.parametrize("meta", [
    {"fiscal_framework": {"source": None}},
    {"fiscal_framework": {"source": []}},
    {"fiscal_framework": ["bad-schema"]},
    ["bad-schema"],
    "bad-schema",
])
def test_malformed_metadata_does_not_destroy_other_indicators(
    client, db_session, seed_source_doc, meta
):
    seed_timeline(db_session, seed_source_doc.id)
    seed_fiscal(db_session, seed_source_doc.id, meta=meta)
    response = read_response(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["debt_to_gdp"]["value"] == 70
    assert body["debt_service_to_revenue"] is None, body["debt_service_to_revenue"]
    assert body["debt_service_to_revenue_absent_reason"]


@pytest.mark.parametrize("meta", [None, {}, {"fiscal_framework": None}])
def test_missing_input_source_metadata_withholds_only_ratio(client, db_session, seed_source_doc, meta):
    seed_timeline(db_session, seed_source_doc.id)
    seed_fiscal(db_session, seed_source_doc.id, meta=meta)
    response = read_response(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["debt_to_gdp"]["value"] == 70
    assert body["debt_service_to_revenue"] is None, body["debt_service_to_revenue"]
    assert body["debt_service_to_revenue_absent_reason"]


@pytest.mark.parametrize("source_key", ["debt_service_source", "revenue_source"])
@pytest.mark.parametrize("missing", ["whole_source", "url", "page"])
def test_each_derived_ratio_operand_needs_its_own_source(
    client, db_session, seed_source_doc, source_key, missing
):
    metadata = fiscal_input_sources()
    if missing == "whole_source":
        metadata.pop(source_key)
    else:
        metadata[source_key].pop(missing)
    # The row still has a SourceDocument and a locator. Those alone must
    # not substitute for the missing source of one operand.
    seed_fiscal(db_session, seed_source_doc.id, meta=metadata)
    body = read_response(client).json()
    assert body["debt_service_to_revenue"] is None, body["debt_service_to_revenue"]
    assert body["debt_service_to_revenue_absent_reason"]


def test_sourced_derived_ratio_retains_both_input_citations(client, db_session, seed_source_doc):
    seed_fiscal(db_session, seed_source_doc.id)
    body = read_response(client).json()
    ratio = body["debt_service_to_revenue"]
    assert ratio["value"] == 20
    assert ratio["debt_service_source"] == fiscal_input_sources()["debt_service_source"]
    assert ratio["revenue_source"] == fiscal_input_sources()["revenue_source"]


def test_absent_revenue_is_nonapplicable_to_budget_only_provenance(
    client, db_session, seed_source_doc
):
    seed_fiscal(db_session, seed_source_doc.id, appropriated_budget=100,
                total_revenue=None, meta={"budget_basis_source": {
                    "title": seed_source_doc.title, "url": seed_source_doc.url,
                    "page": "p.1",
                }})
    assert read_response(client).json()["debt_service_to_revenue"] is None
    response = client.get("/api/v1/provenance/verify/fiscal_summaries?year=2025")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] == "KES 100 appropriated budget (FY 2025/26)"
    assert body["source_url"] == seed_source_doc.url
    assert body["verification_status"] == "publishable"
    assert "not been fetched or validated" in body["reason"]


@pytest.mark.parametrize("field,bad_value", [
    ("gdp_ratio", -1),
    ("gdp_ratio", float("inf")),
    ("gdp_ratio", float("-inf")),
    ("external", -1),
    ("external", 101),
    ("external", float("inf")),
])
def test_bad_debt_numbers_are_absent(client, db_session, seed_source_doc, field, bad_value):
    seed_timeline(db_session, seed_source_doc.id, **{field: bad_value})
    response = read_response(client)
    assert response.status_code == 200, response.text
    body = response.json()
    key = "debt_to_gdp" if field == "gdp_ratio" else "external_debt_share"
    assert body[key] is None, body[key]


@pytest.mark.parametrize("field,bad_value", [
    ("debt_service_cost", -1),
    ("debt_service_cost", float("inf")),
    ("total_revenue", float("inf")),
])
def test_bad_fiscal_numbers_are_absent(client, db_session, seed_source_doc, field, bad_value):
    seed_fiscal(db_session, seed_source_doc.id, **{field: bad_value})
    response = read_response(client)
    assert response.status_code == 200, response.text
    assert response.json()["debt_service_to_revenue"] is None


def test_valid_reported_zero_is_retained(client, db_session, seed_source_doc):
    seed_timeline(db_session, seed_source_doc.id, gdp_ratio=0, external=0)
    seed_fiscal(db_session, seed_source_doc.id, debt_service_cost=0)
    response = read_response(client)
    assert response.status_code == 200
    body = response.json()
    assert body["debt_to_gdp"]["value"] == 0
    assert body["debt_service_to_revenue"]["value"] == 0
    assert body["external_debt_share"] == 0


def test_dsa_age_boundary_and_copy_isolation():
    from services.imf_dsa import kenya_dsa_rating

    result = kenya_dsa_rating(today=date(2026, 9, 26))
    assert result["freshness"]["confirmation_age_days"] == 179
    assert result["freshness"]["status"] == "recent_confirmation"
    result["source"]["published"] = "bad"
    result["latest_confirmed"]["as_of"] = "bad"
    result = kenya_dsa_rating(today=date(2026, 9, 27))
    assert result["freshness"]["confirmation_age_days"] == 180
    assert result["freshness"]["status"] == "confirmation_aging"
    assert result["source"]["published"] == "2024-11-01"


def test_dsa_future_confirmation_is_not_recent():
    from services.imf_dsa import kenya_dsa_rating

    result = kenya_dsa_rating(today=date(2025, 1, 1))
    assert result["freshness"]["status"] == "unknown"
    assert result["freshness"]["confirmation_age_days"] is None


@pytest.mark.parametrize("value", [float("nan"), True, False])
def test_direct_call_rejects_bad_debt_values_before_json(
    db_session, seed_source_doc, value
):
    import main

    row = seed_timeline(db_session, seed_source_doc.id)
    # SQLite converts NaN to NULL and bool to int. Keep the hostile value in
    # the identity-mapped ORM row so this exercises the handler itself.
    row.gdp_ratio = value
    body = asyncio.run(main.get_debt_sustainability(db_session))
    assert body["debt_to_gdp"] is None, body["debt_to_gdp"]


@pytest.mark.parametrize("field,value", [
    ("debt_service_cost", float("nan")),
    ("debt_service_cost", True),
    ("debt_service_cost", False),
    ("total_revenue", True),
])
def test_direct_call_rejects_bad_fiscal_values_before_json(
    db_session, seed_source_doc, field, value
):
    import main

    row = seed_fiscal(db_session, seed_source_doc.id)
    setattr(row, field, value)
    body = asyncio.run(main.get_debt_sustainability(db_session))
    assert body["debt_service_to_revenue"] is None, body["debt_service_to_revenue"]


@pytest.mark.parametrize("field", ["gdp_ratio", "total_revenue", "debt_service_cost"])
def test_missing_numbers_stay_absent(client, db_session, seed_source_doc, field):
    if field == "gdp_ratio":
        seed_timeline(db_session, seed_source_doc.id, gdp_ratio=None)
        key = "debt_to_gdp"
    else:
        seed_fiscal(db_session, seed_source_doc.id, **{field: None})
        key = "debt_service_to_revenue"
    response = read_response(client)
    assert response.status_code == 200
    assert response.json()[key] is None
