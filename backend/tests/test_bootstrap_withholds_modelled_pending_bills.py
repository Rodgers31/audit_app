"""Bootstrap writes no county money, and only the Treasury BROP publishes pending bills.

``enhanced_county_data.json`` sets every county's pending bills at a flat 8%
of a budget that is itself population x KSh 4,500 — the same ratio for all 47
counties, which is what a formula looks like, not a set of measurements. The
`pending_bills` domain publishes the real per-county figures from the
Treasury's Budget Review and Outlook Paper.

This started as a deferral ("write the modelled figure only where the BROP has
none"), then became "write the debt row but not the pending-bills row". As of
#238 bootstrap writes no county money at all — no budget lines, no debt, no
pending bills — because every one of those rows either competed with a live
domain's rows or sat in the database as a figure the gates had to keep
catching. Bootstrap keeps the reference skeleton.

The gate changed with it. "Sourced" used to mean "not bootstrap's modelled
row", and the pending-bills FIXTURE's invented county figures passed that
test. A row is now published only when it declares the BROP.
"""

import pytest

from models import Base, BudgetLine, DebtCategory, Entity, EntityType, Loan


@pytest.fixture()
def seeded_from_scratch(monkeypatch):
    """A full ``initialize_reference_data`` run against an empty database."""
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker

    import bootstrap

    @compiles(JSONB, "sqlite")
    def _c(t, c, **kw):  # pragma: no cover
        return "TEXT"

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    monkeypatch.setattr(bootstrap, "SessionLocal", Sess)

    bootstrap.initialize_reference_data()

    with Sess() as s:
        yield s


def _county_ids(session):
    return [
        e.id
        for e in session.query(Entity).filter(Entity.type == EntityType.COUNTY).all()
    ]


class TestBootstrapWritesNoCountyMoney:
    def test_the_skeleton_is_still_there(self, seeded_from_scratch):
        """Control: the run happened and seeded the 47 counties."""
        assert len(_county_ids(seeded_from_scratch)) == 47

    def test_no_county_budget_line(self, seeded_from_scratch):
        """RED before #238: 470 modelled sector lines under FY2025/26."""
        ids = _county_ids(seeded_from_scratch)
        rows = (
            seeded_from_scratch.query(BudgetLine)
            .filter(BudgetLine.entity_id.in_(ids))
            .count()
        )
        assert rows == 0, f"bootstrap wrote {rows} county budget line(s)"

    def test_no_county_loan_of_any_kind(self, seeded_from_scratch):
        """RED before #238: 47 modelled "County Government Debt" rows."""
        ids = _county_ids(seeded_from_scratch)
        rows = seeded_from_scratch.query(Loan).filter(Loan.entity_id.in_(ids)).all()
        assert not rows, (
            f"bootstrap wrote {len(rows)} county loan row(s), e.g. "
            f"{[(r.lender, float(r.outstanding or 0)) for r in rows[:2]]}"
        )


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
                else {
                    "source": "cob_pending_bills_etl",
                    "publication": "treasury_brop",
                    "notes": "Treasury BROP Table 10",
                }
            ),
        )

    @staticmethod
    def _fixture_row(amount):
        """What a night on the pending-bills fixture wrote for Nairobi."""
        from types import SimpleNamespace

        return SimpleNamespace(
            debt_category=SimpleNamespace(value="pending_bills"),
            outstanding=amount,
            principal=amount,
            provenance={
                "source": "cob_pending_bills_etl",
                "fiscal_year": "FY2024/25",
                "category": "county",
                "source_url": "https://cob.go.ke/reports/pending-bills/",
            },
        )

    def test_a_fixture_row_is_not_published(self):
        """RED before #238: the fixture's invented 98.7B passed as sourced."""
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._fixture_row(98_700_000_000)]) is None

    def test_a_brop_row_beside_a_fixture_row_is_the_figure(self):
        from services.publication_gate import county_pending_bills

        loans = [
            self._fixture_row(98_700_000_000),
            self._loan(86_769_200_000, modelled=False),
        ]
        assert county_pending_bills(loans) == 86_769_200_000

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


