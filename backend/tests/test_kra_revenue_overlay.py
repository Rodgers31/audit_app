"""Live-KRA per-tax-head revenue overlay (recommendation #2, full).

The revenue_by_source breakdown (PAYE/VAT/Corporation/Excise/Customs) can now be
refreshed from KRA's FY revenue results — but ONLY through a validated, safe
overlay so a bad parse never replaces the curated fixture. Covers:
  - the per-head text extractor + fiscal-year extractor;
  - the revenue-breakdown validation gate (bands + reconciliation);
  - the overlay (promote when valid+reconciling, reject otherwise, target the
    right FY, leave other years untouched).
"""

from __future__ import annotations

from decimal import Decimal

from seeding.domains.revenue_by_source.fetcher import _overlay_kra_breakdown
from seeding.domains.revenue_by_source.kra_parser import (
    extract_kra_fiscal_year,
    extract_kra_revenue_by_type_from_text,
)
from services.trust_guards import check_revenue_breakdown

KRA_TEXT = """
KRA Revenue Performance for FY 2024/25.
Pay As You Earn (PAYE) contributed Kshs 646 billion.
Value Added Tax (VAT) brought in Kshs 408 billion.
Corporation Tax amounted to Kshs 392 billion.
Excise Duty stood at Kshs 84 billion.
Customs & Border Control collected Kshs 879 billion.
Total revenue was Kshs 2,409 billion.
"""


# ── extractor ───────────────────────────────────────────────────────────
def test_extracts_each_tax_head():
    by_type = extract_kra_revenue_by_type_from_text(KRA_TEXT)
    assert by_type == {
        "PAYE": Decimal("646"),
        "VAT": Decimal("408"),
        "Corporation Tax": Decimal("392"),
        "Excise Duty": Decimal("84"),
        "Customs & Import Duty": Decimal("879"),
    }


def test_extractor_handles_trillions_and_no_match():
    assert extract_kra_revenue_by_type_from_text(
        "PAYE Kshs 1.2 trillion"
    ) == {"PAYE": Decimal("1200.0")}
    assert extract_kra_revenue_by_type_from_text("no figures here") == {}


# Real KRA FY2024/25 press-release wording: money BEFORE the head ("Kshs X
# from P.A.Y.E"), the dotted abbreviation, a "target of Kshs Y" aside that must
# NOT be grabbed for the next head, and sentences run together (HTML-collapsed).
REAL_KRA = (
    "KRA collected Kshs. 2.571 Trillion in the Financial Year 2024/2025. "
    "KRA collected Kshs. 560.963 Billion from P.A.Y.E, achieving 99.0% performance. "
    "Domestic VAT collection stood at Kshs. 327.336 Billion. "
    "On Corporation Tax, KRA collected Kshs. 304.833 Billion against a target of Kshs. 321.080 Billion. "
    "Domestic Excise Duty registered a collection of Kshs. 69.385 Billion. "
    "Customs Revenue recorded a performance rate of 105.9% with a collection of Kshs. 879.329 Billion."
)


def test_extracts_real_kra_press_release_format():
    assert extract_kra_revenue_by_type_from_text(REAL_KRA) == {
        "PAYE": Decimal("560.963"),
        "VAT": Decimal("327.336"),
        "Corporation Tax": Decimal("304.833"),  # not the 321.080 target
        "Excise Duty": Decimal("69.385"),
        "Customs & Import Duty": Decimal("879.329"),
    }
    assert extract_kra_fiscal_year(REAL_KRA) == "FY 2024/25"


def test_extracts_fiscal_year():
    assert extract_kra_fiscal_year(KRA_TEXT) == "FY 2024/25"
    assert extract_kra_fiscal_year("results for 2024/2025 financial year") == "FY 2024/25"
    assert extract_kra_fiscal_year("no year") is None


# ── validation gate ─────────────────────────────────────────────────────
def test_gate_passes_reconciling_breakdown():
    by_type = {"PAYE": 646, "VAT": 408, "Corporation Tax": 392}
    assert check_revenue_breakdown(by_type, expected_total=1446) == []


def test_gate_flags_non_reconciling_sum():
    by_type = {"PAYE": 646, "VAT": 408}  # sums to 1054
    notes = check_revenue_breakdown(by_type, expected_total=2380)
    assert any("reconcile" in n for n in notes)


def test_gate_flags_implausible_head():
    notes = check_revenue_breakdown({"PAYE": 9999}, expected_total=None)
    assert any("cap" in n for n in notes)


# ── overlay ─────────────────────────────────────────────────────────────
def _payload():
    return [
        {"fiscal_year": "FY 2024/25", "revenue_type": "PAYE", "category": "tax", "amount_billion_kes": 640},
        {"fiscal_year": "FY 2024/25", "revenue_type": "VAT", "category": "tax", "amount_billion_kes": 400},
        {"fiscal_year": "FY 2024/25", "revenue_type": "Corporation Tax", "category": "tax", "amount_billion_kes": 390},
        {"fiscal_year": "FY 2024/25", "revenue_type": "Excise Duty", "category": "tax", "amount_billion_kes": 80},
        {"fiscal_year": "FY 2024/25", "revenue_type": "Customs & Import Duty", "category": "tax", "amount_billion_kes": 870},
        {"fiscal_year": "FY 2023/24", "revenue_type": "PAYE", "category": "tax", "amount_billion_kes": 600},
    ]


def test_overlay_promotes_reconciling_breakdown_for_target_fy():
    by_type = {"PAYE": 646, "VAT": 408, "Corporation Tax": 392, "Excise Duty": 84, "Customs & Import Duty": 879}
    payload, status = _overlay_kra_breakdown(_payload(), by_type, "FY 2024/25")
    assert status.startswith("promoted:5")
    paye_2425 = next(r for r in payload if r["fiscal_year"] == "FY 2024/25" and r["revenue_type"] == "PAYE")
    assert paye_2425["amount_billion_kes"] == 646
    assert paye_2425["_revenue_source"] == "kra_live"
    # The other fiscal year must be untouched.
    paye_2324 = next(r for r in payload if r["fiscal_year"] == "FY 2023/24")
    assert paye_2324["amount_billion_kes"] == 600


def test_overlay_rejects_non_reconciling_keeps_fixture():
    by_type = {"PAYE": 6460}  # 10x — won't reconcile to ~2380
    payload, status = _overlay_kra_breakdown(_payload(), by_type, "FY 2024/25")
    # The status now carries the failing check's own note, so the nightly says
    # WHY rather than only that something failed. 6,460B trips the per-head cap
    # before the sum is ever compared.
    assert status.startswith("failed_validation")
    assert "PAYE" in status and "cap" in status
    paye = next(r for r in payload if r["fiscal_year"] == "FY 2024/25" and r["revenue_type"] == "PAYE")
    assert paye["amount_billion_kes"] == 640  # unchanged


def test_overlay_noop_on_empty():
    payload, status = _overlay_kra_breakdown(_payload(), {}, "FY 2024/25")
    assert status == "no_live_value"
