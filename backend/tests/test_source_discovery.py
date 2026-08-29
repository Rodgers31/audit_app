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
