"""Independent executable completion attacks against the county-volume walker."""

from copy import deepcopy

import pytest

from models import Extraction
from seeding.extractors import oag_county_volume as cv
from seeding.extractors.oag_blue_book import PageText
from seeding.extractors.reconciliation import IncompleteExtraction, ReconciliationRequired
from tests.test_oag_county_volume import BODY, TITLE, _FILLER, _contents, _volume


COUNTIES = ["Mombasa", "Taita Taveta", *_FILLER]
KNOWN = {cv._letters(name): name for name in COUNTIES}


def readable_pages():
    return _volume([
        (i, f"County Executive of {name}",
         f"COUNTY EXECUTIVE OF {name.upper()} - NO.{i}",
         BODY.format(a=2 * i - 1, b=2 * i))
        for i, name in enumerate(COUNTIES, 1)
    ])


@pytest.fixture
def volume_doc(seed_source_doc, tmp_path):
    path = tmp_path / "volume.pdf"
    path.write_bytes(b"%PDF-1.4 placeholder")
    seed_source_doc.file_path = str(path)
    seed_source_doc.md5 = "a" * 32
    seed_source_doc.url = "https://www.oagkenya.go.ke/COUNTY-EXECUTIVES-2024-2025.pdf"
    seed_source_doc.meta = {
        "oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}
    }
    return seed_source_doc


def extract(db, doc, monkeypatch, pages):
    monkeypatch.setattr(cv, "read_pages", lambda *args, **kwargs: pages)
    return cv.extract_county_volume(db, doc, None, known_counties=KNOWN)


def rows(db, doc):
    return [deepcopy(row.extracted_json) for row in db.query(Extraction).filter_by(
        source_document_id=doc.id, extractor=cv.EXTRACTOR_ID
    ).order_by(Extraction.id)]


def test_readable_positive_control_is_complete_and_reusable(db_session, volume_doc, monkeypatch):
    result = extract(db_session, volume_doc, monkeypatch, readable_pages())
    assert result["partial"] is False
    assert result["created"] == 24
    assert {row["county_name"] for row in rows(db_session, volume_doc)} == set(COUNTIES)
    assert extract(db_session, volume_doc, monkeypatch, readable_pages())["reason"] == "already_extracted"


@pytest.mark.parametrize("heading", [
    "Appendix A: List of County Executives and Audit Opinions given on their Financial",
    "A: List of County Assemblies and Audit Opinions given on their Financial",
])
def test_actual_2021_opinion_appendix_is_end_matter(db_session, volume_doc, monkeypatch, heading):
    pages = readable_pages()
    pages += [PageText(len(pages) + 1,
        heading + "\nStatements\n",
        "pdfplumber"), PageText(len(pages) + 2, "", "rejected")]
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert result["partial"] is False
    assert result["created"] == 24


@pytest.mark.parametrize("location", ["cover", "between", "last", "back_cover"])
def test_unreadable_page_boundaries(db_session, volume_doc, monkeypatch, location):
    pages = readable_pages()
    expected_partial = location in {"between", "last"}
    if location == "cover":
        pages = [PageText(1, "", "rejected")] + [
            PageText(page.page_number + 1, page.text, page.method) for page in pages
        ]
    elif location == "between":
        pages.insert(5, PageText(6, "", "rejected"))
        pages = [PageText(i, page.text, page.method) for i, page in enumerate(pages, 1)]
    elif location == "last":
        pages[-1] = PageText(pages[-1].page_number, "", "rejected")
    else:
        pages += [PageText(len(pages) + 1, "APPENDIX\nCounty opinions", "pdfplumber"),
                  PageText(len(pages) + 2, "", "rejected")]
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert result["partial"] is expected_partial
    assert (volume_doc.meta.get("extracted_md5") == volume_doc.md5) is not expected_partial


def test_unreadable_first_contents_and_chapter_cannot_certify_remaining_volume(
    db_session, volume_doc, monkeypatch
):
    pages = readable_pages()
    # The original TOC is split over two pages. County 1 has its own first
    # contents page, now rejected, and its chapter page is also rejected.
    other_entries = pages[1].text.splitlines()[5:]
    assert len(other_entries) == len(COUNTIES) - 1
    pages = [TITLE, PageText(2, "", "rejected"), _contents(*other_entries, page=3),
             PageText(4, "", "rejected")] + [
        PageText(page.page_number + 1, page.text, page.method) for page in pages[3:]
    ]
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert "Mombasa" not in {row["county_name"] for row in rows(db_session, volume_doc)}
    cached = cv.already_extracted(db_session, volume_doc)
    assert (result["partial"], cached) == (True, 0), (result, cached, volume_doc.meta)


