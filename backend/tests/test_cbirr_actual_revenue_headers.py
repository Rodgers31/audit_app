"""Cash columns in CoB FY2025/26 Tables 3.34 and 3.50 (PDF SHA below).

The eighteen page fixtures are pdfplumber's extracted rows from the exact CoB
annual PDF SHA-256 5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3.
The publisher calls the cash column ``Actual Revenues``/``Actual Revenue``;
the adjacent ``Total Revenues`` column is on an accrual basis.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from seeding.pdf_parsers import (
    ExtractedTable, _corroborated_misgrouped_cash, _is_revenue_table, _kes_cell,
    county_revenue_receipts,
)


FIXTURE = Path(__file__).parent / "fixtures" / "cbirr_fy2025_26_revenue_recovery.json"


def _tables(county):
    raw = json.loads(FIXTURE.read_text())
    assert raw["source_sha256"] == "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3"
    return [
        ExtractedTable(t["page_number"], 0, t["headers"], t["rows"], (0, 0, 0, 0))
        for t in raw["tables"][county]
    ]


@pytest.mark.parametrize(
    "county,total,equitable",
    [
        ("Bungoma", "16154951221", "11838054667"),
        ("Busia", "9897383793", "7956564058"),
    ],
)
def test_actual_revenue_cash_column_reconciles_to_printed_grand_total(
    county, total, equitable,
):
    tables = _tables(county)
    assert all(_is_revenue_table(table) for table in tables)
    streams, reason = county_revenue_receipts(tables)
    assert reason == ""
    assert streams["Total"][1] == Decimal(total)
    assert streams["Equitable Share"][1] == Decimal(equitable)
    parts = sum(value[1] for key, value in streams.items() if key != "Total")
    # Busia's printed streams are KES 2 below its printed Grand Total; the
    # existing KES 1,000 source-table tolerance covers this disclosed drift.
    assert Decimal(total) - parts == (Decimal(2) if county == "Busia" else Decimal(0))
    if county == "Busia":
        # Its two grant target subtotals are additive, while the second
        # actual subtotal already includes the first. Both are source facts.
        assert streams["Additional Allocations"] == (
            Decimal("1101725837"), Decimal("728472124")
        )


def test_cash_column_cannot_be_confused_with_adjacent_accrual_column():
    table = _tables("Busia")[0]
    assert "actual" in table.headers[3].lower()
    assert "accrual" in table.headers[5].lower()
    # Busia's opening-balance subtotal is KES 509,371,640 cash; its
    # accrual figure is KES 1,120,364,257. The extracted result must keep
    # the former even when the latter also contains a numeric amount.
    streams, reason = county_revenue_receipts(_tables("Busia"))
    assert reason == ""
    assert streams["Balance Brought Forward"][1] == Decimal("509371640")


def test_migori_three_grant_subtotals_still_require_separate_reconciliation():
    # Migori Table 3.412 has three nested grant subtotals. Its adjacent
    # composition chart on PDF 549 also names a different grants amount;
    # the two-subtotal support proven by Busia cannot certify this chapter.
    streams, reason = county_revenue_receipts(_tables("Migori"))
    assert streams is None
    assert reason == "a_section_has_two_subtotals"


def test_kilifi_split_target_header_still_reads_cash_grand_total():
    # PDF 314 splits "Targeted" across the preceding Revenue Stream header
    # and the target cell. It must not drop its closing Grand Total.
    streams, reason = county_revenue_receipts(_tables("Kilifi"))
    assert reason == ""
    assert streams["Total"][1] == Decimal("17118563037")
    assert streams["Other Revenue"] == (None, Decimal("950062290"))


def test_a_clipped_leading_digit_cannot_become_a_smaller_target():
    # Kilifi's printed 1,150,000,000 is extracted as ",150,000,000.00".
    assert _kes_cell(",150,000,000.00") is None


@pytest.mark.parametrize("cell", ["1,500,", "1,50,0"])
def test_malformed_grouping_cannot_become_a_plausible_amount(cell):
    assert _kes_cell(cell) is None


def test_explicit_accrual_actual_revenue_header_is_not_cash():
    table = ExtractedTable(
        1, 0,
        ["Revenue Stream", "Annual Target", "Actual Revenues (on an accrual basis)"],
        [["Equitable Share", "1000", "1500"], ["Grand Total", "1000", "1500"]],
        (0, 0, 0, 0),
    )
    assert not _is_revenue_table(table)
    streams, reason = county_revenue_receipts([table])
    assert streams is None


def test_machakos_misgrouped_cash_item_requires_row_evidence():
    # PDF 440 prints FIF cash as "16,04,988,360". The adjacent C cell is
    # nil and D prints 1,604,988,360; the FIF subtotal prints that amount too.
    # The loose number remains invalid outside this corroborated table row.
    assert _kes_cell("16,04,988,360") is None
    streams, reason = county_revenue_receipts(_tables("Machakos"))
    assert reason == ""
    assert streams["Facility Improvement Financing"][1] == Decimal("1604988360")
    assert streams["Total"][1] == Decimal("14230737987")


@pytest.mark.parametrize("receivable,accrual", [("1", "1501"), ("-", "9999")])
def test_misgrouped_cash_without_zero_receivable_and_matching_accrual_is_refused(
    receivable, accrual,
):
    headers = ["revenue stream", "actual receipts", "receivables", "total accrual"]
    row = ["item", "1,50,0", receivable, accrual]
    assert _corroborated_misgrouped_cash(row, headers, 1) is None


def test_kisumu_clipped_target_digit_stays_with_its_total():
    streams, reason = county_revenue_receipts(_tables("Kisumu"))
    assert reason == ""
    assert streams["Total"] == (
        Decimal("16973318712"), Decimal("13360566017.46")
    )
