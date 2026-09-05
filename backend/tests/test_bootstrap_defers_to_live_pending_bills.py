"""The modelled pending-bills figure gives way to the published one.

``enhanced_county_data.json`` sets every county's pending bills at a flat 8%
of a budget that is itself population x KSh 4,500 — the same ratio for all 47
counties, which is what a model looks like, not a measurement. The
`pending_bills` domain publishes the real per-county figures from Table 10 of
the Treasury's Budget Review and Outlook Paper.

Writing both puts two different claims about one county's debt side by side.
The deferral is per county, because the BROP parse currently reaches 46 of 47
and a county it misses must keep the only figure it has.
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


class TestDeferral:
    def test_the_modelled_figure_is_skipped_when_the_brop_row_exists(self, county):
        session, entity, doc = county
        _live_row(session, entity, doc)

        _seed(session, entity, doc)

        modelled = session.query(Loan).filter(Loan.lender == "Pending Bills").count()
        assert modelled == 0, "the modelled pending-bills row was written anyway"

    def test_a_county_the_brop_parse_missed_keeps_the_fixture(self, county):
        """POSITIVE CONTROL — Narok is exactly this case in production today."""
        session, entity, doc = county

        _seed(session, entity, doc)

        assert session.query(Loan).filter(Loan.lender == "Pending Bills").count() == 1

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

    def test_another_county_s_live_row_does_not_count(self, county):
        """The check has to be per entity, not per table."""
        session, entity, doc = county
        other = Entity(
            country_id=entity.country_id, type=EntityType.COUNTY,
            canonical_name="Kisii County", slug="kisii-county",
        )
        session.add(other)
        session.flush()
        session.add(
            Loan(
                entity_id=other.id,
                lender="Pending Bills — County Governments (Kisii County)",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=1, outstanding=1, currency="KES",
                issue_date=date(2024, 7, 1), source_document_id=doc.id,
            )
        )
        session.flush()

        _seed(session, entity, doc)

        assert session.query(Loan).filter(Loan.lender == "Pending Bills").count() == 1
