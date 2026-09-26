"""Splitting OAG's combined county volumes (FY2021/22 onwards) per county.

Run over the four years' eight volumes on 2026-09-26, the extractor the
FY2020/21 volumes went through found 0 findings in three volumes and partial
results in the rest. Each class below is one layout fact that caused it.
The page text is modelled on the real volumes, and line shapes are quoted from
them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seeding.extractors import oag_blue_book as bb
from seeding.extractors import oag_county_volume as cv
from seeding.extractors.oag_blue_book import PageText
from seeding.extractors.oag_county_audit import CountyAuditError

KNOWN = {
    "mombasa": "Mombasa",
    "kwale": "Kwale",
    "kilifi": "Kilifi",
    "taitataveta": "Taita Taveta",
    "nairobi": "Nairobi",
}

TITLE = PageText(
    1,
    "AUDITOR-GENERAL'S REPORT\nON\nTHE COUNTY GOVERNMENTS\nFOR\n"
    "THE YEAR 2024/2025\nVOLUME 1: COUNTY EXECUTIVES",
    "pdfplumber",
)


def _contents(*lines: str, page: int = 2) -> PageText:
    return PageText(
        page,
        "Table of Contents\nVOLUME 1 – COUNTY EXECUTIVES Page\n"
        "Foreword ......................................... iii\n"
        "Code County Executives\n" + "\n".join(lines),
        "pdfplumber",
    )


def _volume(chapters, *, contents=None, tail=()):
    """TITLE, contents, then one page per chapter body, then ``tail`` pages."""
    pages = [TITLE]
    toc_lines = contents or [
        f"{no}. {name} ................................ {i + 1}"
        for i, (no, name, _heading, _body) in enumerate(chapters)
    ]
    pages.append(_contents(*toc_lines))
    for no, _name, heading, body in chapters:
        pages.append(PageText(len(pages) + 1, heading + "\n" + body, "pdfplumber"))
    for text in tail:
        pages.append(PageText(len(pages) + 1, text, "pdfplumber"))
    return pages


BODY = (
    "REPORT ON THE FINANCIAL STATEMENTS\n"
    "Basis for Qualified Opinion\n"
    "{a}. Inaccuracies in Cash and Cash Equivalents\n"
    "The statement reflects Kshs.1,234,567.\n"
    "{b}. Unsupported Pending Bills\n"
    "Pending bills of Kshs.9,999,999 were not supported.\n"
)


class TestContents:
    def test_the_three_contents_line_shapes(self):
        """'18 County Executive of Nyandarua ...' has no period. Nyeri's line
        uses the ellipsis character with no space before the page number. The
        FY2021/22 volumes print a contents page twice."""
        pages = [
            TITLE,
            _contents(
                "1. County Executive of Mombasa ................ 1",
                "18 County Executive of Nyandarua ................ 177",
                "19. County Assembly of Nyeri…………………………………73",
            ),
            _contents("1. County Executive of Mombasa ................ 1", page=3),
        ]
        toc = cv.parse_toc(pages)
        assert sorted(toc) == [1, 18, 19]
        assert toc[19].name == "County Assembly of Nyeri"
        assert toc[19].printed_page == 73

    def test_front_matter_is_not_an_entry(self):
        toc = cv.parse_toc([TITLE, _contents("1. Introduction ........ vi")])
        assert toc == {}

    @pytest.mark.parametrize(
        "name, county",
        [
            ("County Executive of Taita/Taveta", "Taita/Taveta"),
            ("County Assembly of Nairobi City", "Nairobi City"),
            ("Nairobi City County Assembly", "Nairobi City"),
            ("Introduction", None),
        ],
    )
    def test_county_from_auditee(self, name, county):
        assert cv.county_from_auditee(name) == county


class TestSplit:
    def test_chapters_are_found_by_heading_with_no_printed_page_footer(self):
        """FY2023/24 executives: the first chapter page carries no printed
        '1', so find_offset returned None and the old walk extracted nothing
        from a 555-page volume."""
        pages = _volume(
            [
                (1, "County Executive of Mombasa", "COUNTY EXECUTIVE OF MOMBASA - NO.1", BODY.format(a=1, b=2)),
                (2, "County Executive of Kwale", "COUNTY EXECUTIVE OF KWALE – NO.2", BODY.format(a=3, b=4)),
            ]
        )
        assert bb.find_offset(pages) is None  # the old walk's precondition fails
        split = cv.split_volume(pages)
        assert [(c.no, c.county, c.start_page, c.end_page) for c in split.chapters] == [
            (1, "Mombasa", 3, 3),
            (2, "Kwale", 4, 4),
        ]
        assert split.refused == []
        assert split.fiscal_year_in_text == "2024/2025"
        assert split.kind_in_text == "executives"

    def test_the_heading_form_without_of(self):
        pages = _volume(
            [(47, "Nairobi City County Assembly", "NAIROBI CITY COUNTY ASSEMBLY – NO.47", BODY.format(a=1, b=2))]
        )
        assert [c.county for c in cv.split_volume(pages).chapters] == ["Nairobi City"]

    def test_a_heading_naming_a_different_county_is_refused(self):
        """'COUNTY EXECUTIVE OF KILIFI – NO.2' where the contents say No.2 is
        Kwale: file it under neither."""
        pages = _volume(
            [(2, "County Executive of Kwale", "COUNTY EXECUTIVE OF KILIFI – NO.2", BODY.format(a=1, b=2))]
        )
        split = cv.split_volume(pages)
        assert split.chapters == []
        assert split.refused == [(2, "heading_does_not_match_contents")]

    def test_a_contents_entry_with_no_chapter_is_reported(self):
        pages = _volume(
            [(1, "County Executive of Mombasa", "COUNTY EXECUTIVE OF MOMBASA - NO.1", BODY.format(a=1, b=2))],
            contents=[
                "1. County Executive of Mombasa ........ 1",
                "2. County Executive of Kwale ........ 9",
            ],
        )
        assert cv.split_volume(pages).refused == [(2, "chapter_heading_not_found")]

    def test_the_last_chapter_stops_at_the_appendix(self):
        pages = _volume(
            [(1, "County Executive of Mombasa", "COUNTY EXECUTIVE OF MOMBASA - NO.1", BODY.format(a=1, b=2))],
            tail=[
                "APPENDIX\nA: List of County Executives and Audit Opinions\n"
                "S/N County Code County Executive Opinion\n3. 12 Meru Qualified",
                "CONTACTS\n3rd Floor, Anniversary Towers",
            ],
        )
        split = cv.split_volume(pages)
        assert split.chapters[0].end_page == 3
        findings, _ = cv.segment_volume(pages, split)
        assert [f.paragraph_no for _, f in findings] == [1, 2]


class TestSegment:
    def _one_chapter(self, body):
        pages = _volume(
            [(36, "County Executive of Kilifi", "COUNTY EXECUTIVE OF KILIFI – NO.36", body)],
        )
        split = cv.split_volume(pages)
        return cv.segment_volume(pages, split)[0]

    def test_paragraph_numbers_past_999(self):
        """FY2024/25 executives numbers paragraphs continuously to 1323. The
        3-digit pattern merged every finding from 1000 on into the one before."""
        found = self._one_chapter(
            "Basis for Qualified Opinion\n999. Unsupported Receipts\ntext\n"
            "1000. Irregular Payments\ntext\n1001. Stalled Projects\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [999, 1000, 1001]

    def test_an_appendix_citation_inside_a_finding_does_not_end_the_chapter(self):
        """'Appendix VI to the financial statements on summary of fixed assets
        register reflects...' starts a line in chapter 36. The national rule
        broke the chapter there and lost 40 findings."""
        found = self._one_chapter(
            "Basis for Qualified Opinion\n950. Inaccuracies in Property, Plant and Equipment\n"
            "Appendix VI to the financial statements on summary of fixed assets register reflects\n"
            "a balance of Kshs.969,142,528.\n"
            "951. Unsupported Trade and Other Payables Balance\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [950, 951]
        assert "Appendix VI" in found[0][1].finding_text

    def test_a_number_oag_skipped_does_not_lose_the_rest_of_the_chapter(self):
        """1266 appears nowhere in the FY2024/25 executives volume. With a
        strict prev+1 rule, 1267-1282 were all lost."""
        found = self._one_chapter(
            "Basis for Conclusion\n1265. Unsupported Medical Insurance Costs\ntext\n"
            "1267. Non-Compliance with Fiscal Responsibility Principles on Wages\ntext\n"
            "1268. Non-Compliance with Law on Staff Ethnic Composition\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [1265, 1267, 1268]

    def test_a_year_at_the_start_of_a_wrapped_line_is_not_a_finding(self):
        found = self._one_chapter(
            "Basis for Qualified Opinion\n799. Long Outstanding Refundable Deposits\n"
            "The deposits have been outstanding since 30 June,\n"
            "2020. This was contrary to Regulation 106 of the Public Finance Management\n"
            "800. Failure to Undertake Valuation for Assets\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [799, 800]

    def test_a_numbered_list_inside_a_finding_is_not_a_finding(self):
        """A prior-year issues table inside the chapter numbers from 1."""
        found = self._one_chapter(
            "Basis for Qualified Opinion\n804. Ineffectiveness of Internal Audit Functions\n"
            "No. Audit Issues for 2020/2021\n1. Inaccurate Non-Financial Assets\n"
            "2. Variance between Financial Statements and IFMIS\n"
            "805. Failure to Maintain Inventory Register\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [804, 805]

    def test_a_prior_year_issues_table_is_not_findings(self):
        """FY2024/25 assemblies, Mombasa, p.14, verbatim. Finding 2 lists last
        year's six issues as a numbered table. With prev=2, table rows 3-6
        passed as four body-less findings, and the real 3 and 4 after them
        then read as going backwards and were dropped."""
        pages = _volume(
            [
                (1, "County Assembly of Mombasa", "COUNTY ASSEMBLY OF MOMBASA – NO.1",
                 "REPORT ON THE FINANCIAL STATEMENTS\nOther Matter\n"
                 "1. Budgetary Control and Performance\nThe summary shows Kshs.1,000,000.\n"
                 "2. Unresolved Prior Year’s Audit Matters\n"
                 "In the previous year’s audit report, several issues were raised under the Report on the\n"
                 "Financial Statements. Review of the status during the audit in 2024/2025 revealed that the following\n"
                 "six (6) issues remained unresolved as at 30 June, 2025:\n"
                 "No. Audit Issues for 2023/2024\n"
                 "1. Unsupported cash and cash equivalents\n"
                 "2. Inaccurate statement of financial assets and liabilities\n"
                 "3. Inaccurate statement of cash flows\n"
                 "4. Inaccurate statement of comparison of budget and actual amounts\n"
                 "5. Employees over sixty (60) years\n"
                 "6. Non-compliance with the law on ethnic composition\n"
                 "Other Information\n"
                 "3. There were no material issues relating to Other Information.\n"
                 "REPORT ON LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC\nRESOURCES\n"
                 "Basis for Conclusion\n"
                 "4. Non-Compliance with the Law on Staff Ethnic Composition\n"
                 "Review of personnel records for the year under review indicated that the County\n"),
            ]
        )
        found = cv.segment_volume(pages, cv.split_volume(pages))[0]
        assert [(f.paragraph_no, f.title[:24]) for _, f in found] == [
            (1, "Budgetary Control and Pe"),
            (2, "Unresolved Prior Year’s "),
            (4, "Non-Compliance with the "),
        ]
        # The table stays in the finding it belongs to, as its evidence.
        assert "6. Non-compliance with the law on ethnic composition" in found[1][1].finding_text

    def test_a_table_row_that_wraps_does_not_end_the_table(self):
        found = self._one_chapter(
            "Basis for Qualified Opinion\n1. Cash\ntext\n2. Unresolved Prior Year Matters\n"
            "No. Audit Issue\n1. Unsupported cash and cash\nequivalents balances\n"
            "2. Inaccurate statement of financial assets\n3. Pending bills\n"
            "Other Information\n3. Irregular Payments\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [1, 2, 3]
        assert found[2][1].title == "Irregular Payments"

    def test_a_table_is_ended_by_a_number_that_breaks_its_sequence(self):
        """No heading after the table: the next real finding (prev+1 = 841)
        is not 7, so the table is over."""
        found = self._one_chapter(
            "Basis for Qualified Opinion\n840. Unresolved Prior Year Matters\n"
            "No. Audit Issue\n1. Pending Bills\n2. Stalled Projects\n"
            "841. Irregular Procurement\ntext\n"
        )
        assert [f.paragraph_no for _, f in found] == [840, 841]

    def test_the_chapter_heading_is_not_recorded_as_a_sub_section(self):
        found = self._one_chapter("Basis for Qualified Opinion\n1. Cash\ntext\n")
        assert found[0][1].sub_section is None

    def test_the_national_walk_is_unchanged_by_default(self):
        """The keyword arguments must not move the national Blue Book: by
        default a 4-digit number is not a finding and an Appendix line ends
        the chapter."""
        pages = [
            PageText(1, "Basis for Qualified Opinion\n1. First\ntext\n1000. Not a finding\n"
                        "2. Second\nAppendix A tables\n3. After the appendix", "pdfplumber"),
        ]
        found, _ = bb.segment_chapter(pages, 1011, "Vote", 1, 1, 0)
        assert [f.paragraph_no for f in found] == [1, 2]
        assert "1000. Not a finding" in found[0].finding_text


class TestProvenanceGates:
    def test_agreeing_sources_give_the_year_and_name_them(self):
        fy, sources = cv.resolve_fiscal_year(
            in_text="2023/2024", discovered="2023/2024", in_filename=None
        )
        assert (fy, sources) == ("2023/2024", ["oag_year_page", "title_page"])

    def test_disagreeing_sources_refuse(self):
        with pytest.raises(CountyAuditError) as exc:
            cv.resolve_fiscal_year(
                in_text="2023/2024", discovered="2024/2025", in_filename=None
            )
        assert exc.value.reason == "fiscal_year_conflict"

    def test_no_source_refuses(self):
        with pytest.raises(CountyAuditError) as exc:
            cv.resolve_fiscal_year(in_text=None, discovered=None, in_filename=None)
        assert exc.value.reason == "fiscal_year_not_found"

    def test_kind_must_agree(self):
        assert cv.resolve_kind(in_text="executives", discovered="executives") == "executives"
        with pytest.raises(CountyAuditError):
            cv.resolve_kind(in_text="executives", discovered="assemblies")
        with pytest.raises(CountyAuditError):
            cv.resolve_kind(in_text=None, discovered=None)

    @pytest.mark.parametrize(
        "printed, held",
        [("Nairobi City", "Nairobi"), ("Taita/Taveta", "Taita Taveta"), ("Atlantis", None)],
    )
    def test_canonical_county(self, printed, held):
        assert cv.canonical_county(printed, KNOWN) == held


def _hand_made_pdf(path: Path) -> None:
    """One A4 page: a visible line, and a line drawn 500pt left of the page,
    the way the FY2021/22 volumes carry the previous page."""
    content = (
        b"BT /F1 12 Tf 72 700 Td (VISIBLE PAGE TEXT) Tj ET\n"
        b"BT /F1 12 Tf -500 700 Td (HIDDEN PREVIOUS PAGE) Tj ET"
    )
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n" % (len(objs) + 1, xref)
    out += b"%%EOF\n"
    path.write_bytes(out)


class TestOffCanvasText:
    def test_text_drawn_off_the_page_is_not_read(self, tmp_path):
        """FY2021/22: 262 of 546 executive-volume pages carried the previous
        page's text at x=-523, so each read as two pages interleaved."""
        pdf = tmp_path / "offcanvas.pdf"
        _hand_made_pdf(pdf)
        plain = bb.read_pages(pdf, ocr_enabled=False)[0].text
        visible = bb.read_pages(pdf, ocr_enabled=False, visible_only=True)[0].text
        assert "HIDDEN PREVIOUS PAGE" in plain  # the defect, reproduced
        assert "HIDDEN PREVIOUS PAGE" not in visible
        assert "VISIBLE PAGE TEXT" in visible


