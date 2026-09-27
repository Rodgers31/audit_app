"""Regressions for #289/#320: a nominal ratio is not a DSA verdict."""
from datetime import date

import pytest
from models import DebtTimeline, FiscalSummary


@pytest.mark.parametrize("ratio", [0, 40, 55, 70])
def test_sustainability_ratios_do_not_invent_thresholds(client, db_session, seed_source_doc, monkeypatch, ratio):
    import main
    monkeypatch.setattr(main, "_get_regional_peers", lambda **kwargs: [])
    db_session.add(DebtTimeline(year=2025, total=100, external=0, domestic=100,
                                gdp_ratio=ratio, unit="KES", source_document_id=seed_source_doc.id))
    db_session.add(FiscalSummary(fiscal_year="FY 2025/26", total_revenue=100,
                                debt_service_cost=0, page_ref="p.1", unit="KES",
                                source_document_id=seed_source_doc.id,
                                meta={
                                    "debt_service_source": {"url": "https://treasury.go.ke/debt.pdf", "page": "p.1"},
                                    "revenue_source": {"url": "https://treasury.go.ke/revenue.pdf", "page": "p.2"},
                                }))
    db_session.commit()
    main.clear_all_caches()
    body = client.get("/api/v1/debt/sustainability").json()
    assert body["debt_to_gdp"]["value"] == ratio
    assert not {"threshold_imf", "threshold_eac", "status"} & body["debt_to_gdp"].keys()
    assert body["debt_service_to_revenue"]["value"] == 0
    assert not {"threshold", "status"} & body["debt_service_to_revenue"].keys()
    assert body["external_debt_share"] == 0
    assert body["imf_dsa"]["source"]["published"] == "2024-11-01"


def test_dsa_available_without_fiscal_or_debt_rows(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "_get_regional_peers", lambda **kwargs: [])
    main.clear_all_caches()
    assert client.get("/api/v1/debt/sustainability").json()["imf_dsa"]["source"]["page"] == 132


@pytest.mark.parametrize("today,expected", [(date(2026, 4, 1), "recent_confirmation"),
                                           (date(2026, 9, 27), "confirmation_aging"),
                                           (date(2026, 3, 1), "unknown")])
def test_dsa_confirmation_age_is_explicit(today, expected):
    from services.imf_dsa import kenya_dsa_rating
    result = kenya_dsa_rating(today=today)
    assert result["freshness"]["status"] == expected
    assert result["freshness"]["evaluated_on"] == today.isoformat()
    assert result["source"]["dsa_date"] == "2024-10-18"
    assert result["latest_confirmed"]["as_of"] == "2026-03-31"
