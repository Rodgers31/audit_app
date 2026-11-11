"""OAG national FY2024/25 source regressions, plus adjacent grammar controls.

The fixture retains original pdfplumber text and glyph geometry from the
SHA256-bound official PDF. Page numbers below are physical, one based.
"""
import copy
import json
from pathlib import Path

import pytest

from seeding.extractors import oag_blue_book as bb


SOURCE = json.loads((Path(__file__).parent / "fixtures/oag_structural_2024_2025.json").read_text())


def walk(text, *, statements=None):
    kwargs = {} if statements is None else {"clean_statements": statements}
    return bb.segment_chapter([bb.PageText(1, text, "pdfplumber")], 1112, "Department", 1, 1, 0, **kwargs)[0]


@pytest.mark.parametrize("page,paragraph,expected", [
    (423, 1347, "Payment of Claims"),
    (510, 1596, "Long Outstanding Pending Accounts Payable"),
])
def test_source_wrapped_references_preserve_parent_and_list(page, paragraph, expected):
    text = next(p["text"] for p in SOURCE["pages"] if p["page_number"] == page)
    row = next(r for r in walk(text) if r.paragraph_no == paragraph)
    assert expected in row.finding_text
    assert row.title == ("Unresolved Prior Year Audit Matters" if page == 423 else "Unresolved Prior Year Matters")
    pages = [bb.PageText(i, "", "pdfplumber") for i in range(1, page)] + [bb.PageText(page, text, "pdfplumber")]
    row = next(r for r in bb.segment_chapter(pages,1112,"Department",page-13,page-13,13)[0] if r.paragraph_no == paragraph)
    assert (row.pdf_page, row.printed_page) == (page, page-13)


@pytest.mark.parametrize("reference", [
    "Report on the Financial Statements, and the control report.",
    "REPORT ON THE FINANCIAL STATEMENTS was cited in the previous year.",
    "REPORT ON THE FINANCIAL STATEMENTS\nwas cited in the previous year.",
    "Report on the Financial Statements\nwas cited in the previous year.",
    "Report on Lawfulness and Effectiveness in the Use of Public Resources,\nremained unresolved.",
])
def test_heading_words_in_prose_stay_in_parent(reference):
    rows = walk("Other Matter\n10. Unresolved Prior Year Matters\nThe prior report,\n" + reference + "\nNo. Audit Issues\n1. Pending Bills\n1")
    assert len(rows) == 1
    assert "Pending Bills" in rows[0].finding_text
    assert " ".join(reference.split()) in rows[0].finding_text


@pytest.mark.parametrize("heading", [
    "REPORT ON THE FINANCIAL STATEMENTS",
    "Report on the Financial Statements",
    "REPORT ON LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC\nRESOURCES",
    "Report on Lawfulness and Effectiveness in Use of\nPublic Resources",
    "REPORT ON EFFECTIVENESS OF INTERNAL CONTROLS, RISK MANAGEMENT\nAND GOVERNANCE",
    "REPORT ON EFFECTIVENESS OF INTERNAL CONTROLS, RISK MANAGEMENT,\nAND GOVERNANCE",
    "REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE THE OF PUBLIC RESOURCES",
    "REPORT ON LAWFULNESS AND THE EFFECTIVENESS IN THE USE OF PUBLIC RESOURCES",
    "REPORT ON THE LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC RESOURCES",
    "REPORT ON LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC RESOURCES.",
    "REPORT ON EFFECTIVENESS OF INTERNAL CONTROL, RISK MANAGEMENT AND GOVERNANCE",
    "REPORT ON EFFECTIVENESS OF INTERNAL CONTROLS, RISK MANAGEMENT",
    "REPORT ON THE EFFECTIVENESS OF INTERNAL CONTROLS, RISK MANAGEMENT AND GOVERNANCE",
    "REPORT ON THE FINACIAL STATEMENTS",
    "REPORT ON THE REVENUE STATEMENTS",
])
def test_complete_standalone_heading_closes_parent(heading):
    rows = walk("Other Matter\n10. Prior matter\nFirst body.\n" + heading + "\nBasis for Conclusion\n11. Current matter\nNext body.\n1")
    assert [r.paragraph_no for r in rows] == [10, 11]
    assert rows[0].finding_text == "Prior matter First body."
    assert rows[1].heading == "Basis for Conclusion"
    assert rows[1].subreport == heading.splitlines()[0]


