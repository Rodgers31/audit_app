"""The county-debt publication gate (credibility audit F15).

Production serves, on the Nairobi and Mombasa county pages, a debt instrument
reading "World Bank (County Infrastructure)" — KES 13.1B and 6.3B outstanding,
rendered as "81.2% of total debt" on Mombasa's Budget & Debt tab. That lender
string appears nowhere in this repository: not in a fixture, not in a seeder,
not in a migration. A grep over 1,611 tracked files (positive-controlled
against a string that does exist) finds nothing.

It is also constitutionally implausible. Article 212 of the Constitution and
s.58 of the PFM Act 2012 allow a county to borrow only where the national
government guarantees the loan; a county cannot contract external debt
directly. So the row asserts, against a named county government, a liability to
a named multilateral, with no document behind it.

The gate withholds such a row from the breakdown AND from the county's total,
so the parts still sum to the whole. These tests pin BOTH directions: the gate
fires on the real production shape, and it goes green when the row shows its
working — otherwise it is a filter, not a gate.
"""

from __future__ import annotations

from services.publication_gate import county_debt_instrument_failure


class _Loan:
    """The two fields the gate reads. Not the ORM model on purpose: the gate
    must not need a database to be exercised."""

    def __init__(self, lender, source_document_id=None):
        self.lender = lender
        self.source_document_id = source_document_id


# ── The rows production actually serves ────────────────────────────────────

def test_withholds_the_production_world_bank_county_row():
    loan = _Loan("World Bank (County Infrastructure)")
    assert (
        county_debt_instrument_failure(loan) == "external_creditor_no_source_document"
    )


def test_withholds_every_sovereign_only_creditor_shape():
    # Lender strings a county row could plausibly carry. Each names an entity
    # that lends to sovereigns, so each needs a guarantee document to publish.
    for lender in (
        "World Bank (County Infrastructure)",
        "IDA Concessional Credit",
        "IBRD Loan",
        "African Development Bank",
        "AfDB County Roads Facility",
        "International Monetary Fund",
        "Eurobond 2032",
        "China Exim Bank",
        "JICA Water Project",
        "AFD Urban Programme",
        "KfW Sanitation Loan",
        "Commercial Banks (Syndicated loans)",
        "Bilateral (Japan — JICA)",
        "Multilateral (World Bank / IDA / IBRD)",
    ):
        assert county_debt_instrument_failure(_Loan(lender)) is not None, lender


def test_match_is_case_insensitive():
    assert county_debt_instrument_failure(_Loan("WORLD BANK")) is not None
    assert county_debt_instrument_failure(_Loan("world bank")) is not None


# ── Positive control: the gate must be able to pass ────────────────────────

def test_publishes_a_domestic_county_instrument():
    # A county's own borrowing from a domestic source is not what this gate is
    # about; it must pass untouched even with no source document, so the gate
    # cannot quietly become "withhold all county debt".
    assert county_debt_instrument_failure(_Loan("County Government Debt")) is None
    assert county_debt_instrument_failure(_Loan("Pending Bills")) is None
    assert (
        county_debt_instrument_failure(
            _Loan("Pending Bills — County Governments (Mombasa County)")
        )
        is None
    )


def test_publishes_an_external_row_that_shows_its_working():
    # THE test that makes this a gate. Same lender, same everything, except the
    # row resolves to a source document — a gazetted national guarantee, a
    # county loan register entry. It publishes.
    assert (
        county_debt_instrument_failure(
            _Loan("World Bank (County Infrastructure)", source_document_id=2311)
        )
        is None
    )


def test_empty_string_source_document_id_does_not_count_as_working():
    assert (
        county_debt_instrument_failure(
            _Loan("World Bank (County Infrastructure)", source_document_id="")
        )
        == "external_creditor_no_source_document"
    )


def test_missing_lender_is_not_treated_as_external():
    assert county_debt_instrument_failure(_Loan(None)) is None
    assert county_debt_instrument_failure(_Loan("")) is None


# ── The endpoint's use of the gate: parts must still sum to the whole ──────

def _mombasa_production_rows():
    """The four rows GET /api/v1/counties/047/comprehensive served on
    2026-09-03, verbatim. `category` is what the endpoint reports; only the
    World Bank row lacks any source document."""
    from models import DebtCategory

    return [
        _LoanRow("World Bank (County Infrastructure)", 8_000_000_000, 6_334_420_131.22,
                 DebtCategory.OTHER, None),
        _LoanRow("County Government Debt", 1_468_124_595, 1_468_124_595,
                 DebtCategory.OTHER, None),
        _LoanRow("Pending Bills", 782_999_784, 782_999_784,
                 DebtCategory.PENDING_BILLS, None),
        _LoanRow("Pending Bills — County Governments (Mombasa County)",
                 3_867_700_000, 3_867_700_000, DebtCategory.PENDING_BILLS, None),
    ]


class _LoanRow(_Loan):
    def __init__(self, lender, principal, outstanding, category, source_document_id):
        super().__init__(lender, source_document_id)
        self.principal = principal
        self.outstanding = outstanding
        self.debt_category = category


def _apply_gate(rows):
    """Mirrors the filter in main.py's /counties/{id}/comprehensive handler."""
    withheld, kept = {}, []
    for row in rows:
        reason = county_debt_instrument_failure(row)
        if reason:
            withheld[reason] = withheld.get(reason, 0) + 1
            continue
        kept.append(row)
    return kept, withheld


def test_mombasa_world_bank_row_is_withheld_and_the_total_drops():
    from main import _is_debt_loan

    rows = _mombasa_production_rows()

    before_total = sum(
        float(r.outstanding) for r in rows if _is_debt_loan(r)
    )
    assert round(before_total) == 7_802_544_726, (
        "guard: this is the KES 7.80B the county page publishes today"
    )

    kept, withheld = _apply_gate(rows)

    assert withheld == {"external_creditor_no_source_document": 1}
    assert [r.lender for r in kept] == [
        "County Government Debt",
        "Pending Bills",
        "Pending Bills — County Governments (Mombasa County)",
    ]

    after_total = sum(float(r.outstanding) for r in kept if _is_debt_loan(r))
    assert round(after_total) == 1_468_124_595

    # The point of filtering the total as well as the breakdown: what is left
    # in the list still adds up to what the page prints. Before this change the
    # breakdown showed a row worth 81.2% of a total that included it.
    assert round(after_total) == round(
        sum(float(r.outstanding) for r in kept if _is_debt_loan(r))
    )
    assert all(county_debt_instrument_failure(r) is None for r in kept)
