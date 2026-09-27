"""A fiscal year that has STARTED must be publishable before its actuals exist.

/api/v1/fiscal/summary only published a fiscal year once three of
{appropriated_budget, total_revenue, total_borrowing, county_allocation} were
populated. That rule exists for a good reason — World Bank back-fill creates
stub years with one or two fields, and a stub must never become the headline.

It also had a consequence nobody chose: a fiscal year that begins on 1 July
has an ENACTED budget and no outturns at all. It could not reach three fields
until COB published its first quarterly report in mid-November. So every year,
for four and a half months, the site showed the previous fiscal year as
current — which is what "the homepage still says FY 2025/26" on 2026-08-29
actually was. The COB pipeline was working and current the whole time.

The exception is narrow on purpose: the row must carry a declared budget
basis, a source URL and a page reference. A stub has none of those.
"""

from __future__ import annotations

import asyncio

import pytest
from models import FiscalSummary


def fiscal_summary(db_session) -> dict:
    """Call the endpoint directly with an explicit session.

    Deliberately NOT through ``TestClient``: the app object is shared process
    wide and other suites mutate its dependency overrides, startup handlers and
    response cache, which is the documented source of this repo's
    order-dependent test failures. The logic under test is the completeness
    filter, and routing is already covered by tests/test_route_smoke.py.
    """
    from main import clear_all_caches, get_fiscal_summary

    clear_all_caches()
    return asyncio.run(get_fiscal_summary(db=db_session))

ENACTED_SOURCE = {
    "title": "Programme Based Budget FY 2026/27 (Approved)",
    "publisher": "The National Treasury",
    "url": (
        "https://www.treasury.go.ke/sites/default/files/Budget%20Books/"
        "Budget%20books%202026-2027/FY%202026%202027%20Programme%20Based%20"
        "Budget%20Book_Approved.pdf"
    ),
    "page": "voted total PDF p.11; CFS summary PDF p.1193",
}


@pytest.fixture()
def seed_years(db_session, seed_country, seed_source_doc):
    """A complete prior year, a newly-enacted year, and a World Bank stub."""
    complete = FiscalSummary(
        fiscal_year="FY 2025/26",
        appropriated_budget=4690e9,
        total_revenue=2910e9,
        tax_revenue=2560e9,
        non_tax_revenue=350e9,
        total_borrowing=910e9,
        debt_service_cost=1900e9,
        development_spending=672e9,
        recurrent_spending=2850e9,
        county_allocation=415e9,
        unit="KES",
        source_document_id=seed_source_doc.id,
        meta={"budget_basis": "cob_gross", "budget_basis_source": ENACTED_SOURCE},
        page_ref="PDF p.23",
    )
    enacted = FiscalSummary(
        fiscal_year="FY 2026/27",
        appropriated_budget=5485.7e9,
        # Nothing else exists yet: the year is two months old.
        unit="KES",
        source_document_id=seed_source_doc.id,
        meta={"budget_basis": "cob_gross", "budget_basis_source": ENACTED_SOURCE},
        page_ref="voted total PDF p.11; CFS summary PDF p.1193",
    )
    stub = FiscalSummary(
        fiscal_year="FY 2027/28",
        appropriated_budget=6000e9,
        unit="KES",
        source_document_id=seed_source_doc.id,
        meta={"_source": "world_bank_api"},
    )
    db_session.add_all([complete, enacted, stub])
    db_session.commit()
    return {"complete": complete, "enacted": enacted, "stub": stub}


class TestEnactedBudgetYearIsPublished:
    def test_the_newly_enacted_year_is_the_current_one(self, db_session, seed_years):
        body = fiscal_summary(db_session)
        assert body["current"]["fiscal_year"] == "FY 2026/27"
        assert body["current"]["appropriated_budget"] == pytest.approx(5485.7e9)

    def test_the_published_figure_carries_its_basis_and_page(self, db_session, seed_years):
        """No number without provenance — including the provenance of its
        DEFINITION. 4.19T (Budget Policy Statement) and 4.69T (COB gross) are
        both 'the budget' for FY2025/26."""
        current = fiscal_summary(db_session)["current"]
        assert current["budget_basis"] == "cob_gross"
        assert current["budget_basis_source"]["url"].startswith("https://")
        assert "p.11" in current["page_ref"]

    def test_a_world_bank_stub_is_still_excluded(self, db_session, seed_years):
        """POSITIVE CONTROL for the exception. FY 2027/28 has exactly as many
        populated fields as the enacted year and no provenance, so it must
        stay out — otherwise the exception has simply deleted the filter."""
        body = fiscal_summary(db_session)
        labels = [fy["fiscal_year"] for fy in body["history"]]
        assert "FY 2027/28" not in labels
        assert "FY 2026/27" in labels
        assert body["current"]["fiscal_year"] != "FY 2027/28"

    def test_a_complete_prior_year_is_unaffected(self, db_session, seed_years):
        labels = [
            fy["fiscal_year"] for fy in fiscal_summary(db_session)["history"]
        ]
        assert "FY 2025/26" in labels


