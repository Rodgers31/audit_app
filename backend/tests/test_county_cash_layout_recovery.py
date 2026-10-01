"""Source-shaped cash layout recoveries from the checksum-pinned CoB annual PDF."""
import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from seeding.pdf_parsers import ExtractedTable, county_revenue_receipts

FIXTURE = Path(__file__).parent / "fixtures/cbirr_annual_cash_layouts.json"


def tables(county):
    raw = json.loads(FIXTURE.read_text())
    assert (
        raw["source_sha256"]
        == "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3"
    )
    return [ExtractedTable(**t) for t in raw["tables"][county]]


@pytest.mark.parametrize(
    "county,total,stream,actual",
    [
        ("Kisii", "16499037626", "Additional Allocations", "855582918"),
        ("Kisumu", "13360566017.46", "Appropriations in Aid", "124070871"),
        ("Kitui", "13809805963", "Additional Allocations", "1286750893.25"),
    ],
)
def test_source_cash_layout_reconciles(county, total, stream, actual):
    receipts, reason = county_revenue_receipts(tables(county))
    assert reason == "", reason
    assert receipts["Total"][1] == Decimal(total)
    assert receipts[stream][1] == Decimal(actual)
    if county == "Kisumu":
        assert receipts["Total"][0] == Decimal("16973318712")
        assert receipts["Facility Improvement Financing"][1] == Decimal("693554054")


@pytest.mark.parametrize(
    "county,reason",
    [
        ("Kwale", "streams_do_not_sum_to_grand_total (out by 59,814,318.00)"),
        ("Migori", "a_section_has_two_subtotals"),
        ("Nyeri", "unobserved_receipts_cell"),
        ("Samburu", "streams_do_not_sum_to_grand_total (out by 24,413)"),
    ],
)
def test_source_conflicts_remain_withheld(county, reason):
    assert county_revenue_receipts(tables(county)) == (None, reason)


def _kitui_subtotal(ts):
    return next(row for table in ts for row in table.rows if row[1] == "-")


@pytest.mark.parametrize(
    "mutation",
    ["cash", "accrual", "arrears", "target", "missing_cash", "unknown_next_stream"],
)
def test_unlabelled_subtotal_needs_local_evidence_not_a_matching_grand_total(mutation):
    ts = copy.deepcopy(tables("Kitui"))
    row = _kitui_subtotal(ts)
    if mutation == "cash":
        # Within the old KES 1,000 tolerance, outside printed precision.
        row[3] = row[5] = "1,286,750,993.25"
    elif mutation == "accrual":
        row[5] = "1,286,750,993.25"
    elif mutation == "arrears":
        row[4] = "100"
    elif mutation == "target":
        row[2] = "1,000"
    elif mutation == "missing_cash":
        row[3] = ""
    else:
        heading = next(row for table in ts for row in table.rows if row[0] == "E")
        heading[1] = "Unknown stream"
    assert county_revenue_receipts(ts) == (None, "unlabelled_subtotal_not_corroborated")


def test_incomplete_item_targets_do_not_replace_the_printed_aggregate_target():
    streams, why = county_revenue_receipts(tables("Kitui"))
    assert why == ""
    assert streams["Additional Allocations"][0] == Decimal("2071208708.42")


def _small_table(rows):
    return ExtractedTable(
        1,
        0,
        ["No", "Revenue Stream", "Annual Target", "Actual Receipts"],
        rows,
        (0, 0, 0, 0),
    )


def test_numbered_equitable_subtotal_requires_an_identical_closing_pair():
    rows = [
        ["B", "Equitable Share", "", ""],
        ["1", "Sub-Total", "50", "50"],
        ["", "Sub-Total", "50", "50"],
        ["", "Grand Total", "50", "50"],
    ]
    receipts, why = county_revenue_receipts([_small_table(rows)])
    assert why == ""
    assert receipts["Equitable Share"] == (Decimal(50), Decimal(50))
    rows[2][2] = "60"
    assert county_revenue_receipts([_small_table(rows)])[0] is None
    rows[2][2] = "50"
    rows[1][0] = ""
    assert county_revenue_receipts([_small_table(rows)])[0] is None


@pytest.mark.parametrize("nil", ["_", "-", "–"])
def test_printed_nil_item_is_distinct_from_an_observed_zero_total(nil):
    rows = [
        ["B", "Equitable Share", "", ""],
        ["1", "Equitable Share", "0", nil],
        ["", "Grand Total", "0", "0"],
    ]
    assert county_revenue_receipts([_small_table(rows)])[0] is None
    rows[1][3] = "0"
    assert county_revenue_receipts([_small_table(rows)])[0]["Total"][1] == 0
    rows[3 - 1][3] = nil
    assert county_revenue_receipts([_small_table(rows)])[0] is None


@pytest.mark.parametrize(
    "cell", ["6,973,318,712", "69,973,318,712", ",973,318,712", "NaN", ""]
)
def test_total_label_digit_does_not_publish_a_truncated_or_unreadable_target(cell):
    ts = copy.deepcopy(tables("Kisumu"))
    total = next(row for table in ts for row in table.rows if row[0] == "Total 1")
    total[2] = cell
    streams, why = county_revenue_receipts(ts)
    assert why == ""
    expected = {
        "6,973,318,712": Decimal("16973318712"),
        "69,973,318,712": Decimal("169973318712"),
    }.get(cell)
    assert streams["Total"][0] == expected


def test_erased_numbered_grant_cannot_disappear_from_subtotal_evidence():
    ts = copy.deepcopy(tables("Kitui"))
    row = next(
        row for table in ts for row in table.rows if row[0] == "3" and "KDSP" in row[1]
    )
    row[2:] = [""] * (len(row) - 2)
    assert county_revenue_receipts(ts) == (None, "unlabelled_subtotal_not_corroborated")
