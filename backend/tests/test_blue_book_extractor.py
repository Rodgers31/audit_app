"""Layer-3 Blue Book extractor: grammar, integrity gate, mis-attribution guard.

Every guard here has a test that makes it FIRE (rule: a check that cannot
fail is not a check): the cid gate rejects glyph-junk, the paragraph-
continuity rule rejects numbered list items inside a finding body, and a
TOC/header mismatch skips a chapter instead of mis-attributing findings.
"""

from __future__ import annotations

from seeding.extractors.oag_blue_book import (
    BlueBookResult,
    PageText,
    cid_ratio,
    fiscal_year_from_url,
    find_offset,
    parse_blue_book,
    parse_toc,
    segment_chapter,
    severity_for,
    source_hash_of,
)

CID_JUNK = "(cid:31)(cid:30)(cid:29)(cid:28)(cid:27)(cid:26)(cid:25)"


class TestCidRatio:
    def test_clean_text_is_zero(self):
        assert cid_ratio("Pending Accounts Payable of Kshs.20,811,926,257") == 0.0

    def test_glyph_junk_is_high(self):
        assert cid_ratio(CID_JUNK) > 0.9

    def test_mixed_below_threshold_passes(self):
        text = "A real finding about pending bills. " * 20 + "(cid:31)"
        assert cid_ratio(text) < 0.20

    def test_empty_is_zero(self):
        assert cid_ratio("") == 0.0


class TestSeverityMapping:
    def test_basis_for_adverse_is_critical(self):
        assert severity_for("Basis for Adverse Opinion", None) == "CRITICAL"

    def test_disclaimer_opinion_is_critical(self):
        assert severity_for(None, "Disclaimer of Opinion") == "CRITICAL"

    def test_basis_for_qualified_is_warning(self):
        assert severity_for("Basis for Qualified Opinion", "Qualified Opinion") == "WARNING"

    def test_basis_for_conclusion_is_warning(self):
        assert severity_for("Basis for Conclusion", None) == "WARNING"

    def test_emphasis_of_matter_is_info(self):
        assert severity_for("Emphasis of Matter", "Unmodified Opinion") == "INFO"

    def test_no_context_is_info(self):
        assert severity_for(None, None) == "INFO"


class TestFiscalYearFromUrl:
    def test_national_report_filename(self):
        url = "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
        assert fiscal_year_from_url(url) == "2024/2025"

    def test_upload_date_path_not_mistaken_for_fy(self):
        # /uploads/2026/05/ is a publish date, not a fiscal year.
        url = "https://x.go.ke/wp-content/uploads/2026/05/SOME-REPORT.pdf"
        assert fiscal_year_from_url(url) is None

    def test_non_consecutive_span_rejected(self):
        assert fiscal_year_from_url("plan-2019-2023.pdf") is None


def _page(n: int, text: str, method: str = "pdfplumber") -> PageText:
    return PageText(page_number=n, text=text, method=method)


TOC_PAGE = _page(
    1,
    "Table of Contents\n"
    "Vote Page\n"
    "1071 The National Treasury ........................ 1\n"
    "1072 State Department for Economic Planning ...... 3\n",
)

CHAPTER_1071 = _page(
    2,
    "THE NATIONAL TREASURY - VOTE 1071\n"
    "REPORT ON THE FINANCIAL STATEMENTS\n"
    "Qualified Opinion\n"
    "Basis for Qualified Opinion\n"
    "1. Unsupported Expenditure\n"
    "The statement reflects expenditure of Kshs.1,353,256,472 which was\n"
    "not supported by documents. The following anomalies were noted;\n"
    "1. missing vouchers\n"
    "2. absent approvals\n"
    "2. Pending Accounts Payable\n"
    "Trade payables of Kshs.20,811,926,257 and prior bills of\n"
    "Kshs.17,637,257,074 were not settled.\n"
    "Emphasis of Matter\n"
    "3. Budgetary Control and Performance\n"
    "Final receipts budget of Kshs.122,176,370,707 against actual\n"
    "receipts of Kshs.113,732,718,491.\n"
    "1",
)

CHAPTER_1071_PAGE_2 = _page(
    3,
    "4. There were no material issues relating to Other Information.\n"
    "2",
)

CHAPTER_1072 = _page(
    4,
    "STATE DEPARTMENT FOR ECONOMIC PLANNING VOTE - 1072\n"
    "REPORT ON THE FINANCIAL STATEMENTS\n"
    "Unmodified Opinion\n"
    "5. " + CID_JUNK + "\n"
    "3",
)