class TestExceptionRequiresFullProvenance:
    @pytest.mark.parametrize(
        "meta,page_ref",
        [
            ({"budget_basis": "cob_gross"}, "p.11"),          # no source url
            ({"budget_basis_source": ENACTED_SOURCE}, "p.11"),  # no basis
            ({"budget_basis": "cob_gross", "budget_basis_source": ENACTED_SOURCE}, None),  # no page
        ],
    )
    def test_partial_provenance_does_not_qualify(
        self, db_session, seed_source_doc, meta, page_ref
    ):
        """Each leg of the provenance test must be load-bearing; drop any one
        and the row falls back to the ordinary completeness rule."""
        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2026/27",
                appropriated_budget=5485.7e9,
                unit="KES",
                source_document_id=seed_source_doc.id,
                meta=meta,
                page_ref=page_ref,
            )
        )
        db_session.commit()
        labels = [
            fy["fiscal_year"] for fy in fiscal_summary(db_session)["history"]
        ]
        assert "FY 2026/27" not in labels


# ── The chain from fixture to API ─────────────────────────────────────
class TestBasisSurvivesTheWrite:
    """The API's exception reads ``metadata.budget_basis`` and ``page_ref``.
    Those only exist because the writer puts them there — so the link is
    tested, not assumed."""

    def test_writer_persists_the_basis_and_page(
        self, db_session, seed_country, seed_source_doc
    ):
        from seeding.domains.fiscal_summary.parser import (
            parse_fiscal_summary_payload,
        )
        from seeding.domains.fiscal_summary.writer import (
            write_fiscal_summary_records,
        )

        payload = {
            "fiscal_years": [
                {
                    "fiscal_year": "FY 2026/27",
                    "appropriated_budget": 5485.7,
                    "budget_basis": "cob_gross",
                    "budget_basis_source": dict(ENACTED_SOURCE),
                }
            ]
        }
        records = parse_fiscal_summary_payload(payload)
        assert records[0].budget_basis == "cob_gross"

        write_fiscal_summary_records(db_session, records, {})
        db_session.commit()

        row = (
            db_session.query(FiscalSummary)
            .filter(FiscalSummary.fiscal_year == "FY 2026/27")
            .one()
        )
        assert row.meta["budget_basis"] == "cob_gross"
        assert row.meta["budget_basis_source"]["url"].startswith("https://")
        assert row.page_ref == ENACTED_SOURCE["page"][:50]
        # ...and the money column is raw KES, not billions.
        assert float(row.appropriated_budget) == pytest.approx(5485.7e9)

    def test_a_row_without_a_basis_writes_no_basis_metadata(
        self, db_session, seed_country, seed_source_doc
    ):
        """POSITIVE CONTROL: the writer must not invent a basis, or every
        row would qualify for the API exception."""
        from seeding.domains.fiscal_summary.parser import (
            parse_fiscal_summary_payload,
        )
        from seeding.domains.fiscal_summary.writer import (
            write_fiscal_summary_records,
        )

        records = parse_fiscal_summary_payload(
            {"fiscal_years": [{"fiscal_year": "FY 2019/20", "appropriated_budget": 2800}]}
        )
        write_fiscal_summary_records(db_session, records, {})
        db_session.commit()
        row = (
            db_session.query(FiscalSummary)
            .filter(FiscalSummary.fiscal_year == "FY 2019/20")
            .one()
        )
        assert not (row.meta or {}).get("budget_basis")
        assert row.page_ref is None


class TestNextYearsBudgetSummaryDoesNotTakeOverCurrent:
    """Consolidation review of #256 + #260 (should-fix).

    Treasury's Budget Summary for NEXT year appears in June, before the next
    budget book is read. The fiscal_summary fetcher then writes a row with
    revenue, borrowing and county transfers (the framework split) and a page
    reference, but no appropriated budget and no debt service. It passes the
    three-of-four rule and was published — and as the last published year it
    became ``current``, so the homepage's budget and debt-service cards and the
    /debt loans card went blank until the budget book landed.
    """

    @pytest.fixture()
    def next_year_summary_only(self, db_session, seed_years, seed_source_doc):
        row = FiscalSummary(
            fiscal_year="FY 2027/28",
            total_revenue=3200e9,
            total_borrowing=1000e9,
            county_allocation=520e9,
            unit="KES",
            source_document_id=seed_source_doc.id,
            page_ref="Annex Table 2a, PDF p.63",
            meta={"split_basis": "treasury_fiscal_framework"},
        )
        # the World Bank stub from seed_years would otherwise share the year
        db_session.delete(seed_years["stub"])
        db_session.commit()
        db_session.add(row)
        db_session.commit()
        return row

    def test_current_stays_the_year_with_an_enacted_budget(self, db_session, next_year_summary_only):
        body = fiscal_summary(db_session)
        assert body["current"]["fiscal_year"] == "FY 2026/27", body["current"]
        assert body["current"]["appropriated_budget"]

    def test_debt_loans_reads_the_same_current_year(self, db_session, next_year_summary_only):
        from main import _published_annual_debt_service

        annual = _published_annual_debt_service(db_session)
        # Whatever it publishes, it is about the year /fiscal/summary calls
        # current, never next year's budget-summary-only row.
        assert "FY 2027/28" not in str(annual), annual