class TestCountyDebtGate:
    """``county_debt_total`` and ``_debt_sustainability``.

    The modelled "County Government Debt" row was a flat 15% of a budget that
    was itself population x KSh 4,500 — the same ratio for all 47 counties.
    With it gone, 43 counties have no sourced debt at all, and what they get
    told about themselves has to reflect that.
    """

    @staticmethod
    def _loan(amount, *, modelled: bool, category=None):
        """A stand-in carrying the REAL DebtCategory enum.

        ``_is_debt_loan`` compares against the enum member, so a namespace
        with a matching ``.value`` sails past it and a pending-bills row would
        be counted as debt — which is what this fixture did at first.
        """
        from types import SimpleNamespace

        from models import DebtCategory

        return SimpleNamespace(
            debt_category=category if category is not None else DebtCategory.OTHER,
            outstanding=amount,
            principal=amount,
            provenance=(
                [{"source": "bootstrap", "dataset": "enhanced_county_data.json"}]
                if modelled
                else [{"dataset_id": "national-debt"}]
            ),
        )

    def test_a_sourced_debt_row_is_published(self):
        import main

        assert main.county_debt_total([self._loan(13_114_825_391, modelled=False)]) == 13_114_825_391

    def test_a_modelled_debt_row_is_not(self):
        import main

        assert main.county_debt_total([self._loan(450_065_025, modelled=True)]) is None

    def test_a_county_with_no_debt_rows_is_absent_not_zero(self):
        import main

        result = main.county_debt_total([])

        assert result is None
        assert result != 0

    def test_pending_bills_are_not_counted_as_debt(self):
        """The rule _is_debt_loan exists to enforce, still enforced here."""
        import main

        from models import DebtCategory

        loans = [
            self._loan(2_345_000, modelled=False, category=DebtCategory.PENDING_BILLS)
        ]

        assert main.county_debt_total(loans) is None

    def test_no_assessment_is_made_without_a_debt_figure(self):
        """The reassuring answer was the wrong one.

        Reading an absent numerator as 0 made the ratio 0%, which is below
        the 20% threshold, which returned "sustainable" — the most confident
        of the three labels, about a county nobody had measured.
        """
        import main

        assert main._debt_sustainability(None, 8_983_760_000) is None

    def test_no_assessment_without_a_budget_either(self):
        import main

        assert main._debt_sustainability(346_300_000, 0) is None

    @pytest.mark.parametrize(
        "debt,expected",
        [(1_000_000, "sustainable"), (3_000_000, "moderate"), (5_000_000, "at_risk")],
    )
    def test_the_thresholds_still_work(self, debt, expected):
        import main

        assert main._debt_sustainability(debt, 10_000_000) == expected


class TestListAndDetailAgreeOnDebt:
    """A figure one page withholds must not appear on the other.

    The detail endpoint gated each county debt row; the list endpoint did not.
    So Nairobi read "13.1B" on /counties and "—" on /counties/nairobi, for the
    same row, on the same data. Both now ask the same question.
    """

    @staticmethod
    def _wb_loan(amount, doc):
        from types import SimpleNamespace

        from models import DebtCategory

        return SimpleNamespace(
            debt_category=DebtCategory.OTHER,
            lender="World Bank (County Infrastructure)",
            outstanding=amount,
            principal=amount,
            provenance=[{"dataset_id": "national-debt"}],
            source_document=doc,
        )

    def test_a_sovereign_creditor_with_no_authorisation_is_withheld(self):
        """The four surviving rows, exactly.

        They name the World Bank and cite treasury.go.ke/public-debt/ — a
        section index. A county cannot borrow from the World Bank without an
        instrument, and a landing page is not one.
        """
        import main
        from types import SimpleNamespace

        doc = SimpleNamespace(
            title="National Treasury Public Debt Bulletin Q3 2024",
            url="https://www.treasury.go.ke/public-debt/",
            doc_type=None,
        )

        assert main.county_debt_total([self._wb_loan(13_114_825_391, doc)]) is None

    def test_a_domestic_lender_is_not_gated_on_an_instrument(self):
        """The gate targets creditors that only lend to sovereigns.

        Without this the check would be a filter that nothing can pass, which
        is not a gate.
        """
        import main
        from types import SimpleNamespace

        from models import DebtCategory

        loan = SimpleNamespace(
            debt_category=DebtCategory.OTHER,
            lender="Equity Bank",
            outstanding=500_000_000,
            principal=500_000_000,
            provenance=[{"dataset_id": "county-debt"}],
            source_document=None,
        )

        assert main.county_debt_total([loan]) == 500_000_000
