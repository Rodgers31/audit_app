"""Discovery of the CURRENT edition of a republished document.

Overlays were wired to hardcoded deep links that rot on each release:
``treasury_brop_url`` pinned a 2025 path, while the CBK bulletin and KRA
URLs were never set at all — so those overlays had simply never run.
Discovery reads the publisher's listing page each run instead.

Filenames below are REAL, scraped from CBK and Treasury on 2026-08-29.
"""

from __future__ import annotations

from datetime import date

import pytest
from seeding.discovery import (
    discover_latest_pdf,
    find_pdf_links,
    parse_document_date,
    parse_fiscal_year,
)

CBK_PAGE = """
<a href="/uploads/statistical_bulletin/1031256347_December 2003.pdf">2003</a>
<a href="/uploads/statistical_bulletin/10533542_June 2023 .pdf">2023</a>
<a href="/uploads/statistical_bulletin/1052162370_Statistical Bulletin Dec 2019 Revised.pdf">2019</a>
<a href="/uploads/statistical_bulletin/107371226_Statistical Bulletin - December 2025.pdf">2025</a>
<a href="/uploads/other/some-unrelated-report.pdf">noise</a>
"""

BROP_PAGE = """
<a href="/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf">2025</a>
<a href="/sites/default/files/BBB/2024-Budget-Review-and-Outlook-Paper.pdf">2024</a>
<a href="/sites/default/files/BBB/2021-Budget-Review-and-Outlook-Paper.pdf">2021</a>
<a href="/sites/default/files/BBB/BOP-Jan-2009-10-to-2011-12.pdf">old</a>
"""


class TestDateParsing:
    @pytest.mark.parametrize("name,expected", [
        ("107371226_Statistical Bulletin - December 2025.pdf", date(2025, 12, 1)),
        ("1052162370_Statistical Bulletin Dec 2019 Revised.pdf", date(2019, 12, 1)),
        ("10533542_June 2023 .pdf", date(2023, 6, 1)),
        ("2025-Budget-Review-and-Outlook-Paper-1.pdf", date(2025, 1, 1)),
    ])
    def test_real_filenames(self, name, expected):
        assert parse_document_date(name)[0] == expected

    def test_upload_hash_digits_are_not_read_as_a_year(self):
        """CBK prefixes every file with a 10-digit upload hash. A naive
        \\d{4} matches '1031' inside it and dates the document to 1031."""
        parsed, _ = parse_document_date("1031256347_December 2003.pdf")
        assert parsed == date(2003, 12, 1)

    def test_undated_returns_none(self):
        assert parse_document_date("annual-report.pdf") == (None, "none")

    def test_empty_input(self):
        assert parse_document_date("") == (None, "none")


# Real hrefs from https://www.treasury.go.ke/budget-books/ on 2026-08-29.
# Note the directory spellings Treasury actually uses in ONE tree: "Budget
# Books 2025-2026", "Budget books 2026-2027" (lowercase b), "Budget Books
# 2024 - 2025", "Budget Estimates 2020 -2021".
BUDGET_BOOKS_PAGE = """
<a href="/sites/default/files/Budget%20Books/Budget%20Books%202024%20-%202025/FY-2024-25-Program-Based-Budget-Book.pdf">a</a>
<a href="/sites/default/files/Budget%20Books/Budget%20Books%202025-2026/Budget%20Estimates/Programme-Based-Budget.pdf">b</a>
<a href="/sites/default/files/Budget%20Books/Budget%20Books%202025-2026/Supplementary-1/FY-2025-26%20PBB%20Supplementary%20I%201011-2151.pdf">c</a>
<a href="/sites/default/files/Budget%20Books/Budget%20books%202026-2027/Development%20Volume%20III%20(1092-1135)_Approved.pdf">d</a>
<a href="/sites/default/files/Budget%20Books/Budget%20books%202026-2027/FY%202026%202027%20Programme%20Based%20Budget%20Book_Approved.pdf">e</a>
<a href="/sites/default/files/Budget%20Books/Budget%20Estimates%202020%20-2021/FY2020-21-Programme-Based-Budget.pdf">f</a>
"""


