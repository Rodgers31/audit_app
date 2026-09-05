"""The modelled pending-bills figure is never written.

``enhanced_county_data.json`` sets every county's pending bills at a flat 8%
of a budget that is itself population x KSh 4,500 — the same ratio for all 47
counties, which is what a formula looks like, not a set of measurements. The
`pending_bills` domain publishes the real per-county figures from Table 10 of
the Treasury's Budget Review and Outlook Paper.

This started as a deferral: write the modelled figure only where the BROP has
none, so "a county the parse has not reached keeps the only figure it has".
That was wrong. The figure it kept was a fabrication, and the single county it
applied to — Narok — is exactly the one the BROP reports as having submitted
no data at all. So nothing is written now, and a county with no published
figure shows absence.
"""

from datetime import date

import pytest

from models import Country, DebtCategory, DocumentType, Entity, EntityType, Loan, SourceDocument


@pytest.fixture()
def county(db_session):
    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    entity = Entity(
        country_id=country.id, type=EntityType.COUNTY,
        canonical_name="Narok County", slug="narok-county",
    )
    doc = SourceDocument(
        title="Narok County Budget FY2024/25", publisher="County Treasury",
        doc_type=DocumentType.BUDGET, country_id=country.id,
        fetch_date=date(2025, 8, 24),
    )
    db_session.add_all([entity, doc])
    db_session.flush()
    return db_session, entity, doc


def _seed(session, entity, doc, *, debt=1_000_000.0, bills=500_000.0):
    import bootstrap

    bootstrap._upsert_county_debt(
        session,
        entity_id=entity.id,
        county_name="Narok",
        debt_outstanding=debt,
        pending_bills=bills,
        source_document_id=doc.id,
    )
    session.flush()


def _live_row(session, entity, doc):
    session.add(
        Loan(
            entity_id=entity.id,
            lender="Pending Bills — County Governments (Narok County)",
            debt_category=DebtCategory.PENDING_BILLS,
            principal=2_345_000, outstanding=2_345_000, currency="KES",
            issue_date=date(2024, 7, 1), source_document_id=doc.id,
        )
    )
    session.flush()


class TestTheModelledFigureIsNeverWritten:
    def test_the_modelled_figure_is_not_written_when_the_brop_row_exists(self, county):
        session, entity, doc = county
        _live_row(session, entity, doc)

        _seed(session, entity, doc)

        modelled = session.query(Loan).filter(Loan.lender == "Pending Bills").count()
        assert modelled == 0, "the modelled pending-bills row was written anyway"

    def test_it_is_not_written_for_a_county_with_no_brop_row_either(self, county):
        """Narok, which is why this stopped being a deferral.

        The BROP prints an empty row for Narok and a footnote saying the
        entity did not submit. Filling that silence with 8% of a modelled
        budget publishes a figure for the one county that reported none.
        """
        session, entity, doc = county

        _seed(session, entity, doc)

        assert session.query(Loan).filter(Loan.lender == "Pending Bills").count() == 0

    def test_the_deferral_does_not_touch_the_other_loan(self, county):
        """Only pending bills have a live source; the debt row is separate.

        County Government Debt is modelled too — a flat 15% of the same
        modelled budget — but no publisher issues a per-county debt stock, so
        there is nothing for it to defer TO. Suppressing it here would delete
        a figure rather than replace it, which is a different decision.
        """
        session, entity, doc = county
        _live_row(session, entity, doc)

        _seed(session, entity, doc)

        assert session.query(Loan).filter(
            Loan.lender == "County Government Debt"
        ).count() == 1


class TestTheApiGate:
    """``county_pending_bills`` decides what a county's figure IS.

    It has to distinguish absence from zero, because for Narok they are
    different claims and only one of them is true.
    """

    @staticmethod
    def _loan(amount, *, modelled: bool, category="pending_bills"):
        from types import SimpleNamespace

        return SimpleNamespace(
            debt_category=SimpleNamespace(value=category),
            outstanding=amount,
            principal=amount,
            provenance=(
                [{"source": "bootstrap", "dataset": "enhanced_county_data.json"}]
                if modelled
                else {"source": "cob_pending_bills", "notes": "Treasury BROP Table 10"}
            ),
        )

    def test_a_sourced_row_is_published(self):
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._loan(2_345_000, modelled=False)]) == 2_345_000

    def test_a_modelled_row_is_not(self):
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._loan(416_834_280, modelled=True)]) is None

    def test_a_county_with_only_a_modelled_row_reads_as_absent_not_zero(self):
        """Narok, exactly.

        None means "nobody has published this". 0.0 would mean "the county
        owes nothing", which no document says.
        """
        from services.publication_gate import county_pending_bills

        result = county_pending_bills([self._loan(416_834_280, modelled=True)])

        assert result is None
        assert result != 0

    def test_a_county_with_no_loans_at_all_is_absent(self):
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([]) is None

    def test_a_real_zero_is_still_published(self):
        """A publisher CAN report zero, and that is a figure."""
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._loan(0, modelled=False)]) == 0.0

    def test_other_debt_categories_are_ignored(self):
        from services.publication_gate import county_pending_bills

        loans = [self._loan(9_000_000, modelled=False, category="domestic_bonds")]

        assert county_pending_bills(loans) is None

    def test_sourced_rows_are_summed_and_modelled_ones_left_out(self):
        from services.publication_gate import county_pending_bills

        loans = [
            self._loan(1_000_000, modelled=False),
            self._loan(500_000, modelled=False),
            self._loan(416_834_280, modelled=True),
        ]

        assert county_pending_bills(loans) == 1_500_000
