"""Historical budget figures obey the same accounting as the current summary."""

from datetime import datetime

import pytest

from models import BudgetLine, Entity, EntityType, FiscalPeriod


@pytest.fixture
def historical_county(db_session, seed_country, seed_source_doc):
    county = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    db_session.add(county)
    db_session.flush()
    # Every period includes components restating its total. Deliberately give
    # the components different spending so summing all rows alters execution.
    for year, allocated, spent in [
        (2020, 100, 70),
        (2021, 100, 0),
        (2022, 100, None),
        (2023, 0, 0),
        (2100, 100, 50),  # Open/future periods cannot enter completed history.
    ]:
        period = FiscalPeriod(
            country_id=seed_country.id,
            label=f"FY{year}/{str(year + 1)[2:]}",
            start_date=datetime(year, 7, 1),
            end_date=datetime(year + 1, 6, 30),
        )
        db_session.add(period)
        db_session.flush()
        for category, allocation, spending in [
            ("Total", allocated, spent),
            ("Recurrent", 60, 30),
            ("Development", 40, 20),
        ]:
            db_session.add(
                BudgetLine(
                    entity_id=county.id,
                    period_id=period.id,
                    category=category,
                    allocated_amount=allocation,
                    actual_spent=spending,
                    currency="KES",
                    page_ref="p.42",
                    source_document_id=seed_source_doc.id,
                )
            )
    db_session.flush()
    return county


def _response(client, county):
    response = client.get("/api/v1/counties/047/comprehensive")
    assert response.status_code == 200, response.text
    entity = client.get(f"/api/v1/entities/{county.id}")
    assert entity.status_code == 200, entity.text
    return response.json(), entity.json()


def test_budget_only_history_cannot_invent_historical_health_grades(
    client, historical_county
):
    payload, _ = _response(client, historical_county)
    assert payload["health_history"] == []


def test_completed_budget_history_matches_published_summary_without_double_counting(
    client, historical_county
):
    payload, entity = _response(client, historical_county)
    series = {
        row["fiscal_period"]["label"]: row
        for row in entity["financial_time_series"]
    }
    history = payload["budget_execution_history"]
    assert [row["fiscal_period"]["label"] for row in history] == [
        "FY2020/21", "FY2021/22", "FY2022/23", "FY2023/24"
    ]
    for row in history:
        expected = series[row["fiscal_period"]["label"]]
        for key in (
            "total_allocation", "total_spent", "execution_rate",
            "accounting_basis", "currency", "sources", "absent_reasons",
        ):
            assert row[key] == expected[key], (key, row, expected)
        assert row["sources"][0]["page_refs"] == ["p.42"]
    assert history[0]["total_allocation"] == 100
    assert history[0]["total_spent"] == 70
    assert history[0]["execution_rate"] == 70


def test_completed_budget_history_preserves_zero_and_absence(
    client, historical_county
):
    payload, _ = _response(client, historical_county)
    history = {
        row["fiscal_period"]["label"]: row
        for row in payload["budget_execution_history"]
    }
    assert history["FY2021/22"]["total_spent"] == 0
    assert history["FY2021/22"]["execution_rate"] == 0
    assert history["FY2022/23"]["total_spent"] is None
    assert history["FY2022/23"]["execution_rate"] is None
    assert history["FY2023/24"]["total_allocation"] == 0
    assert history["FY2023/24"]["execution_rate"] is None
