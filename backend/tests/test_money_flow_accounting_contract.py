"""Money-flow stages must preserve the county's published accounting contract.

All calls use the SQLite-backed TestClient fixture. Extra rows deliberately
look numeric and plausible; only a report's Total or complete economic
classification can establish a county budget or spending total.
"""
from __future__ import annotations

import pytest
from models import BudgetLine, Entity, EntityType


CASES = [
    pytest.param(
        [("Total", 100, None), ("Own Source Revenue", 10, 9), ("Health", 20, 15)],
        100,
        None,
        id="missing-total-spend-with-unrelated-numbers",
    ),
    pytest.param(
        [("Total", 0, 0), ("Recurrent", 60, 45), ("Development", 40, 25)],
        0,
        0,
        id="reported-zero-total-overrides-components",
    ),
    pytest.param([("Total", 0, 0)], 0, 0, id="reported-zero-only"),
    pytest.param([("Total", 100, 0)], 100, 0, id="reported-zero-spending"),
    pytest.param(
        [("Health", 900, 800), ("Education", 100, 50)],
        None,
        None,
        id="sector-only-projection-is-not-reported-total",
    ),
    pytest.param(
        [("Recurrent", 60, None), ("Development", 40, 20)],
        100,
        None,
        id="one-classification-spending-component-absent",
    ),
    pytest.param(
        [
            ("Total", 100, 50),
            ("Recurrent", 60, 30),
            ("Development", 40, 20),
            ("Own Source Revenue", 10, 9),
        ],
        100,
        50,
        id="supported-positive-total-is-not-double-counted",
    ),
]


@pytest.fixture()
def county_accounting(db_session, seed_country, seed_fiscal_period, seed_source_doc):
    entity = Entity(
        id=501,
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        type=EntityType.COUNTY,
        slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    def populate(rows):
        for category, allocation, spending in rows:
            db_session.add(
                BudgetLine(
                    entity_id=501,
                    period_id=seed_fiscal_period.id,
                    category=category,
                    allocated_amount=allocation,
                    actual_spent=spending,
                    currency="KES",
                    source_document_id=seed_source_doc.id,
                    page_ref="p.42",
                )
            )
        db_session.commit()

    return populate


def _response(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("rows,allocation,spending", CASES)
@pytest.mark.parametrize("surface", ["county", "batch", "national"])
def test_money_flow_matches_entity_and_county_headlines(
    client, county_accounting, rows, allocation, spending, surface
):
    county_accounting(rows)
    # Positive and absent expectations are explicit, not derived from the
    # implementation under test. This also pins the fiscal period.
    entity = _response(client, "/api/v1/entities/501")
    summary = entity["financial_time_series"][0]
    assert summary["fiscal_period"]["label"] == "FY2024/25"
    assert summary["total_allocation"] == allocation
    assert summary["total_spent"] == spending
    detail = _response(
        client, "/api/v1/counties/code:001/comprehensive?fiscal_year=2024%2F25"
    )
    assert detail["budget"]["total_allocated"] == allocation
    assert detail["budget"]["total_spent"] == spending

    path = {
        "county": "/api/v1/counties/501/money-flow?year=2024%2F25",
        "batch": "/api/v1/money-flow/all-counties?year=2024%2F25",
        "national": "/api/v1/audit/money-flow/national?year=2024%2F25",
    }[surface]
    body = _response(client, path)
    if surface == "batch":
        assert len(body) == 1
        body = body[0]
    assert body["fiscal_year"] == "2024/25"
    stages = {stage["stage"]: stage for stage in body["stages"]}
    assert stages["Allocated"]["amount"] == allocation
    assert stages["Spent"]["amount"] == spending
    assert stages["Allocated"].get("data_unavailable", False) is (allocation is None)
    assert stages["Spent"].get("data_unavailable", False) is (spending is None)
    expected_efficiency = (
        spending / allocation * 100 if allocation and spending is not None else None
    )
    assert body["efficiency_score"] == expected_efficiency
    if allocation is None:
        assert body["budget_source"] is None
        assert stages["Allocated"].get("source") is None
    if spending is None or allocation is None:
        assert stages["Spent"].get("gap_from_prev") is None