#: Ten more counties, so the fixture has a volume's contents list (a real one
#: has 47; fewer than 10 is not treated as a volume).
_FILLER = ["Kwale", "Kilifi", "Lamu", "Garissa", "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru", "Embu"]


class TestExtractionRows:
    """The database write, with page text injected in place of a PDF."""

    PAGES = _volume(
        [
            (1, "County Executive of Mombasa", "COUNTY EXECUTIVE OF MOMBASA - NO.1", BODY.format(a=1, b=2)),
            (6, "County Executive of Taita/Taveta", "COUNTY EXECUTIVE OF TAITA/TAVETA – NO.6", BODY.format(a=3, b=4)),
            (7, "County Executive of Atlantis", "COUNTY EXECUTIVE OF ATLANTIS – NO.7", BODY.format(a=5, b=6)),
        ]
        + [
            (10 + i, f"County Executive of {n}", f"COUNTY EXECUTIVE OF {n.upper()} – NO.{10 + i}",
             BODY.format(a=10 + 2 * i, b=11 + 2 * i))
            for i, n in enumerate(_FILLER)
        ]
    )
    #: Mombasa and Taita Taveta resolve; Atlantis and the filler do not.
    KNOWN = {"mombasa": "Mombasa", "taitataveta": "Taita Taveta"}

    @pytest.fixture()
    def doc(self, db_session, seed_source_doc, tmp_path):
        f = tmp_path / "vol.pdf"
        f.write_bytes(b"%PDF-1.4 placeholder")
        seed_source_doc.file_path = str(f)
        seed_source_doc.md5 = "a" * 32
        seed_source_doc.url = (
            "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
            "AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf"
        )
        seed_source_doc.meta = {
            "oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}
        }
        db_session.flush()
        return seed_source_doc

    def _run(self, db_session, doc, monkeypatch):
        monkeypatch.setattr(cv, "read_pages", lambda *a, **k: self.PAGES)
        return cv.extract_county_volume(db_session, doc, None, known_counties=self.KNOWN)

    def test_rows_are_written_for_resolved_counties_only(self, db_session, doc, monkeypatch):
        from models import Extraction

        stats = self._run(db_session, doc, monkeypatch)
        rows = db_session.query(Extraction).filter_by(source_document_id=doc.id).all()
        assert stats["created"] == 4 == len(rows)
        assert stats["refused"] == [[7, "county_not_resolved"]] + [
            [10 + i, "county_not_resolved"] for i in range(len(_FILLER))
        ]
        assert {r.extracted_json["entity_name"] for r in rows} == {
            "County Executive of Mombasa",
            "County Executive of Taita Taveta",
        }
        first = min(rows, key=lambda r: r.extracted_json["paragraph_no"])
        assert first.extractor == cv.EXTRACTOR_ID
        assert first.page_number == 3 == first.extracted_json["pdf_page"]
        assert first.extracted_json["fiscal_year"] == "2024/2025"
        assert first.extracted_json["fiscal_year_sources"] == [
            "filename",
            "oag_year_page",
            "title_page",
        ]
        assert "source_hash" not in first.extracted_json
        assert sorted(stats["fresh_extraction_ids"]) == sorted(r.id for r in rows)

    def test_a_second_run_reads_nothing(self, db_session, doc, monkeypatch):
        self._run(db_session, doc, monkeypatch)
        assert doc.meta["extracted_md5"] == doc.md5  # the first run's stamp
        monkeypatch.setattr(
            cv, "read_pages", lambda *a, **k: pytest.fail("re-read an extracted volume")
        )
        stats = cv.extract_county_volume(db_session, doc, None, known_counties=self.KNOWN)
        assert stats["reason"] == "already_extracted" and stats["skipped"] == 4

    def test_a_year_page_contradicting_the_title_page_refuses(self, db_session, doc, monkeypatch):
        doc.meta = {"oag_discovery": {"fiscal_year": "2023/2024", "kind": "executives"}}
        with pytest.raises(CountyAuditError) as exc:
            self._run(db_session, doc, monkeypatch)
        assert exc.value.reason == "fiscal_year_conflict"

    def test_bytes_that_are_not_a_volume_refuse_whatever_discovery_said(
        self, db_session, doc, monkeypatch
    ):
        """Discovery classifies from a filename and a year page. A single
        entity report filed there by mistake must not be split as 47 counties."""
        single = [PageText(1, "REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF LAMU", "pdfplumber")]
        monkeypatch.setattr(cv, "read_pages", lambda *a, **k: single)
        with pytest.raises(CountyAuditError) as exc:
            cv.extract_county_volume(db_session, doc, None, known_counties=self.KNOWN)
        assert exc.value.reason == "not_a_county_volume"

    def test_no_county_reference_refuses(self, db_session, doc, monkeypatch):
        monkeypatch.setattr(cv, "read_pages", lambda *a, **k: self.PAGES)
        with pytest.raises(CountyAuditError) as exc:
            cv.extract_county_volume(db_session, doc, None, known_counties={})
        assert exc.value.reason == "no_county_reference"
