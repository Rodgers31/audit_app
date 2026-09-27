"""Independent hostile-input checks for entity financial publication."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from models import BudgetLine
from services.entity_financials import financial_summary


def _period(**changes):
    values = dict(
        id=1,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _line(**changes):
    values = dict(
        category="Total",
        subcategory=None,
        allocated_amount=100,
        actual_spent=60,
        currency="KES",
        page_ref="p.42",
        source_document_id=1,
        source_document=SimpleNamespace(
            title="Budget report",
            publisher="Controller of Budget",
            url="https://cob.go.ke/report.pdf",
            meta={},
        ),
        basis=None,
        quarantine_reason=None,
        provenance=[],
        period_id=1,
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "amount",
    [
        None,
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        -1,
        "broken",
        {},
        [],
    ],
)
def test_hostile_amounts_do_not_publish(amount):
    summary = financial_summary([_line(allocated_amount=amount)], _period())
    assert summary["total_allocation"] is None
    assert summary["execution_rate"] is None


@pytest.mark.parametrize("amount", [0, 100, Decimal("0"), Decimal("100.25")])
def test_valid_amount_positive_control(amount):
    summary = financial_summary([_line(allocated_amount=amount)], _period())
    assert summary["total_allocation"] == float(amount)


@pytest.mark.parametrize("basis", ["modelled", "projected"])
def test_explicit_nonactual_basis_is_withheld(basis):
    assert (
        financial_summary([_line(basis=basis)], _period())["total_allocation"] is None
    )


@pytest.mark.parametrize(
    "provenance",
    [
        [{"data_quality": "modelled"}],
        {"data_quality": "modelled"},
        [{"data_quality": "estimated"}],
        [{"data_quality": "projected"}],
    ],
)
def test_legacy_provenance_without_basis_is_not_reported_actual(provenance):
    summary = financial_summary([_line(provenance=provenance)], _period())
    assert summary["total_allocation"] is None, summary


def test_source_modelled_metadata_without_basis_is_not_reported_actual():
    line = _line()
    line.source_document.meta = {"data_quality": "modelled"}
    summary = financial_summary([line], _period())
    assert summary["total_allocation"] is None, summary


@pytest.mark.parametrize("location", ["source", "row"])
@pytest.mark.parametrize(
    "dataset", ["enhanced_county_data", "enhanced_county_data.json", "bootstrap_county_model"]
)
def test_modelled_dataset_stamp_cannot_publish_through_financial_gate(location, dataset):
    line = _line()
    stamp = {"dataset_id": dataset}
    if location == "source":
        line.source_document.meta = stamp
    else:
        line.provenance = stamp
    summary = financial_summary([line], _period())
    assert summary["total_allocation"] is None, summary
    assert summary["total_spent"] is None, summary


@pytest.mark.parametrize("page_ref", ["0", "-1"])
def test_impossible_or_blank_locator_does_not_publish(page_ref):
    summary = financial_summary([_line(page_ref=page_ref)], _period())
    assert summary["total_allocation"] is None, summary


@pytest.mark.parametrize(
    "period", [None, _period(start_date=None), _period(end_date=None)]
)
def test_summary_requires_dated_period(period):
    summary = financial_summary([_line()], period)
    assert summary["total_allocation"] is None, summary


def test_float_overflow_is_not_a_publishable_amount():
    summary = financial_summary([_line(allocated_amount=Decimal("1e309"))], _period())
    assert summary["total_allocation"] is None, summary


def test_mixed_documents_do_not_complete_each_other():
    lines = [
        _line(category="Recurrent", allocated_amount=60),
        _line(category="Development", allocated_amount=40, source_document_id=2),
    ]
    summary = financial_summary(lines, _period())
    assert summary["total_allocation"] is None
    assert summary["absent_reasons"]["total_allocation"] == "multiple_sources"


def test_partial_classification_never_becomes_whole_budget():
    summary = financial_summary([_line(category="Recurrent")], _period())
    assert summary["total_allocation"] is None
    assert summary["absent_reasons"]["total_allocation"] == "incomplete_classification"


def test_modelled_legacy_row_is_withheld_through_both_routes(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc
):
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            actual_spent=60,
            currency="KES",
            page_ref="p.42",
            basis=None,
            source_document_id=seed_source_doc.id,
            provenance=[{"data_quality": "modelled"}],
        )
    )
    db_session.flush()
    listing = client.get("/api/v1/entities?entity_type=county")
    detail = client.get(f"/api/v1/entities/{seed_entity.id}")
    assert listing.status_code == detail.status_code == 200
    results = [
        listing.json()[0]["financial_summary"],
        detail.json()["financial_time_series"][0],
    ]
    assert all(row["total_allocation"] is None for row in results), results


def test_nonfinite_recent_amount_does_not_break_detail_serialization(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc
):
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            actual_spent=Decimal("Infinity"),
            currency="KES",
            page_ref="p.42",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.flush()
    response = client.get(f"/api/v1/entities/{seed_entity.id}")
    assert response.status_code == 200, response.text
    assert response.json()["recent_budget_lines"][0]["actual_spent"] is None


@pytest.mark.parametrize("total,spent", [(0, 0), (100, None)])
def test_map_and_entity_routes_agree_on_zero_and_absence(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc, total, spent
):
    for category, amount in [("Total", total), ("Recurrent", 60), ("Development", 40)]:
        db_session.add(
            BudgetLine(
                entity_id=seed_entity.id,
                period_id=seed_fiscal_period.id,
                category=category,
                allocated_amount=amount,
                actual_spent=spent,
                currency="KES",
                page_ref="p.42",
                source_document_id=seed_source_doc.id,
            )
        )
    db_session.flush()
    map_response = client.get("/api/v1/counties")
    entity_response = client.get("/api/v1/entities?entity_type=county")
    assert map_response.status_code == entity_response.status_code == 200
    map_row = map_response.json()[0]
    summary = entity_response.json()[0]["financial_summary"]
    assert (map_row["total_budget"], map_row["total_spent"]) == (
        summary["total_allocation"],
        summary["total_spent"],
    )


@pytest.mark.parametrize("page_ref", [None, "", "   ", "\t\n"])
def test_missing_locator_is_disclosed_without_inventing_a_page(page_ref):
    summary = financial_summary([_line(page_ref=page_ref)], _period())
    assert summary["total_allocation"] == 100
    assert summary["sources"][0]["page_refs"] == []