class TestFiscalYearInThePath:
    """Treasury dates budget books by DIRECTORY, not filename.

    ``parse_document_date`` was written for filenames, and every FY2026/27
    budget book is called something like "Development Volume I (1011-1083)_
    Approved.pdf" — no date at all. Without a fiscal-year strategy the newest
    budget in the country is undiscoverable.
    """

    @pytest.mark.parametrize("path,expected", [
        ("Budget%20Books%202025-2026/Budget%20Estimates/Programme-Based-Budget.pdf", "FY 2025/26"),
        ("Budget%20books%202026-2027/Development%20Volume%20III%20(1092-1135)_Approved.pdf", "FY 2026/27"),
        ("Budget%20Books%202024%20-%202025/FY-2024-25-Program-Based-Budget-Book.pdf", "FY 2024/25"),
        ("Budget%20Estimates%202020%20-2021/FY2020-21-Programme-Based-Budget.pdf", "FY 2020/21"),
        ("FY%202026%202027%20Programme%20Based%20Budget%20Book_Approved.pdf", "FY 2026/27"),
        ("Estimates-of-RevenueGrants-and-Loans-for-FY2022-23.pdf", "FY 2022/23"),
    ])
    def test_real_treasury_paths(self, path, expected):
        assert parse_fiscal_year(path) == expected

    @pytest.mark.parametrize("path", [
        # Vote-code ranges are everywhere in these filenames and are NOT
        # fiscal years. The consecutive-years rule is what separates them.
        "FY-2024-25-Development-Budget-Book-1092-2141.pdf",
        "Development%20Volume%20IV%20(1152-2111)_Approved.pdf",
        "FY-2025-26%20Recurrent%20Supplementary%20(1011-2151).pdf",
    ])
    def test_vote_code_ranges_are_not_fiscal_years(self, path):
        parsed = parse_fiscal_year(path)
        assert parsed in (None, "FY 2024/25", "FY 2025/26"), parsed
        # ...and never a year invented from a vote code.
        assert parsed not in ("FY 1092/93", "FY 1152/53", "FY 1011/12")

    def test_a_calendar_document_is_still_dated_by_year(self):
        """Regression guard: adding the fiscal-year strategy must not
        re-date the BROP, whose filename is a calendar year."""
        assert parse_fiscal_year("2025-Budget-Review-and-Outlook-Paper-1.pdf") is None
        assert parse_document_date(
            "2025-Budget-Review-and-Outlook-Paper-1.pdf"
        ) == (date(2025, 1, 1), "year")

    def test_fiscal_year_sorts_above_a_bare_year_of_the_same_start(self):
        """FY2026/27 is dated 1 July 2026 — after a "2026" calendar doc, so
        the enacted budget wins over a January-dated paper from the same
        year."""
        assert parse_document_date("Budget books 2026-2027/x.pdf") == (
            date(2026, 7, 1), "fiscal_year",
        )