class TestTocAndOffset:
    def test_parse_toc(self):
        assert parse_toc([TOC_PAGE]) == [
            (1071, "The National Treasury", 1),
            (1072, "State Department for Economic Planning", 3),
        ]

    def test_find_offset_locates_printed_page_one(self):
        pages = [TOC_PAGE, CHAPTER_1071, CHAPTER_1071_PAGE_2, CHAPTER_1072]
        assert find_offset(pages) == 1


class TestSegmentChapter:
    def _findings(self):
        pages = [TOC_PAGE, CHAPTER_1071, CHAPTER_1071_PAGE_2, CHAPTER_1072]
        findings, rejected = segment_chapter(
            pages, 1071, "The National Treasury", 1, 2, offset=1
        )
        return findings, rejected

    def test_extracts_findings_with_pages_and_context(self):
        findings, _ = self._findings()
        assert [f.paragraph_no for f in findings] == [1, 2, 3]
        f1 = findings[0]
        assert f1.title == "Unsupported Expenditure"
        assert f1.pdf_page == 2
        assert f1.printed_page == 1
        assert f1.heading == "Basis for Qualified Opinion"
        assert f1.opinion == "Qualified Opinion"
        assert severity_for(f1.heading, f1.opinion) == "WARNING"

    def test_numbered_list_items_inside_a_finding_are_not_findings(self):
        # "1. missing vouchers" restarts numbering inside finding 1's body —
        # the continuity rule must keep it as body text.
        findings, _ = self._findings()
        titles = [f.title for f in findings]
        assert "missing vouchers" not in titles
        assert "missing vouchers" in findings[0].finding_text

    def test_amounts_parsed_raw_kes(self):
        findings, _ = self._findings()
        assert findings[0].amounts == [1_353_256_472.0]
        assert findings[1].amounts == [20_811_926_257.0, 17_637_257_074.0]

    def test_no_material_issue_statements_are_filtered(self):
        findings, _ = self._findings()
        assert all("no material issues" not in f.title for f in findings)

    def test_cid_junk_finding_is_rejected_not_stored(self):
        # POSITIVE CONTROL for the text-integrity gate: the junk paragraph
        # in vote 1072 must be rejected, and counted.
        pages = [TOC_PAGE, CHAPTER_1071, CHAPTER_1071_PAGE_2, CHAPTER_1072]
        findings, rejected = segment_chapter(
            pages, 1072, "State Department for Economic Planning", 3, 3, offset=1
        )
        assert findings == []
        assert rejected == 1


class TestParseBlueBook:
    PAGES = [TOC_PAGE, CHAPTER_1071, CHAPTER_1071_PAGE_2, CHAPTER_1072]

    def test_whole_document(self):
        res = parse_blue_book(
            self.PAGES, "https://x.go.ke/REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
        )
        assert isinstance(res, BlueBookResult)
        assert res.fiscal_year_label == "2024/2025"
        assert res.votes_seen == 2
        assert len(res.findings) == 3  # 1072's only paragraph is cid junk
        assert res.rejected_cid == 1

    def test_toc_header_mismatch_skips_chapter(self):
        # MIS-ATTRIBUTION GUARD: if the page where the TOC claims vote 1071
        # starts does not confirm the vote number, the chapter is skipped.
        bad_chapter = _page(2, "SOME OTHER CONTENT ENTIRELY\nmore text\n1")
        res = parse_blue_book(
            [TOC_PAGE, bad_chapter, CHAPTER_1071_PAGE_2, CHAPTER_1072],
            "REPORT-2024-2025.pdf",
        )
        assert all(f.vote != 1071 for f in res.findings)

    def test_unrecognised_document_extracts_nothing(self):
        res = parse_blue_book(
            [_page(1, "A completely different document\nwith no TOC")],
            "random.pdf",
        )
        assert res.findings == []
        assert res.votes_seen == 0


class TestSourceHash:
    def test_stable_and_key_order_independent(self):
        a = {"x": 1, "y": "text"}
        b = {"y": "text", "x": 1}
        assert source_hash_of(a) == source_hash_of(b)
        assert len(source_hash_of(a)) == 64

    def test_changes_when_content_changes(self):
        assert source_hash_of({"x": 1}) != source_hash_of({"x": 2})
