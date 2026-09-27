"""Independent execution of cash-receipt source, period and numeric contracts."""
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from main import (
    _county_revenue_for_lines,
    county_financial_health,
    county_revenue_block,
)


STREAMS = {
    "Equitable Share": {"target": 10_000_000, "actual": 5_000_000},
    "Own Source Revenue": {"target": 2_000_000, "actual": 1_000_000},
    "Facility Improvement Financing": {"target": 400_000, "actual": 200_000},
    "Appropriations in Aid": {"target": 600_000, "actual": 300_000},
    "Total": {"target": 13_000_000, "actual": 6_500_000},
}


def _block(receipts, local=1_200_000, target=2_400_000):
    return county_revenue_block(
        receipts, local_revenue=local, own_source_target=target, fiscal_year="FY2025/26"
    )


def _line(stream, target, actual, **changes):
    values = dict(
        category="Revenue Receipts",
        subcategory=stream,
        allocated_amount=target,
        actual_spent=actual,
        currency="KES",
        period_id=1,
        entity_id=1,
        source_document_id=1,
        page_ref="p.42",
        period=SimpleNamespace(id=1, label="FY2025/26"),
        source_document=SimpleNamespace(id=1, url="https://cob.go.ke/report.pdf"),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _lines():
    return [_line(name, **amounts) for name, amounts in STREAMS.items()]


@pytest.mark.parametrize(
    "bad",
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
def test_bad_cash_actual_withholds_reconciliation(bad):
    rows = deepcopy(STREAMS)
    rows["Own Source Revenue"]["actual"] = bad
    result = _block(rows)
    assert result["total_revenue"] is None
    assert result["streams"] == []


@pytest.mark.parametrize(
    "bad", [None, True, float("nan"), float("inf"), -1, "broken", {}, []]
)
def test_bad_summary_measure_does_not_erase_valid_cash(bad):
    result = _block(STREAMS, local=bad, target=bad)
    assert result["total_revenue"] == 6_500_000
    assert result["local_revenue"] == 1_500_000
    assert result["summary_table_own_source_revenue"] is None
    assert result["summary_table_own_source_target"] is None


def test_reported_cash_zero_remains_zero():
    zero = {name: {"actual": 0, "target": 0} for name in STREAMS}
    result = _block(zero, local=0, target=0)
    assert (
        result["total_revenue"]
        == result["local_revenue"]
        == result["own_source_target"]
        == 0
    )
    assert result["total_revenue_absent_reason"] is None


def test_cash_target_ratio_includes_aia_on_both_sides():
    result = _county_revenue_for_lines(_lines())
    assert result["local_revenue"] == 1_500_000
    assert result["own_source_target"] == 3_000_000
    health = county_financial_health(
        total_allocated=10_000_000,
        total_spent=5_000_000,
        pending_bills=None,
        audit_status=None,
        own_source_actual=result["local_revenue"],
        own_source_target=result["own_source_target"],
    )
    own = next(c for c in health["components"] if c["name"] == "own_source_revenue")
    assert own["observed"] == 50


def test_missing_one_cash_target_withholds_only_target_not_actual_receipts():
    rows = deepcopy(STREAMS)
    rows["Appropriations in Aid"]["target"] = None
    result = _block(rows)
    assert result["total_revenue"] == 6_500_000
    assert result["local_revenue"] == 1_500_000
    assert result["own_source_target"] is None


@pytest.mark.parametrize(
    "change",
    [
        {
            "source_document_id": 2,
            "source_document": SimpleNamespace(id=2, url="https://cob.go.ke/other.pdf"),
        },
        {"period_id": 2, "period": SimpleNamespace(id=2, label="FY2024/25")},
        {"entity_id": 2},
        {"currency": "USD"},
    ],
)
def test_cash_streams_from_different_contexts_cannot_be_one_total(change):
    lines = _lines()
    for key, value in change.items():
        setattr(lines[0], key, value)
    result = _county_revenue_for_lines(lines)
    assert result["total_revenue"] is None, result


def test_duplicate_cash_streams_are_not_silently_last_row_wins():
    lines = [_line("Own Source Revenue", 9_000_000, 8_000_000), *_lines()]
    result = _county_revenue_for_lines(lines)
    assert result["total_revenue"] is None, result


def test_duplicate_summary_rows_are_not_silently_first_row_wins():
    summaries = [
        _line(None, 2_000_000, amount, category="Own Source Revenue")
        for amount in (1_000_000, 1_500_000)
    ]
    result = _county_revenue_for_lines(summaries)
    assert result["local_revenue"] is None, result


def test_summary_and_cash_comparison_cannot_mix_periods():
    summary = _line(
        None,
        12_000_000,
        10_000_000,
        category="Own Source Revenue",
        period_id=2,
        period=SimpleNamespace(id=2, label="FY2024/25"),
    )
    result = _county_revenue_for_lines([summary, *_lines()])
    assert result["total_revenue"] == 6_500_000
    assert result["fiscal_year"] == "FY2025/26"
    assert result["summary_table_own_source_revenue"] is None
    assert result["own_source_disagreement"] is None


@pytest.mark.parametrize("bad", [True, "broken", {}, []])
def test_invalid_summary_values_in_rows_do_not_crash_or_erase_cash(bad):
    summary = _line(None, 2_000_000, bad, category="Own Source Revenue")
    result = _county_revenue_for_lines([summary, *_lines()])
    assert result["total_revenue"] == 6_500_000
    assert result["summary_table_own_source_revenue"] is None


def test_bool_cash_amount_is_not_converted_to_one_before_validation():
    result = _county_revenue_for_lines(
        [
            _line("Own Source Revenue", 1, True),
            _line("Total", 1, 1),
        ]
    )
    assert result["total_revenue"] is None


def test_sum_of_finite_targets_cannot_publish_infinity():
    rows = deepcopy(STREAMS)
    for stream in (
        "Own Source Revenue",
        "Facility Improvement Financing",
        "Appropriations in Aid",
    ):
        rows[stream]["target"] = 1e308
    assert _block(rows)["own_source_target"] is None


def test_absent_receipts_keep_valid_summary_amount_and_basis():
    result = _block(None)
    assert result["local_revenue"] == 1_200_000
    assert result["own_source_target"] == 2_400_000
    assert result["local_revenue_basis"] == "summary_table_actual_realised"
    assert result["total_revenue"] is None


def test_mixed_source_receipts_are_withheld_on_public_county_route(
    client, db_session, seed_country, seed_source_doc
):
    from models import (
        BudgetLine,
        DocumentType,
        Entity,
        EntityType,
        FiscalPeriod,
        SourceDocument,
    )

    entity = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    period = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    other = SourceDocument(
        country_id=seed_country.id,
        publisher="Controller of Budget",
        title="Other edition",
        url="https://cob.go.ke/other.pdf",
        fetch_date=datetime(2026, 7, 1),
        doc_type=DocumentType.REPORT,
    )
    db_session.add_all([entity, period, other])
    db_session.flush()
    for name, values in STREAMS.items():
        db_session.add(
            BudgetLine(
                entity_id=entity.id,
                period_id=period.id,
                category="Revenue Receipts",
                subcategory=name,
                allocated_amount=values["target"],
                actual_spent=values["actual"],
                currency="KES",
                page_ref="p.42",
                source_document_id=other.id
                if name == "Equitable Share"
                else seed_source_doc.id,
            )
        )
    db_session.flush()
    response = client.get("/api/v1/counties/047")
    assert response.status_code == 200, response.text
    assert response.json()["revenue"]["total_revenue"] is None