class TestBudgetBookDiscovery:
    def test_picks_the_newest_fiscal_years_approved_estimates(self):
        found = discover_latest_pdf(
            BUDGET_BOOKS_PAGE,
            "https://www.treasury.go.ke/budget-books/",
            must_match=("/budget%20books/", "programme"),
            must_not_match=("supplementary", "supp-", "draft"),
        )
        assert found is not None
        assert parse_fiscal_year(found.url) == "FY 2026/27"
        assert found.url.endswith(
            "FY%202026%202027%20Programme%20Based%20Budget%20Book_Approved.pdf"
        )

    def test_supplementary_estimates_are_excluded(self):
        """A supplementary revises a budget mid-year. It is a DIFFERENT
        measure from the original gross budget COB reports on, so it must
        never be picked up as 'the newest budget'."""
        found = discover_latest_pdf(
            BUDGET_BOOKS_PAGE,
            "https://www.treasury.go.ke/budget-books/",
            must_match=("/budget%20books/", "programme"),
            must_not_match=("supplementary", "supp-", "draft"),
        )
        assert "Supplementary" not in found.url

    def test_a_listing_that_lost_its_recent_years_fails_loudly(self):
        """POSITIVE CONTROL: with a floor set, an old-only listing must
        return None rather than seeding FY2020/21 as 'current'."""
        old_only = (
            '<a href="/sites/default/files/Budget%20Books/Budget%20Estimates'
            '%202020%20-2021/FY2020-21-Programme-Based-Budget.pdf">f</a>'
        )
        assert discover_latest_pdf(
            old_only,
            "https://www.treasury.go.ke/budget-books/",
            must_match=("/budget%20books/", "programme"),
            not_before=date(2025, 1, 1),
        ) is None


class TestDiscovery:
    def test_picks_newest_cbk_bulletin_not_page_order(self):
        """The listing is NOT sorted — 2003 appears before 2025."""
        found = discover_latest_pdf(
            CBK_PAGE, "https://www.centralbank.go.ke/releases/statistical-bulletin/",
            must_match=("/uploads/statistical_bulletin/",),
        )
        assert found.published == date(2025, 12, 1)
        assert "December 2025" in found.url

    def test_series_filter_excludes_unrelated_pdfs(self):
        found = discover_latest_pdf(
            CBK_PAGE, "https://www.centralbank.go.ke/",
            must_match=("/uploads/statistical_bulletin/",),
        )
        assert "some-unrelated-report" not in found.url

    def test_picks_newest_brop(self):
        found = discover_latest_pdf(
            BROP_PAGE, "https://www.treasury.go.ke/budget-review-and-outlook-paper/",
            must_match=("budget-review-and-outlook-paper",),
        )
        assert found.published == date(2025, 1, 1)
        assert found.url.endswith("2025-Budget-Review-and-Outlook-Paper-1.pdf")

    def test_stale_listing_fails_loudly_rather_than_seeding_old_data(self):
        """POSITIVE CONTROL: if the newest edition is older than the floor,
        discovery must FAIL rather than quietly seed a 2003 bulletin."""
        old_only = '<a href="/uploads/statistical_bulletin/1_December 2003.pdf">x</a>'
        found = discover_latest_pdf(
            old_only, "https://www.centralbank.go.ke/",
            must_match=("/uploads/statistical_bulletin/",),
            not_before=date(2024, 1, 1),
        )
        assert found is None

    def test_no_match_returns_none(self):
        assert discover_latest_pdf(
            CBK_PAGE, "https://x/", must_match=("nothing-matches-this",)
        ) is None

    def test_undated_candidates_are_not_guessed_between(self):
        html = '<a href="/x/report.pdf">a</a><a href="/x/other.pdf">b</a>'
        assert discover_latest_pdf(html, "https://x/", must_match=("/x/",)) is None

    def test_relative_hrefs_become_absolute(self):
        links = find_pdf_links('<a href="/a/b.pdf">x</a>', "https://h.go.ke/page/")
        assert links[0][0] == "https://h.go.ke/a/b.pdf"


