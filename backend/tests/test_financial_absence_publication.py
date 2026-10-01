"""#240 actual shipping boundaries: absence is not a measured zero."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from models import BudgetLine, FiscalSummary, Loan, DebtCategory

# ETL ships alongside backend; append so backend/seeding keeps precedence.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from etl.knbs_parser import KNBSParser
from etl.pending_bills_extractor import PendingBillsExtractor


@pytest.mark.parametrize("value", [None, 0, 12])
def test_budget_line_readers_preserve_absence_and_sourced_zero(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc, value
):
    row = BudgetLine(
        entity_id=seed_entity.id,
        period_id=seed_fiscal_period.id,
        category="Education",
        allocated_amount=12,
        actual_spent=value,
        committed_amount=value,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add(row)
    db_session.flush()
    responses = [
        client.get(
            f"/api/v1/entities/{seed_entity.id}/periods/{seed_fiscal_period.id}/budget_lines"
        ),
        client.get("/api/v1/search?q=Education"),
    ]
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    lines = [
        responses[0].json()["items"][0],
        responses[1].json()["results"]["budget_lines"][0],
    ]
    for line in lines:
        assert line["allocated_amount"] == 12
        assert line["actual_spent"] == value
        if value is None:
            assert line["absent_reasons"]["actual_spent"] == "not_reported"
        assert line["currency"] == "KES"
        assert line["source_document_id"] == seed_source_doc.id
    assert lines[0]["committed_amount"] == value


@pytest.mark.parametrize("value", [None, 0, 12])
def test_fiscal_history_does_not_invent_missing_money_or_ratio(
    client, db_session, value
):
    db_session.add(
        FiscalSummary(
            fiscal_year="2024/25",
            unit="KES",
            appropriated_budget=100e9,
            total_revenue=70e9,
            total_borrowing=30e9,
            county_allocation=10e9,
            tax_revenue=value,
            borrowing_pct_of_budget=value,
            page_ref="p.42",
        )
    )
    db_session.flush()
    response = client.get("/api/v1/budget/overview")
    assert response.status_code == 200, response.text
    row = response.json()["fiscal_history"][0]
    assert row["appropriated_budget"] == 100
    assert row["tax_revenue"] == (None if value is None else value / 1e9)
    assert row["borrowing_pct_of_budget"] == value
    if value is None:
        assert row["absent_reasons"]["tax_revenue"] == "not_reported"
        assert row["absent_reasons"]["borrowing_pct_of_budget"] == "not_reported"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("GDP growth of 5.4% was reported in the Economic Survey for Kenya.", None),
        ("GDP growth of 0% was reported in the Economic Survey for Kenya.", None),
        (
            "GDP KSh 12.7 trillion was reported in the Economic Survey for Kenya.",
            12.7e12,
        ),
    ],
)
def test_gdp_text_growth_is_not_a_zero_level(text, expected):
    row = KNBSParser()._extract_gdp_from_text(text, 2024)
    assert row is not None
    assert row.gdp_value == expected
    if expected is None:
        assert row.gdp_absent_reason == "level_not_reported"


@pytest.mark.parametrize(
    "level,growth,expected", [("-", "5.4", None), ("0", "0", 0), ("12", "5.4", 12e9)]
)
def test_gdp_table_growth_is_not_a_zero_level(level, growth, expected):
    out = {"gdp_data": []}
    KNBSParser()._extract_gdp_from_table(
        [["Year", "Growth", "GDP"], ["2024", growth, level]], out, {"year": 2024}
    )
    row = out["gdp_data"][0]
    assert row["gdp_value"] == expected
    if expected is None:
        assert row["gdp_absent_reason"] == "level_not_reported"


@pytest.mark.parametrize(
    "total,eligible,ineligible,expected",
    [
        ("-", "10", "-", None),
        ("-", "-", "2", None),
        ("-", "0", "0", 0),
        ("-", "10", "2", 12),
        ("0", "-", "-", 0),
        ("12", "10", "2", 12),
        ("11", "10", "2", None),
        ("-", "NaN", "2", None),
    ],
)
def test_pending_table_never_completes_a_partial_total(
    tmp_path, total, eligible, ineligible, expected
):
    row = PendingBillsExtractor(tmp_path)._parse_pending_bills_table(
        [
            ["Entity", "Total", "Eligible", "Ineligible"],
            ["Education Agency", total, eligible, ineligible],
        ],
        "FY2024/25",
    )[0]
    assert row["total_pending"] == expected
    if expected is None:
        assert row["total_pending_absent_reason"]
    if expected == 0:
        assert row["printed_zero"] is True


@pytest.mark.parametrize(
    "text,expected",
    [
        ("National government pending bills stood at KES 10 billion.", None),
        (
            "National government pending bills stood at KES 10 billion. County pending bills of KES 2 billion. As at 30 June 2025.",
            12e9,
        ),
    ],
)
def test_pending_summary_needs_both_components(tmp_path, text, expected):
    pdf = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    result = PendingBillsExtractor(tmp_path)._extract_summary_from_text(
        pdf, [0], "FY2024/25"
    )
    assert result["total_national"] == 10e9
    assert result["grand_total"] == expected
    if expected is None:
        assert result["grand_total_absent_reason"] == "incomplete_components"


def _debt_row(**changes):
    values = dict(
        lender="County Government Debt",
        outstanding=20,
        principal=100,
        debt_category=DebtCategory.OTHER,
        currency="KES",
        source_document_id=1,
        source_document=SimpleNamespace(
            title="County debt report",
            publisher="County Treasury",
            url="https://example.invalid/synthetic.pdf",
        ),
        entity_id=1,
        issue_date=datetime(2020, 1, 1),
        basis="actual",
        provenance={"as_at": "2025-06-30"},
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("amount,expected", [(None, None), (0, 0), (20, 20)])
def test_county_debt_uses_outstanding_never_original_principal(amount, expected):
    from main import county_debt_total

    assert county_debt_total([_debt_row(outstanding=amount)]) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"outstanding": None},
        {"outstanding": float("nan")},
        {"outstanding": True},
        {"outstanding": -1},
        {"currency": "USD"},
        {"provenance": {"as_at": "2024-06-30"}},
        {"basis": "projected"},
        {"entity_id": 2},
        {"provenance": {}},
    ],
)
def test_county_debt_cannot_publish_a_partial_or_incompatible_total(change):
    from main import county_debt_total

    other = _debt_row(lender="County Bank B", **change)
    assert county_debt_total([_debt_row(), other]) is None


def test_county_debt_complete_same_account_control():
    from main import county_debt_total

    assert county_debt_total([_debt_row(), _debt_row(lender="County Bank B")]) == 40


@pytest.mark.parametrize("amount", [0, 20])
def test_county_debt_http_preserves_outstanding_zero(
    client, db_session, seed_entity, seed_source_doc, amount
):
    loan = Loan(
        entity_id=seed_entity.id,
        lender="County Government Debt",
        principal=100,
        outstanding=amount,
        currency="KES",
        source_document_id=seed_source_doc.id,
        issue_date=datetime(2020, 1, 1),
        debt_category=DebtCategory.OTHER,
        provenance={"as_at": "2025-06-30"},
        page_ref="p.42",
    )
    db_session.add(loan)
    db_session.flush()
    response = client.get("/api/v1/counties/001/comprehensive")
    assert response.status_code == 200, response.text
    debt = response.json()["debt"]
    assert debt["total_debt"] == debt["breakdown"][0]["outstanding"] == amount
    assert debt["breakdown"][0]["principal"] == 100
    assert debt["total_debt_absent_reason"] is None


def test_sources_sql_count_is_measured(client, seed_source_doc):
    response = client.get("/api/v1/sources/summary")
    assert response.status_code == 200
    assert response.json()["total_documents"] == 1
    assert response.json()["sources"][0]["document_count"] == 1


@pytest.mark.parametrize(
    "date,amount,allocation,expected",
    [
        ("2025-06-30", 20, 100, 20),
        ("2025-06-30", 0, 100, 0),
        (None, 20, 100, None),
        ("2024-06-30", 20, 100, None),
        ("2025-06-30", 20, 0, None),
    ],
)
def test_final_comprehensive_ratio_requires_same_source_stock_day(
    client,
    db_session,
    seed_entity,
    seed_fiscal_period,
    seed_source_doc,
    date,
    amount,
    allocation,
    expected,
):
    from models import FigureBasis

    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=allocation,
            actual_spent=0,
            currency="KES",
            page_ref="p.42",
            basis=FigureBasis.ACTUAL,
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.add(
        Loan(
            entity_id=seed_entity.id,
            lender="Synthetic County Bank",
            principal=100,
            outstanding=amount,
            currency="KES",
            source_document_id=seed_source_doc.id,
            issue_date=datetime(2020, 1, 1),
            debt_category=DebtCategory.OTHER,
            basis=FigureBasis.ACTUAL,
            provenance={"as_at": date} if date else {},
            page_ref="p.42",
        )
    )
    db_session.flush()
    response = client.get("/api/v1/counties/001/comprehensive")
    assert response.status_code == 200, response.text
    debt = response.json()["debt"]
    assert debt["total_debt"] == amount
    assert debt["debt_to_budget_ratio"] == expected
    assert (debt["debt_to_budget_ratio_absent_reason"] is None) == (
        expected is not None
    )


@pytest.mark.parametrize("metadata", [["unexpected"], True, "unexpected"])
def test_fiscal_unknown_metadata_shape_does_not_destroy_sourced_amounts(
    client, db_session, metadata
):
    db_session.add(
        FiscalSummary(
            fiscal_year="2024/25",
            unit="KES",
            appropriated_budget=100e9,
            total_revenue=70e9,
            total_borrowing=30e9,
            page_ref="p.42",
            meta=metadata,
        )
    )
    db_session.flush()
    response = client.get("/api/v1/budget/overview")
    assert response.status_code == 200, response.text
    row = response.json()["fiscal_history"][0]
    assert row["appropriated_budget"] == 100
    assert row["metadata_absent_reason"] == "invalid_metadata"


def test_unknown_fiscal_unit_is_withheld_with_reason(client, db_session):
    db_session.add(
        FiscalSummary(
            fiscal_year="2024/25",
            unit="USD",
            appropriated_budget=100,
            total_revenue=70,
            total_borrowing=30,
            page_ref="p.42",
        )
    )
    db_session.flush()
    response = client.get("/api/v1/budget/overview")
    assert response.status_code == 200
    assert response.json()["fiscal_history"] == []
    assert response.json()["fiscal_history_withheld"][0]["reason"] == "unsupported_unit"


@pytest.mark.parametrize(
    "metadata",
    [
        {"as_at": "2025-06-30", "as_of": "2024-06-30"},
        {"as_at": "2025-06-30", "data_quality": "modelled"},
    ],
)
def test_conflicting_or_unreported_debt_metadata_cannot_certify_total(metadata):
    from main import county_debt_total

    assert county_debt_total([_debt_row(provenance=metadata)]) is None


@pytest.mark.parametrize("alias", ["county government debt", "County Government Debt "])
def test_ambiguous_lender_date_is_not_complete_instrument_identity(alias):
    from services.financial_publication import county_debt_summary

    summary = county_debt_summary([_debt_row(), _debt_row(lender=alias)])
    assert summary["total_debt"] is None
    assert summary["total_debt_absent_reason"] == "ambiguous_instrument_identity"
    # Same lender/date can represent legitimate, source-identified instruments.
    first = _debt_row(provenance={"as_at": "2025-06-30", "instrument_id": "A"})
    second = _debt_row(
        lender=alias, provenance={"as_at": "2025-06-30", "instrument_id": "B"}
    )
    assert county_debt_summary([first, second])["total_debt"] == 40


@pytest.mark.parametrize("row", ["A0", {0: "Agency", 1: "0"}])
def test_pending_malformed_row_is_not_source_zero(tmp_path, row):
    assert (
        PendingBillsExtractor(tmp_path)._parse_pending_bills_table(
            [["Entity", "Total"], row], "FY2024/25"
        )
        == []
    )


@pytest.mark.parametrize("row", ["20", {0: 2024, 1: 0}])
def test_gdp_malformed_row_is_not_source_zero(row):
    out = {"gdp_data": []}
    KNBSParser()._extract_gdp_from_table([["Year", "GDP"], row], out, {"year": 2024})
    assert out["gdp_data"] == []


@pytest.mark.parametrize(
    "text",
    [
        "County pending bills of KES 2 billion.",
        "National government pending bills stood at KES 10 million. County pending bills of KES 2 billion. "
        "As at 30 June 2024. As at 30 June 2025.",
    ],
)
def test_pending_summary_cannot_duplicate_scope_or_mix_dates(tmp_path, text):
    pdf = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    result = PendingBillsExtractor(tmp_path)._extract_summary_from_text(
        pdf, [0], "FY2024/25"
    )
    assert result["grand_total"] is None
    assert result["grand_total_absent_reason"]
    if text.startswith("County"):
        assert result["total_national"] is None and result["total_county"] == 2e9
    else:
        assert result["total_national"] == 10e6 and result["total_county"] == 2e9


@pytest.mark.parametrize(
    "header", ["Eligible (USD)", "Eligible projected 2023", "Eligible (2023/24)"]
)
def test_pending_table_does_not_combine_incompatible_accounts(tmp_path, header):
    rows = PendingBillsExtractor(tmp_path)._parse_pending_bills_table(
        [
            ["Entity", "Total", header, "Ineligible (KES actual 2024/25)"],
            ["Education Agency", "-", "10", "2"],
        ],
        "FY2024/25",
    )
    assert rows[0]["total_pending"] is None
    assert rows[0]["total_pending_absent_reason"] == "incompatible_component_context"


@pytest.mark.parametrize(
    "headers",
    [
        ["Eligible KES actual 2024", "Ineligible KES actual 2025"],
        ["Eligible KES million", "Ineligible KES billion"],
    ],
)
def test_pending_table_component_contexts_must_agree(tmp_path, headers):
    row = PendingBillsExtractor(tmp_path)._parse_pending_bills_table(
        [["Entity", *headers], ["Education Agency", "10", "2"]], "FY2024/25"
    )[0]
    assert row["total_pending"] is None
    assert row["total_pending_absent_reason"] == "incompatible_component_context"


@pytest.mark.parametrize(
    "text",
    [
        "National government pending bills stood at KES 10 billion. National government pending bills stood at KES 11 billion. County pending bills of KES 2 billion.",
        "National government pending bills stood at KES 10 billion on a projected basis. County pending bills of KES 2 billion on an actual basis.",
        "National government pending bills stood at KES 10 billion on a cash basis. County pending bills of KES 2 billion on an accrual basis.",
        "For FY2023/24, national government pending bills stood at KES 10 billion. For FY2024/25, county pending bills of KES 2 billion.",
        "Values denominated in USD. National government pending bills stood at 10 billion. County pending bills of 2 billion.",
    ],
)
def test_pending_summary_conflicting_observations_are_absent(tmp_path, text):
    pdf = SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: "As at 30 June 2025. " + text)]
    )
    summary = PendingBillsExtractor(tmp_path)._extract_summary_from_text(
        pdf, [0], "FY2024/25"
    )
    assert summary["grand_total"] is None
    assert summary["grand_total_absent_reason"]


@pytest.mark.parametrize("reason_on", ["debt", "budget"])
def test_debt_ratio_respects_explicit_amount_rejection(reason_on):
    from services.financial_publication import county_debt_budget_ratio

    debt = dict(
        total_debt=20, debt_basis="actual", debt_currency="KES", debt_as_at="2025-06-30"
    )
    budget = dict(
        total_allocation=100,
        currency="KES",
        fiscal_period=dict(start_date="2024-07-01", end_date="2025-06-30"),
    )
    if reason_on == "debt":
        debt["total_debt_absent_reason"] = "ambiguous_instrument_identity"
    else:
        budget["absent_reasons"] = {"total_allocation": "invalid_metadata"}
    result = county_debt_budget_ratio(debt, budget)
    assert result["debt_to_budget_ratio"] is None
    assert result["debt_to_budget_ratio_absent_reason"]


def test_gdp_loader_supports_existing_direct_module_import():
    import os
    import subprocess

    command = "import asyncio; from database_loader import DatabaseLoader; asyncio.run(DatabaseLoader.__new__(DatabaseLoader)._load_gdp_item(None, {'gdp_value': None}, 1, 1))"
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path(__file__).resolve().parents[2] / "etl",
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("value", ["0,0", "0 0", "1,2", "1 2"])
@pytest.mark.parametrize("layout", ["gdp", "gcp"])
def test_malformed_gdp_grouping_cannot_become_reported_zero(value, layout):
    out = {"gdp_data": []}
    table = (
        [["Year", "GDP"], ["2024", value]]
        if layout == "gdp"
        else [["Activity", "2024"], ["Gross County Product", value]]
    )
    KNBSParser()._extract_gdp_from_table(
        table, out, {"year": 2024, "county": "Synthetic County"}
    )
    assert out["gdp_data"] == []


@pytest.mark.parametrize("value,expected", [("0", 0), ("1,234", 1234), ("1 234", 1234)])
def test_valid_gdp_grouping_and_zero_survive(value, expected):
    from etl.gdp_values import reported_gdp_level

    assert reported_gdp_level(value) == expected


def test_pending_extraction_keeps_null_total_without_formatting_crash(
    tmp_path, monkeypatch
):
    import asyncio
    from unittest.mock import AsyncMock

    extractor = PendingBillsExtractor(tmp_path)
    monkeypatch.setattr(
        extractor,
        "_discover_latest_report",
        AsyncMock(return_value=("https://example.invalid/synthetic.pdf", "FY2024/25")),
    )
    monkeypatch.setattr(
        extractor,
        "_download_report_pdf",
        AsyncMock(return_value=tmp_path / "synthetic.pdf"),
    )
    monkeypatch.setattr(
        extractor,
        "_extract_pending_bills_from_pdf",
        lambda *args: {
            "bills": [],
            "summary": {
                "grand_total": None,
                "grand_total_absent_reason": "incomplete_components",
            },
        },
    )
    assert asyncio.run(extractor.extract_all())["summary"]["grand_total"] is None
