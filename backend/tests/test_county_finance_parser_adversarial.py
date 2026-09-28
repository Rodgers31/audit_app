"""Independent hostile-input execution of the county publication parser."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from seeding import pdf_parsers
from seeding.pdf_parsers import CoBQuarterlyReportParser, ExtractedTable, county_revenue_receipts


def _table(rows, headers=None):
    return ExtractedTable(
        1, 0,
        headers or ["No", "Revenue Stream", "Annual Target", "Actual Receipts"],
        rows, (0, 0, 0, 0),
    )


def test_explicit_zero_is_a_valid_observed_total():
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "0", "0"],
        ["", "Grand Total", "0", "0"],
    ])])
    assert why == ""
    assert result == {"Equitable Share": (Decimal(0), Decimal(0)),
                      "Total": (Decimal(0), Decimal(0))}


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "sNaN", "n/a"])
def test_unreadable_aggregate_receipts_cannot_certify_zero(bad):
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "0", bad],
        ["", "Grand Total", "0", "0"],
    ])])
    assert result is None, (result, why)


@pytest.mark.parametrize("missing", ["", None])
def test_heading_without_observed_receipts_cannot_certify_zero(missing):
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "", missing],
        ["", "Grand Total", "0", "0"],
    ])])
    assert result is None, (result, why)


def test_amount_bearing_aggregate_grants_do_not_become_equitable_share():
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "10000", "10000"],
        ["B", "Additional Allocations", "5000", "5000"],
        ["", "Grand Total", "15000", "15000"],
    ])])
    assert result is None or (
        result["Equitable Share"][1] == Decimal(10000)
        and result.get("Additional Allocations", (None, None))[1] == Decimal(5000)
    ), (result, why)


@pytest.mark.parametrize("actual", ["-1", "(1)", "NaN", "Infinity", "True"])
def test_hostile_grand_total_is_withheld(actual):
    result, _ = county_revenue_receipts([_table([
        ["A", "Equitable Share", "0", "0"],
        ["", "Grand Total", "0", actual],
    ])])
    assert result is None


def test_duplicate_grand_totals_are_withheld():
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "10000", "10000"],
        ["", "Grand Total", "10000", "10000"],
        ["", "Grand Total", "10000", "10000"],
    ])])
    assert (result, why) == (None, "more_than_one_grand_total")


def test_two_actual_columns_are_withheld():
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "10000", "10000", "0"],
        ["", "Grand Total", "10000", "10000", "0"],
    ], ["No", "Revenue Stream", "Annual Target", "Actual Receipts", "Actual Receipts YTD"])])
    assert result is None


def test_no_tables_accounts_for_all_counties_without_publication():
    parser = CoBQuarterlyReportParser(Path("absent.pdf"))
    assert parser._extract_county_revenue_receipts() == []
    assert len(parser.revenue_coverage) == 47
    assert {v["status"] for v in parser.revenue_coverage.values()} == {"withheld"}


def test_unreadable_pdf_never_marks_coverage_reconciled(monkeypatch):
    parser = CoBQuarterlyReportParser(Path("absent.pdf"))
    parser.tables = [_table([
        ["A", "Equitable Share", "10000", "10000"],
        ["", "Grand Total", "10000", "10000"],
    ])]
    monkeypatch.setattr(pdf_parsers.pdfplumber, "open", MagicMock(side_effect=FileNotFoundError))
    assert parser._extract_county_revenue_receipts() == []
    assert len(parser.revenue_coverage) == 47
    assert {v["reason"] for v in parser.revenue_coverage.values()} == {"revenue_captions_unreadable"}


def test_valid_caption_and_table_are_positive_coverage_control(monkeypatch):
    parser = CoBQuarterlyReportParser(Path("report.pdf"))
    parser._period = ("2025/26", None)
    parser.tables = [_table([
        ["A", "Equitable Share", "10000", "10000"],
        ["", "Grand Total", "10000", "10000"],
    ])]
    page = SimpleNamespace(extract_text=lambda: "Table 3.1: Nairobi County, Revenue Performance")
    pdf = MagicMock()
    pdf.__enter__.return_value = SimpleNamespace(pages=[page])
    monkeypatch.setattr(pdf_parsers.pdfplumber, "open", lambda _: pdf)
    records = parser._extract_county_revenue_receipts()
    assert len(records) == 2
    assert parser.revenue_coverage["Nairobi"]["status"] == "reconciled"
    assert sum(v["status"] == "withheld" for v in parser.revenue_coverage.values()) == 46


@pytest.mark.parametrize("missing", ["", None])
@pytest.mark.parametrize("label", ["Equitable Share", "Sub-total"])
def test_blank_receipts_cells_are_not_observed_zero(label, missing):
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "", ""],
        ["1", label, "10000", missing],
        ["", "Grand Total", "10000", "0"],
    ])])
    assert result is None, (result, why)


@pytest.mark.parametrize("label", ["Equitable Share", "Sub-total"])
def test_explicit_zero_item_or_subtotal_is_a_positive_control(label):
    result, why = county_revenue_receipts([_table([
        ["A", "Equitable Share", "", ""],
        ["1", label, "10000", "0"],
        ["", "Grand Total", "10000", "0"],
    ])])
    assert why == ""
    assert result["Equitable Share"][1] == Decimal(0)
    assert result["Total"][1] == Decimal(0)