class TestCbkPublicDebtTable:
    """Table 4.1.3 — the live source for the debt_timeline series."""

    # Real rows from the December 2025 bulletin, page 56.
    PAGE = """Table 4.1.3: Deficit Financing and Public Debt Shillings million
Fiscal Year* Domestic External
2024/2025
December 411,238.7 0.0 -6,642.9 404,595.7 5,868,273.2 5,057,005.8 10,925,278.9
June 854,474.3 0.0 179,738.5 1,034,212.8 6,325,454.3 5,484,829.7 11,810,283.9
2025/2026****
July 81,022.0 0.0 -45,643.9 35,378.0 6,386,243.3 5,385,289.2 11,771,532.5
December 509,230.3 0.0 7,776.6 517,006.9 6,837,510.7 5,461,965.7 12,299,476.4
"""

    def test_parses_latest_month_per_calendar_year_in_raw_kes(self):
        from seeding.domains.national_debt.cbk_bulletin import (
            parse_public_debt_table,
        )

        parsed = parse_public_debt_table(self.PAGE)
        # FY2025/2026 July-December -> calendar 2025.
        assert parsed[2025]["total"] == 12_299_476_400_000
        assert parsed[2025]["domestic"] == 6_837_510_700_000
        assert parsed[2025]["external"] == 5_461_965_700_000
        # Shillings million -> raw KES, i.e. 12.299T not 12.3M.
        assert float(parsed[2025]["total"]) / 1e12 == pytest.approx(12.2994764)

    def test_fiscal_year_months_map_to_the_right_calendar_year(self):
        from seeding.domains.national_debt.cbk_bulletin import (
            parse_public_debt_table,
        )

        parsed = parse_public_debt_table(self.PAGE)
        # June of FY2024/2025 is calendar 2025; December of FY2024/2025 is 2024.
        assert 2024 in parsed and parsed[2024]["total"] == 10_925_278_900_000

    def test_row_failing_the_component_identity_is_dropped(self):
        """domestic + external must equal total. A row that fails was
        mis-parsed and must never become a published figure."""
        from seeding.domains.national_debt.cbk_bulletin import (
            parse_public_debt_table,
        )

        bad = """Table 4.1.3: Deficit Financing and Public Debt
2025/2026
December 1.0 0.0 1.0 1.0 1,000.0 1,000.0 9,999,999.0
"""
        assert parse_public_debt_table(bad) == {}


class TestDraftDocumentsAreNotPublishable:
    """A DRAFT may not back a published figure. Decided 2026-08-29.

    Real hrefs from https://www.treasury.go.ke/budget-review-and-outlook-paper/
    on 2026-08-29: Treasury lists drafts beside finals. A "Draft 2026 Budget
    Review and Outlook Paper" is live on the Treasury home page right now,
    next to a "Public Notice on the Draft 2026 Budget Review and Outlook
    Paper" inviting comment — i.e. its figures are explicitly provisional.
    """

    PAGE = """
    <a href="/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf">final 2025</a>
    <a href="/sites/default/files/BBB/2024-Budget-Review-and-Outlook-Paper.pdf">final 2024</a>
    <a href="/sites/default/files/BBB/Draft-2026-Budget-Review-and-Outlook-Paper.pdf">draft 2026</a>
    """

    def test_a_newer_draft_does_not_displace_an_older_final(self):
        found = discover_latest_pdf(
            self.PAGE,
            "https://www.treasury.go.ke/budget-review-and-outlook-paper/",
            must_match=("budget-review-and-outlook-paper",),
            must_not_match=("draft",),
        )
        assert found.url.endswith("2025-Budget-Review-and-Outlook-Paper-1.pdf")

    def test_positive_control_without_the_filter_the_draft_wins(self):
        """Shows the filter is load-bearing, not decoration: discovery ranks
        by date, so a 2026 draft outranks the 2025 final."""
        found = discover_latest_pdf(
            self.PAGE,
            "https://www.treasury.go.ke/budget-review-and-outlook-paper/",
            must_match=("budget-review-and-outlook-paper",),
        )
        assert "Draft-2026" in found.url

    def test_the_pending_bills_discovery_applies_the_filter(self):
        """`grep-verify-before-listing`: assert the call site, not the
        capability."""
        import inspect

        from seeding.domains.pending_bills import fetcher

        source = inspect.getsource(fetcher._discover_brop_url)
        assert 'must_not_match=("draft",)' in source
