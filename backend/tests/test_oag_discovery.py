"""OAG county audit discovery: listing -> year pages -> volumes, plus sitemap.

Every fixture string here is a shape observed on www.oagkenya.go.ke on
2026-09-26. Discovery used to be the WordPress media API, which counted 783
county PDFs and returned 154, the newest from 2023-11. The nightly logged
"5 known + 0 newly discovered" while OAG had published four more years.
"""

from __future__ import annotations

import pytest

from seeding import oag_discovery as od

LISTING_HTML = """
<a href="/2016-2017-county-government-audit-reports">2016/17</a>
<a href="/2018-2019-county-government-audit-reports/">2018/19</a>
<a href="/2020-2021-county-government-audit-reports">2020/21</a>
<a href="/2021-2022-county-government-audit-reports">2021/22</a>
<a href="/2023-2024-county-government-audit-reports">2023/24</a>
<a href="/2024-2025-county-government-audit-reports">2024/25</a>
<a href="/2024-2025-county-government-audit-reports/">again, with a slash</a>
<a href="https://www.oagkenya.go.ke/national-government-audit-reports/">national</a>
"""

FY2324 = od.YearPage(
    "2023/2024",
    "https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/",
)
FY2324_HTML = """
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-ASSEMBLIES-2024-FINAL-01-April-2025-KLB.pdf">A</a>
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf">E</a>
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2025/04/Auditor-Generals-summary-Report-on-County-Governments-2023-2024.pdf">S</a>
"""

FY2122 = od.YearPage(
    "2021/2022",
    "https://www.oagkenya.go.ke/2021-2022-county-government-audit-reports/",
)
FY2122_HTML = """
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2023/07/AUDITOR-GENERAL-S-REPORT-ON-THE-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2021-2022-VOLUME-1.pdf">1</a>
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2023/07/AUDITOR-GENERAL-S-REPORT-ON-THE-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLES-2021-2022-VOLUME-2.pdf">2</a>
<a href="/wp-content/uploads/2023/10/County-Executive-of-Garissa-2021-2022-.pdf#new_tab">Garissa</a>
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2023/10/County-Executive-of-Garissa-2021-2022-.pdf">Garissa again</a>
<a href="https://www.oagkenya.go.ke/wp-content/uploads/2023/11/County-Assemby-of-Garissa-2021-2022.pdf">misspelt</a>
"""


class TestListing:
    def test_every_year_page_is_found_oldest_first_and_once(self):
        pages = od.parse_listing(LISTING_HTML)
        assert [p.fiscal_year for p in pages] == [
            "2016/2017",
            "2018/2019",
            "2020/2021",
            "2021/2022",
            "2023/2024",
            "2024/2025",
        ]
        assert all(p.url.endswith("/") for p in pages)

    def test_a_non_county_link_is_not_a_year_page(self):
        assert not any(
            "national" in p.url for p in od.parse_listing(LISTING_HTML)
        )


class TestYearPage:
    def test_a_volume_with_no_year_in_its_name_takes_the_pages_year(self):
        """GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf is FY2023/24.
        Its name has no fiscal-year span. OAG files it on the 2023-2024 page."""
        docs, conflicts = od.parse_year_page(FY2324_HTML, FY2324)
        by_kind = {d.kind: d for d in docs}
        assert conflicts == []
        assert by_kind["executives"].fiscal_year == "2023/2024"
        assert by_kind["executives"].filename.startswith("GREEN-BOOK-EXECUTIVES")
        assert by_kind["assemblies"].fiscal_year == "2023/2024"
        assert by_kind["summary"].fiscal_year == "2023/2024"

    def test_one_pdf_linked_twice_is_one_document(self):
        """The FY2021/22 page links Garissa's executive report relatively
        with #new_tab and absolutely. 96 hrefs, 95 documents."""
        docs, _ = od.parse_year_page(FY2122_HTML, FY2122)
        garissa = [d for d in docs if "Executive-of-Garissa" in d.url]
        assert len(garissa) == 1
        assert garissa[0].url == (
            "https://www.oagkenya.go.ke/wp-content/uploads/2023/10/"
            "County-Executive-of-Garissa-2021-2022-.pdf"
        )

    def test_a_filename_contradicting_its_page_is_not_filed_under_either(self):
        page_html = (
            '<a href="/wp-content/uploads/2024/04/'
            'GREEN-BOOK-COUNTY-EXECUTIVES-VOL-1-2022-2023-1.pdf">x</a>'
        )
        docs, conflicts = od.parse_year_page(page_html, FY2324)
        assert docs[0].fiscal_year is None
        assert "2022/2023" in docs[0].note and "2023/2024" in docs[0].note
        assert len(conflicts) == 1