def test_clean_source_statement_is_retained_separately_with_lineage():
    statements = []
    text = next(p["text"] for p in SOURCE["pages"] if p["page_number"] == 510)
    rows = walk(text, statements=statements)
    assert 1594 not in [r.paragraph_no for r in rows]
    clean = next(r for r in statements if r.paragraph_no == 1594)
    assert clean.finding_text.startswith("There were no issues noted during the audit")
    assert clean.opinion == "Unmodified Opinion"


@pytest.mark.parametrize("suffix", [
    " However, unsupported expenditure of Kshs.1,250 was observed.",
    " except for unsupported expenditure of Kshs.1,250.",
])
def test_clean_prefix_does_not_discard_adverse_qualification(suffix):
    rows = walk("Conclusion\n10. There were no material issues relating to controls." + suffix + "\n1")
    assert len(rows) == 1
    assert rows[0].amounts == [1250.0]


@pytest.mark.parametrize("suffix", [
    " Unsupported expenditure of Kshs.1,250 was observed.",
    " and unsupported expenditure of Kshs.1,250 was observed.",
])
def test_clean_statement_requires_a_complete_positive_conclusion(suffix):
    rows = walk("Conclusion\n10. There were no material issues relating to controls." + suffix + "\n1")
    assert len(rows) == 1
    assert rows[0].amounts == [1250.0]


@pytest.mark.parametrize("suffix", [
    "; cash was misappropriated.",
    " whose cash balance could not be verified.",
    " and the cash balance could not be verified.",
])
def test_financial_clean_scope_cannot_consume_an_adverse_clause(suffix):
    rows = walk("Unmodified Opinion\n10. There were no material issues noted during the audit of financial statements of the Project" + suffix + "\n1")
    assert len(rows) == 1
    assert suffix in rows[0].finding_text


@pytest.mark.parametrize("page,paragraph,title", [
    (86,215,"There were no material issues"),
    (575,1813,"Delay in Completion of Works"),
])
def test_source_spaced_numbered_markers_preserve_paragraphs(page, paragraph, title):
    text = next(p["text"] for p in SOURCE["pages"] if p["page_number"] == page)
    if paragraph == 1813:
        assert any(r.paragraph_no == paragraph for r in walk(text))
    clean = []
    rows = walk(text, statements=clean)
    row = next(r for r in rows+clean if r.paragraph_no == paragraph)
    assert row.title.startswith(title)
    if paragraph == 1813:
        assert row in rows
        assert not any(title in r.finding_text for r in rows if r.paragraph_no != paragraph)
    else:
        assert row in clean


@pytest.mark.parametrize("heading", [
    "REPORT OF OTHER LEGAL AND REGULATORY REQUIREMENTS",
    "REPORT ON OTHER LEGAL REQUIREMENTS",
    "REPORT ON OTHER LEGAL AND REGULATIORY REQUIREMENTS",
])
def test_source_legal_heading_variants_are_neutral(heading):
    rows = walk("Basis for Adverse Opinion\n10. Prior matter\nBody.\n" + heading +
                "\n11. As required by the agreement, the records were kept.\n1")
    payload = bb.finding_to_extracted_json(rows[-1], "2024/2025")
    assert payload["severity"] == "INFO"
    assert payload["observation_type"] == "statutory_reporting"


@pytest.mark.parametrize("page,paragraph", [(379,1193), (483,1505), (640,2002)])
def test_new_source_project_does_not_inherit_statutory_context(page, paragraph):
    text = next(p["text"] for p in SOURCE["pages"] if p["page_number"] == page)
    prefix = "REPORT ON OTHER LEGAL AND REGULATORY REQUIREMENTS\n"
    rows = walk(prefix + f"{paragraph-2}. As required by the agreement, the records were kept.\n" + text) if page != 379 else walk(text)
    row = next(r for r in rows if r.paragraph_no == paragraph)
    payload = bb.finding_to_extracted_json(row, "2024/2025")
    assert payload.get("observation_type") != "statutory_reporting"
    if page == 379:
        assert payload["severity"] == "WARNING"


def test_source_numbered_opinion_retains_clean_body_and_identity():
    text = next(p["text"] for p in SOURCE["pages"] if p["page_number"] == 483)
    clean = []
    rows = walk(text, statements=clean)
    statement = next(r for r in clean if r.paragraph_no == 1504)
    assert statement.title == "Unmodified Opinion"
    assert statement.opinion == "Unmodified Opinion"
    assert "There were no material issues noted" in statement.finding_text
    assert all(r.paragraph_no != 1504 for r in rows)