def test_appendix_citation_at_page_start_cannot_hide_last_county_evidence(
    db_session, volume_doc, monkeypatch
):
    pages = readable_pages()
    # A normal citation begins a continuation page, followed by another
    # finding in the same county. Only a true end-matter heading can end it.
    pages.append(PageText(len(pages) + 1,
        "Appendix VI to the financial statements discloses a material balance.\n"
        "25. Unreconciled Receivables\nThe balance was unsupported.\n", "pdfplumber"))
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert any(row["paragraph_no"] == 25 for row in rows(db_session, volume_doc)), result


def test_last_county_rejected_page_after_appendix_citation_remains_partial(
    db_session, volume_doc, monkeypatch
):
    pages = readable_pages()
    pages += [PageText(len(pages) + 1,
                "Appendix VI to the financial statements discloses a material balance.", "pdfplumber"),
              PageText(len(pages) + 2, "", "rejected")]
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert result["partial"] is True, (result, volume_doc.meta)


@pytest.mark.parametrize("mode", ["missing_heading", "wrong_heading", "blank_body", "thin"])
def test_incomplete_reread_preserves_richer_existing_rows(
    db_session, volume_doc, monkeypatch, mode
):
    pages = readable_pages()
    extract(db_session, volume_doc, monkeypatch, pages)
    before = rows(db_session, volume_doc)
    volume_doc.md5 = "b" * 32
    page = pages[3]
    heading, body = page.text.split("\n", 1)
    if mode == "missing_heading":
        text = body
    elif mode == "wrong_heading":
        text = heading.replace("TAITA TAVETA", "MOMBASA") + "\n" + body
    elif mode == "blank_body":
        text = heading
    else:
        text = heading + "\nBasis for Qualified Opinion\n3. Inaccuracies in Cash and Cash Equivalents\nTruncated.\n"
    pages[3] = PageText(page.page_number, text, page.method)
    with pytest.raises((IncompleteExtraction, ReconciliationRequired)):
        extract(db_session, volume_doc, monkeypatch, pages)
    assert rows(db_session, volume_doc) == before


def test_conflicting_duplicate_contents_is_not_complete(db_session, volume_doc, monkeypatch):
    pages = readable_pages()
    pages[1] = PageText(2, pages[1].text + "\n1. County Executive of Kwale ........ 1", "pdfplumber")
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert result["partial"] is True, result


def test_first_run_blank_county_body_is_not_certified_as_complete(
    db_session, volume_doc, monkeypatch
):
    pages = readable_pages()
    # read_pages accepts any nonempty mapped text. A surviving heading with
    # no readable report body is therefore a reachable pdfplumber page.
    page = pages[3]
    pages[3] = PageText(page.page_number, page.text.split("\n", 1)[0], page.method)
    result = extract(db_session, volume_doc, monkeypatch, pages)
    assert "Taita Taveta" not in {row["county_name"] for row in rows(db_session, volume_doc)}
    assert (result["partial"], cv.already_extracted(db_session, volume_doc)) == (True, 0)


def test_repeated_county_heading_cannot_file_evidence_under_previous_county(
    db_session, volume_doc, monkeypatch
):
    pages = readable_pages()
    # A repeated chapter appears after the final county. Duplicate chapter
    # numbers cannot be silently ignored: its findings then inherit Embu.
    pages.append(PageText(len(pages) + 1,
        "COUNTY EXECUTIVE OF MOMBASA - NO.1\n" + BODY.format(a=25, b=26), "pdfplumber"))
    result = extract(db_session, volume_doc, monkeypatch, pages)
    wrong = [(row["paragraph_no"], row["county_name"])
             for row in rows(db_session, volume_doc)
             if row["paragraph_no"] in {25, 26} and row["county_name"] != "Mombasa"]
    assert result["partial"] is True, (result, wrong)
    assert wrong == []