class TestClassify:
    @pytest.mark.parametrize(
        "name, kind",
        [
            ("AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf", "executives"),
            ("AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf", "assemblies"),
            ("AUDITOR-GENERALS-SUMMARY-REPORT-ON-COUNTY-GOVERNMENTS-2024-2025.pdf", "summary"),
            ("GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf", "executives"),
            ("GREEN-BOOK-COUNTY-ASSEMBLIES-VOL.-2-2022-2023.pdf", "assemblies"),
            # OAG's own spelling, FY2021/22 volume 2.
            ("AUDITOR-GENERAL-S-REPORT-ON-THE-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLES-2021-2022-VOLUME-2.pdf", "assemblies"),
            ("REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-I-COUNTY-EXECUTIVES-1.pdf", "executives"),
            ("County-Executive-of-Garissa-2021-2022-.pdf", "single_entity"),
            ("COUNTY-ASSEMBLY-OF-ISIOLO-2020-2021.pdf", "single_entity"),
            # OAG's misspelling. It was classified "other" and not registered.
            ("County-Assemby-of-Garissa-2021-2022.pdf", "single_entity"),
            # A municipality's report that names its county mid-title.
            ("Elwak-Municipality-–-County-Government-of-Mandera-2021-2022.pdf", "other"),
            ("Muhu-Secondary-School-2021-2022-Kiambu-County.pdf", "other"),
        ],
    )
    def test_kinds(self, name, kind):
        assert od.classify_document(f"https://x/{name}")[0] == kind

    def test_the_single_entity_names_its_county(self):
        kind, entity = od.classify_document("https://x/County-Assembly-of-Homa-Bay-2021-2022.pdf")
        assert (kind, entity) == ("single_entity", "Homa Bay")


class TestUrlsAndYears:
    def test_the_malformed_sitemap_entry_is_skipped_not_raised(self):
        """Real entry in wp-sitemap-posts-dlp_document-1.xml. urlsplit raised
        'Invalid IPv6 URL' and aborted the whole sitemap pass."""
        assert (
            od.normalise_oag_url(
                "http://]/wp-content/uploads/2022/02/Muranga-University-of-Technology-2019-2020.pdf#new_tab"
            )
            is None
        )

    @pytest.mark.parametrize(
        "href",
        [
            "/wp-content/uploads/2026/05/X-2024-2025-1.pdf#new_tab",
            "http://new01.oagkenya.go.ke/wp-content/uploads/2026/05/X-2024-2025-1.pdf",
            "https://oagkenya.go.ke/wp-content/uploads/2026/05/X-2024-2025-1.pdf",
        ],
    )
    def test_one_document_three_spellings(self, href):
        assert od.normalise_oag_url(href) == (
            "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/X-2024-2025-1.pdf"
        )

    def test_an_off_site_link_is_not_an_oag_document(self):
        assert od.normalise_oag_url("https://example.com/a.pdf") is None

    @pytest.mark.parametrize(
        "name, fy",
        [
            ("X-2024-2025-1.pdf", "2024/2025"),
            ("GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf", None),
            ("Plan-2019-2023.pdf", None),  # not consecutive: not a fiscal year
            ("Both-2021-2022-and-2022-2023.pdf", None),  # ambiguous
        ],
    )
    def test_fiscal_year_in_name(self, name, fy):
        assert od.fiscal_year_in_name(name) == fy


class TestSitemap:
    def test_schools_are_counted_not_registered_and_unplaced_are_counted(self):
        locs = [
            "/wp-content/uploads/2024/06/Muhoho-High-School-Kiambu-County.pdf",
            "/wp-content/uploads/2023/11/County-Assembly-of-Kitui-2021-2022.pdf#new_tab",
            "/wp-content/uploads/2025/02/GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf",
            "http://]/wp-content/uploads/2022/02/Muranga-University-of-Technology-2019-2020.pdf",
        ]
        docs, unplaced, other = od.documents_from_sitemap(locs, "sm")
        assert [d.kind for d in docs] == ["single_entity", "executives"]
        assert docs[0].fiscal_year == "2021/2022"
        assert docs[1].fiscal_year is None
        assert (unplaced, other) == (1, 1)

    def test_the_year_page_places_what_the_sitemap_cannot(self):
        page_docs, _ = od.parse_year_page(FY2324_HTML, FY2324)
        sm_docs, _, _ = od.documents_from_sitemap(
            ["/wp-content/uploads/2025/02/GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf"],
            "sm",
        )
        merged = {d.url: d for d in od.merge(page_docs, sm_docs)}
        exe = merged[
            "https://www.oagkenya.go.ke/wp-content/uploads/2025/02/"
            "GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf"
        ]
        assert (exe.fiscal_year, exe.found_on) == ("2023/2024", "year_page")


