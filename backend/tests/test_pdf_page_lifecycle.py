"""Tables must survive page cleanup; heavy layouts must not survive advancement."""

from contextlib import contextmanager

import pytest

from seeding.pdf_parsers import (
    CoBQuarterlyReportParser,
    ExtractedTable,
    PDFCorruptedError,
    extract_all_tables,
)


class CachedPage:
    def __init__(self, number, events, active, tables=None, failure=None):
        self.number = number
        self.events = events
        self.active = active
        self.tables = tables if tables is not None else [
            [[" County ", "Amount"], [" Nairobi ", "0"], ["Mombasa", None]],
            [],
            [["Header only"]],
            [["Exact"], ["12.3400"]],
        ]
        self.failure = failure
        self.bbox = (0, 0, 100, 200)

    def extract_tables(self):
        # A layout is materialized only when a selected page is processed.
        self.events.append(("extract", self.number, tuple(sorted(self.active))))
        self.active.add(self.number)
        if self.failure:
            raise self.failure
        return self.tables

    def close(self):
        self.events.append(("close", self.number))
        self.active.discard(self.number)

    def extract_text(self):
        self.events.append(("text", self.number, tuple(sorted(self.active))))
        self.active.add(self.number)
        if self.failure:
            raise self.failure
        return "Table 3.1: Nairobi County, Revenue Performance"


def install_pdf(monkeypatch, pages, events):
    @contextmanager
    def opened(_path):
        try:
            yield type("PDF", (), {"pages": pages})()
        finally:
            events.append(("pdf_exit",))
            # Mirror real pdfplumber: document exit also closes all pages.
            for page in pages:
                page.close()

    monkeypatch.setattr("seeding.pdf_parsers.pdfplumber.open", opened)


@pytest.mark.parametrize("selected", [None, [1, 3], []])
def test_layouts_released_before_next_page_without_losing_tables(
    tmp_path, monkeypatch, selected
):
    events, active = [], set()
    pages = [CachedPage(i, events, active) for i in range(1, 5)]
    install_pdf(monkeypatch, pages, events)
    path = tmp_path / "fixture.pdf"
    path.touch()

    tables = extract_all_tables(path, pages=selected)

    wanted = [1, 2, 3, 4] if selected is None else selected
    assert [(t.page_number, t.table_index, t.headers, t.rows, t.bbox) for t in tables] == [
        item
        for number in wanted
        for item in [
            (number, 0, ["County", "Amount"], [["Nairobi", "0"], ["Mombasa", ""]], (0, 0, 100, 200)),
            (number, 3, ["Exact"], [["12.3400"]], (0, 0, 100, 200)),
        ]
    ]
    assert [(e[1], e[2]) for e in events if e[0] == "extract"] == [
        (number, ()) for number in wanted
    ], "previous page layouts remained alive when processing the next page"
    assert not active


@pytest.mark.parametrize("failure", [False, True])
def test_revenue_caption_scan_releases_each_layout_and_preserves_refusal(
    tmp_path, monkeypatch, failure
):
    events, active = [], set()
    pages = [CachedPage(i, events, active) for i in range(1, 5)]
    if failure:
        pages[1].failure = ValueError("bad caption page")
    install_pdf(monkeypatch, pages, events)
    parser = CoBQuarterlyReportParser(tmp_path / "fixture.pdf")
    parser.tables = [ExtractedTable(2, 0, ["Revenue"], [["0"]], (0, 0, 100, 200)),
                     ExtractedTable(4, 0, ["Revenue"], [["12.3400"]], (0, 0, 100, 200))]
    monkeypatch.setattr("seeding.pdf_parsers._is_revenue_table", lambda table: True)
    captured = []
    monkeypatch.setattr("seeding.pdf_parsers.group_revenue_tables_by_county",
                        lambda tables, captions: captured.append((tables, captions)) or {})

    assert parser._extract_county_revenue_receipts() == []

    assert [(e[1], e[2]) for e in events if e[0] == "text"] == [
        (number, ()) for number in ([1, 2] if failure else [1, 2, 3, 4])
    ], "caption page layouts accumulated between pages"
    last = 2 if failure else 4
    assert events.index(("close", last)) < events.index(("pdf_exit",))
    assert not active
    if failure:
        assert captured == []
        assert {item["reason"] for item in parser.revenue_coverage.values()} == {
            "revenue_captions_unreadable"
        }
    else:
        assert captured[0][0] == parser.tables
        assert captured[0][1] == {number: "Nairobi" for number in [1, 2, 3, 4]}
        assert {item["reason"] for item in parser.revenue_coverage.values()} == {
            "no_supported_revenue_table"
        }


@pytest.mark.parametrize("failure_at", ["extract", "normalize"])
def test_failed_page_releases_layout_before_document_cleanup(
    tmp_path, monkeypatch, failure_at
):
    class InvalidCell:
        def __str__(self):
            raise ValueError("bad cell")

    events, active = [], set()
    failing = CachedPage(
        2, events, active,
        failure=ValueError("bad page") if failure_at == "extract" else None,
        tables=[[['Header'], [InvalidCell()]]] if failure_at == "normalize" else None,
    )
    pages = [CachedPage(1, events, active), failing, CachedPage(3, events, active)]
    install_pdf(monkeypatch, pages, events)
    path = tmp_path / "fixture.pdf"
    path.touch()

    with pytest.raises(PDFCorruptedError) as error:
        extract_all_tables(path)

    assert isinstance(error.value.__cause__, ValueError)
    assert ("extract", 3, ()) not in events
    assert events.index(("close", 2)) < events.index(("pdf_exit",)), (
        "failed page layout survived until document cleanup"
    )
    assert not active
