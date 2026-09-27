"""Independent hostile-input tests of fiscal-outturn publication."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from seeding.domains.fiscal_summary import fiscal_framework as ff
from services.fiscal_outturns import fiscal_outturn


def edition():
    data = json.loads((Path(__file__).parent / "fixtures/budget_summary/fy2026_27.json").read_text())
    pages = [data["pages"].get(str(i), "") for i in range(1, data["_source"]["page_count"] + 1)]
    return ff.read_edition(pages, fiscal_year="FY 2026/27")


def framework():
    split = ff.split_for_fiscal_year(edition(), "FY 2023/24", known_ordinary_revenue=2288.9)
    return ff.framework_payload(split, source_url="https://treasury.go.ke/book.pdf", page=63)


def outturn(meta):
    return fiscal_outturn(SimpleNamespace(meta=meta, fiscal_year="FY 2023/24"))


@pytest.mark.parametrize("meta", [None, {}, [], "bad", False,
                                      {"fiscal_framework": None},
                                      {"fiscal_framework": []},
                                      {"fiscal_framework": "bad"}])
def test_missing_or_malformed_metadata_withholds(meta):
    row = outturn(meta)
    assert row["expenditure"] is None
    assert row["balance"] is None
    assert row["absent_reason"]


@pytest.mark.parametrize("source", [None, {}, [], "bad", False])
def test_missing_or_malformed_source_withholds(source):
    data = framework()
    data["source"] = source
    row = outturn({"fiscal_framework": data})
    assert row["expenditure"] is None
    assert row["absent_reason"]


@pytest.mark.parametrize("field", [
    "total_revenue_incl_aia_billion", "total_expenditure_billion",
    "fiscal_deficit_incl_grants_billion", "total_financing_billion",
    "grants_billion", "adjustment_to_cash_basis_billion",
    "statistical_discrepancy_billion",
])
@pytest.mark.parametrize("value", [None, True, False, float("nan"), float("inf"), float("-inf"), "0", [], {}])
def test_hostile_amounts_do_not_publish(field, value):
    data = framework()
    data[field] = value
    row = outturn({"fiscal_framework": data})
    assert row["expenditure"] is None
    assert row["balance"] is None
    assert row["absent_reason"]


@pytest.mark.parametrize("field", [
    "total_revenue_incl_aia_billion", "total_expenditure_billion",
    "fiscal_deficit_incl_grants_billion", "total_financing_billion",
    "grants_billion", "adjustment_to_cash_basis_billion",
    "statistical_discrepancy_billion",
])
@pytest.mark.parametrize("delta", [1, 0.4])
def test_mismatched_totals_withhold(field, delta):
    data = framework()
    data[field] += delta
    row = outturn({"fiscal_framework": data})
    assert row["balance"] is None
    assert row["absent_reason"]


@pytest.mark.parametrize("field,value", [
    ("url", True), ("url", ["https://treasury.go.ke/book.pdf"]),
    ("url", "   "), ("page", True), ("page", -1),
    ("page", "0"), ("page", "-1"), ("page", "0.0"), ("page", "NaN"), ("page", "Infinity"),
    ("page", "   "), ("page", ["p.63"]),
])
def test_malformed_source_locator_does_not_publish(field, value):
    data = framework()
    data["source"][field] = value
    row = outturn({"fiscal_framework": data})
    assert row["balance"] is None, row
    assert row["absent_reason"]


def test_printed_balance_and_financing_remain_distinct():
    row = outturn({"fiscal_framework": framework()})
    assert row["expenditure"] == 3605.2
    assert row["balance"] == -880.5
    assert row["financing"] == 818.3
    assert row["cash_adjustment"] == 45.4
    assert row["statistical_discrepancy"] == -16.8
    assert row["column"] == "Actual"
    assert row["absent_reason"] is None


def test_printed_zero_is_preserved():
    data = framework()
    for key in list(data):
        if key.endswith("_billion"):
            data[key] = 0
    row = outturn({"fiscal_framework": data})
    assert row["expenditure"] == 0
    assert row["balance"] == 0
    assert row["financing"] == 0
    assert row["absent_reason"] is None


def test_unknown_header_is_not_inferred_from_old_fiscal_year():
    data = json.loads((Path(__file__).parent / "fixtures/budget_summary/fy2026_27.json").read_text())
    lines = data["pages"]["63"].splitlines()
    lines = ["Unsupported header shape" if line.strip().startswith("Act.") else line for line in lines]
    table = ff.parse_annex_lines(lines, page=63)
    split = ff.gate_column(table, 0, fiscal_year="FY 2023/24", identified_by="revenue_column")
    assert split.column_label is None
    payload = ff.framework_payload(split, source_url="https://treasury.go.ke/book.pdf", page=63)
    row = outturn({"fiscal_framework": payload})
    assert row["column"] == "Vintage unconfirmed"
    assert row["balance"] == -880.5


@pytest.mark.parametrize("column", [
    None, "", "   ", "Vintage unconfirmed", True, 1, ["Actual"],
    {"label": "Actual"}, "revenue_column", "actual",
    "The column printing this row's ordinary revenue", "Supplementary",
])
def test_stored_unknown_vintage_is_not_published_as_a_confirmed_label(column):
    """Legacy JSON can bypass today's parser; it cannot certify its own label."""
    data = framework()
    data["source"]["column"] = column
    row = outturn({"fiscal_framework": data})
    assert row["column"] == "Vintage unconfirmed"
    # An unknown vintage does not invalidate independently reconciled amounts.
    assert row["balance"] == -880.5
    assert row["absent_reason"] is None


def test_stored_missing_vintage_does_not_guess_from_period():
    data = framework()
    del data["source"]["column"]
    row = outturn({"fiscal_framework": data})
    assert row["column"] == "Vintage unconfirmed"
    assert row["balance"] == -880.5


@pytest.mark.parametrize("fy,revenue,label", [
    ("FY 2023/24", 2288.9, "Actual"),
    ("FY 2024/25", 2420.2, "Preliminary"),
    ("FY 2025/26", 2784.4, "Supplementary I"),
    ("FY 2026/27", 2985.7, "Approved"),
])
def test_all_parser_identified_vintages_survive_publication(fy, revenue, label):
    """Use captured publisher headers, including Suppl.1, as positive controls."""
    split = ff.split_for_fiscal_year(edition(), fy, known_ordinary_revenue=revenue)
    data = ff.framework_payload(split, source_url="https://treasury.go.ke/book.pdf", page=63)
    row = fiscal_outturn(SimpleNamespace(meta={"fiscal_framework": data}, fiscal_year=fy))
    assert row["column"] == label
    assert row["balance"] is not None
    assert row["absent_reason"] is None