@pytest.mark.parametrize("heading", [
    "REPORT ON OTHER LEGAL AND REGULATORY\nREQUIREMENTS",
    "REPORT ON OTHER LEGAL AND REGULATORY\n\nREQUIREMENTS",
])
def test_wrapped_statutory_heading_preserves_classification(heading):
    rows = walk("Basis for Adverse Opinion\n10. Prior matter\nBody.\n" + heading +
                "\n11. As required by the agreement, the records were kept.\n1")
    payload = bb.finding_to_extracted_json(rows[-1], "2024/2025")
    assert payload["severity"] == "INFO"
    assert payload["observation_type"] == "statutory_reporting"


def test_statutory_report_resets_inherited_adverse_severity():
    rows = walk("Basis for Adverse Opinion\n10. Unsupported Payments\nKshs.5,000 was unsupported.\n"
                "REPORT ON OTHER LEGAL AND REGULATORY REQUIREMENTS\n"
                "11. As required by the Financing Agreement, I report based on my audit\n"
                "that I have obtained all information and explanations necessary for the audit.\n1")
    payload = bb.finding_to_extracted_json(rows[1], "2024/2025")
    assert payload["severity"] == "INFO"
    assert payload["observation_type"] == "statutory_reporting"
    assert payload["heading"] is None
    assert payload["opinion"] is None
    assert rows[0].amounts == [5000.0]


def test_source_lowered_fraction_denominator_keeps_reading_order():
    from pdfplumber.utils import chars_to_textmap

    raw = copy.deepcopy(SOURCE["fraction_chars"])
    before = chars_to_textmap(raw).as_string
    assert "(2/ )" in before
    fixed = bb._inline_fraction_chars(raw)
    after = chars_to_textmap(fixed).as_string
    assert after.count("(2/3)") == 2
    assert "should ensure compliance" in " ".join(after.split())
    assert raw == SOURCE["fraction_chars"]
    assert sorted(c["text"] for c in fixed) == sorted(c["text"] for c in raw)


def test_pdf_reader_preserves_source_fraction(monkeypatch):
    import pdfplumber
    from pdfplumber.utils import chars_to_textmap

    class SourcePage:
        chars = SOURCE["fraction_chars"]
        bbox = SOURCE["fraction_bbox"]
        width, height = bbox[2], bbox[3]

        def extract_text(self):
            return chars_to_textmap(self.chars).as_string

        def close(self):
            pass

    class PDF:
        pages = [SourcePage()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(pdfplumber, "open", lambda _: PDF())
    page = bb.read_pages(Path("fixture-only.pdf"), ocr_enabled=False)[0]
    assert page.text.count("(2/3)") == 2
    assert "should ensure compliance" in " ".join(page.text.split())


def test_fraction_geometry_does_not_move_a_digit_on_another_line():
    raw = copy.deepcopy(SOURCE["fraction_chars"])
    digit = next(c for c in raw if c["text"] == "3" and 258 < c["top"] < 260)
    digit["top"] += 15
    digit["bottom"] += 15
    assert bb._inline_fraction_chars(raw) == raw


@pytest.mark.parametrize("invalid", [float("nan"),float("inf"),True,None])
def test_fraction_geometry_requires_finite_numeric_anchor_sizes(invalid):
    raw = copy.deepcopy(SOURCE["fraction_chars"])
    for char in raw:
        if char["text"] in "(/)" and 255 < char["top"] < 256:
            char["size"] = invalid
    index = next(i for i,c in enumerate(raw) if c["text"] == "3" and 258 < c["top"] < 260)
    assert bb._inline_fraction_chars(raw)[index]["top"] == raw[index]["top"]


@pytest.mark.parametrize("fails", [False,True])
def test_reader_releases_page_cache_after_text_or_failure(monkeypatch, fails):
    import pdfplumber

    class Page:
        closed = False

        def close(self):
            self.closed = True

    page = Page()

    class PDF:
        pages = [page]

        def __enter__(self):
            return self

        def __exit__(self,*args):
            return False

    monkeypatch.setattr(pdfplumber,"open",lambda _:PDF())

    def read(_, *, qualifications=None):
        if fails:
            raise ValueError("fixture extraction failure")
        return "Genuine source text"

    monkeypatch.setattr(bb,"_page_text",read)
    if fails:
        with pytest.raises(ValueError,match="fixture extraction failure"):
            bb.read_pages(Path("fixture-only.pdf"),ocr_enabled=False)
    else:
        assert bb.read_pages(Path("fixture-only.pdf"),ocr_enabled=False)[0].text == "Genuine source text"
    assert page.closed
