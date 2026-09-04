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


class _Doc:
    """The three document fields the gate reads."""

    def __init__(self, title="", publisher="", url=""):
        self.title = title
        self.publisher = publisher
        self.url = url


#: What production rows actually point at: a national debt bulletin. It names
#: the creditor but authorises no county to borrow from it.
CBK_BULLETIN = _Doc(
    title="Public Debt — Monthly Statistical Bulletin",
    publisher="Central Bank of Kenya",
    url="https://www.centralbank.go.ke/public-debt/",
)

#: What would actually authorise the borrowing (Article 212).
NATIONAL_GUARANTEE = _Doc(
    title="Kenya Gazette Notice — National Government Guarantee, Mombasa County",
    publisher="Government Printer",
    url="https://gazette.go.ke/2024/guarantee-047",
)


class _Loan:
    """The fields the gate reads. Not the ORM model on purpose: the gate must
    not need a database to be exercised."""

    def __init__(self, lender, source_document=None):
        self.lender = lender
        self.source_document = source_document


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
    # row resolves to a gazetted national guarantee. It publishes.
    assert (
        county_debt_instrument_failure(
            _Loan("World Bank (County Infrastructure)", NATIONAL_GUARANTEE)
        )
        is None
    )


def test_a_source_document_that_is_not_an_authorisation_does_not_count():
    """The production condition, and the reason an FK check would be useless.

    ``Loan.source_document_id`` is ``nullable=False`` (models.py:281-283), so
    every persisted row HAS a document — checking only that the FK is set is a
    check that cannot fail.  What production rows point at is a CBK debt
    bulletin, which lists the World Bank as a creditor of the Republic but
    authorises no county to borrow from it.
    """
    assert (
        county_debt_instrument_failure(
            _Loan("World Bank (County Infrastructure)", CBK_BULLETIN)
        )
        == "external_creditor_document_is_not_a_borrowing_authorisation"
    )


def test_a_row_with_no_resolvable_document_is_withheld():
    assert (
        county_debt_instrument_failure(_Loan("World Bank (County Infrastructure)"))
        == "external_creditor_no_source_document"
    )


def test_missing_lender_is_not_treated_as_external():
    assert county_debt_instrument_failure(_Loan(None)) is None
    assert county_debt_instrument_failure(_Loan("")) is None


# ── The endpoint's use of the gate: parts must still sum to the whole ──────

def _mombasa_production_rows():
    """The four rows GET /api/v1/counties/047/comprehensive served on
    2026-09-03, verbatim. `category` is what the endpoint reports. Every row
    carries the CBK bulletin it was seeded from — which is exactly why an
    FK-presence check would pass all four."""
    from models import DebtCategory

    return [
        _LoanRow("World Bank (County Infrastructure)", 8_000_000_000, 6_334_420_131.22,
                 DebtCategory.OTHER, CBK_BULLETIN),
        _LoanRow("County Government Debt", 1_468_124_595, 1_468_124_595,
                 DebtCategory.OTHER, CBK_BULLETIN),
        _LoanRow("Pending Bills", 782_999_784, 782_999_784,
                 DebtCategory.PENDING_BILLS, CBK_BULLETIN),
        _LoanRow("Pending Bills — County Governments (Mombasa County)",
                 3_867_700_000, 3_867_700_000, DebtCategory.PENDING_BILLS,
                 CBK_BULLETIN),
    ]


class _LoanRow(_Loan):
    def __init__(self, lender, principal, outstanding, category, source_document):
        super().__init__(lender, source_document)
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

    assert withheld == {"external_creditor_document_is_not_a_borrowing_authorisation": 1}
    assert [r.lender for r in kept] == [
        "County Government Debt",
        "Pending Bills",
        "Pending Bills — County Governments (Mombasa County)",
    ]

    after_total = sum(float(r.outstanding) for r in kept if _is_debt_loan(r))
    assert round(after_total) == 1_468_124_595

    assert all(county_debt_instrument_failure(r) is None for r in kept)


# ── The shipped path: breakdown and total must agree in the real response ───

def test_serialized_breakdown_sums_to_the_serialized_total(client, db_session):
    """Assert against what the endpoint actually returns, not a local mirror.

    The previous version of this test recomputed the filtered sum and compared
    it to itself, so it could not fail.  It also missed a real defect: the
    handler put every kept row into ``debt_breakdown`` while ``total_debt``
    excluded pending bills, so the breakdown summed to KES 6.119B beside a
    printed total of KES 1.468B.
    """
    from datetime import datetime, timezone

    from models import (
        Country,
        DebtCategory,
        DocumentStatus,
        DocumentType,
        Entity,
        EntityType,
        Loan,
        SourceDocument,
    )

    country = Country(
        id=1, iso_code="KEN", name="Kenya", currency="KES",
        timezone="Africa/Nairobi", default_locale="en_KE",
    )
    db_session.add(country)
    db_session.flush()

    bulletin = SourceDocument(
        country_id=country.id,
        publisher="Central Bank of Kenya",
        title="Public Debt - Monthly Statistical Bulletin",
        url="https://www.centralbank.go.ke/public-debt/",
        fetch_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.OTHER,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(bulletin)
    db_session.flush()

    entity = Entity(
        country_id=country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    for lender, principal, outstanding, category in (
        # Withheld: sovereign-only creditor, document is a bulletin not a guarantee.
        ("World Bank (County Infrastructure)", 8_000_000_000, 6_334_420_131, DebtCategory.OTHER),
        # Published, and counted in total_debt.
        ("County Government Debt", 1_468_124_595, 1_468_124_595, DebtCategory.OTHER),
        # Published elsewhere, but NOT part of total_debt - arrears, not borrowing.
        ("Pending Bills", 782_999_784, 782_999_784, DebtCategory.PENDING_BILLS),
    ):
        db_session.add(
            Loan(
                entity_id=entity.id, lender=lender, debt_category=category,
                principal=principal, outstanding=outstanding, currency="KES",
                source_document_id=bulletin.id,
                issue_date=datetime(2020, 1, 1),
            )
        )
    db_session.commit()

    debt = client.get("/api/v1/counties/047/comprehensive").json()["debt"]

    breakdown = debt["breakdown"]
    total = debt.get("total_debt")
    assert total is not None, f"endpoint returned no total_debt: {list(debt)[:20]}"

    lenders = [r["lender"] for r in breakdown]
    assert "World Bank (County Infrastructure)" not in lenders, (
        "the withheld sovereign-creditor row is still being published"
    )
    assert "Pending Bills" not in lenders, (
        "pending bills are in the breakdown but excluded from total_debt, so "
        "the parts no longer sum to the whole"
    )
    assert round(sum(r["outstanding"] for r in breakdown)) == round(total), (
        f"breakdown sums to {sum(r['outstanding'] for r in breakdown)} but the "
        f"page prints {total}"
    )