class _Resp:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """Serves a URL->text map. A missing URL raises, like a 404 would."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, raise_for_status=True):
        self.calls.append(url)
        if url not in self.pages:
            raise RuntimeError(f"404 {url}")
        body = self.pages[url]
        if isinstance(body, Exception):
            raise body
        return _Resp(body)


def _site(**overrides):
    base = {
        od.LISTING_URL: LISTING_HTML,
        "https://www.oagkenya.go.ke/2021-2022-county-government-audit-reports/": FY2122_HTML,
        "https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/": FY2324_HTML,
        "https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/": (
            '<a href="/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-'
            'GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf">A</a>'
            '<a href="/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-'
            'GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf">E</a>'
        ),
        od.SITEMAP_INDEX_URL: (
            "<sitemapindex><sitemap><loc>https://www.oagkenya.go.ke/"
            "wp-sitemap-posts-dlp_document-1.xml</loc></sitemap></sitemapindex>"
        ),
        "https://www.oagkenya.go.ke/wp-sitemap-posts-dlp_document-1.xml": (
            "<urlset>"
            "<url><loc>http://]/wp-content/uploads/2022/02/Bad-2019-2020.pdf</loc></url>"
            "<url><loc>/wp-content/uploads/2023/11/County-Assembly-of-Kitui-2021-2022.pdf#new_tab</loc></url>"
            "<url><loc>/wp-content/uploads/2021/09/County-Assembly-of-Kisumu-2018-2019.pdf</loc></url>"
            "</urlset>"
        ),
    }
    base.update(overrides)
    return base


class TestDiscoverPass:
    def test_the_whole_pass(self):
        result = od.discover_county_audit_documents(FakeClient(_site()))
        assert result.errors == []
        # The full listing is reported, including years before the floor.
        assert result.listing_fiscal_years[0] == "2016/2017"
        assert result.listing_fiscal_years[-1] == "2024/2025"
        # Newest fiscal year first, executives before assemblies.
        assert [(v.fiscal_year, v.kind) for v in result.volumes()] == [
            ("2024/2025", "executives"),
            ("2024/2025", "assemblies"),
            ("2023/2024", "executives"),
            ("2023/2024", "assemblies"),
            ("2021/2022", "executives"),
            ("2021/2022", "assemblies"),
        ]
        urls = {d.url for d in result.documents}
        # The sitemap adds what the year pages lack (Kitui), one bad entry does
        # not abort it, and pre-floor documents (Kisumu 2018/19) are not
        # returned.
        assert any("Assembly-of-Kitui-2021-2022" in u for u in urls)
        assert not any("2018-2019" in u for u in urls)

    def test_pre_floor_year_pages_are_not_fetched(self):
        client = FakeClient(_site())
        od.discover_county_audit_documents(client)
        assert not any("2016-2017" in c or "2020-2021" in c for c in client.calls)

    def test_an_unreachable_listing_is_an_error_not_an_empty_year_list(self):
        site = _site()
        del site[od.LISTING_URL]
        result = od.discover_county_audit_documents(FakeClient(site))
        assert result.listing_fiscal_years == []
        assert any("listing unreachable" in e for e in result.errors)

    def test_a_challenge_page_served_as_200_is_an_error(self):
        """OAG has answered GitHub runners with HTTP 200 and an HTML page."""
        site = _site(**{od.LISTING_URL: "<html><title>Just a moment...</title></html>"})
        result = od.discover_county_audit_documents(FakeClient(site))
        assert result.listing_fiscal_years == []
        assert any("linked no" in e for e in result.errors)

    def test_a_year_page_with_no_pdf_is_an_error(self):
        site = _site(
            **{"https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/": "<html></html>"}
        )
        result = od.discover_county_audit_documents(FakeClient(site))
        assert any("2023/2024 linked no PDF" in e for e in result.errors)

    def test_as_meta_is_what_the_gate_reads(self):
        meta = od.discover_county_audit_documents(FakeClient(_site())).as_meta()
        assert meta["listing_fiscal_years"][-1] == "2024/2025"
        assert set(meta["volumes_by_fiscal_year"]) == {"2021/2022", "2023/2024", "2024/2025"}
