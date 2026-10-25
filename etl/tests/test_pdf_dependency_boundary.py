"""Exercise the maintained PDF readers against an owned, local ruled table."""

import logging

import pytest

from etl import knbs_parser
from etl.extractor import DocumentExtractor


@pytest.fixture
def table_pdf(tmp_path):
    rows = [("County", "Year", "Population"), ("Samburu", "2019", "310327")]
    commands = ["0.5 w"]
    for x in (50, 180, 300, 450):
        commands.append(f"{x} 640 m {x} 700 l S")
    for y in (640, 670, 700):
        commands.append(f"50 {y} m 450 {y} l S")
    for row, y in zip(rows, (680, 650)):
        for text, x in zip(row, (60, 190, 310)):
            commands.append(f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET")
    content = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(document)
    document.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path = tmp_path / "owned-table.pdf"
    path.write_bytes(document)
    return path


def test_pdfplumber_extracts_original_table_values(table_pdf):
    result = DocumentExtractor()._extract_with_pdfplumber(str(table_pdf))
    assert "error" not in result
    assert len(result["tables"]) == 1
    table = result["tables"][0]["data"]
    assert table["headers"] == ["County", "Year", "Population"]
    assert table["rows"] == [["Samburu", "2019", "310327"]]


def test_camelot_raster_path_preserves_original_table_values(table_pdf):
    result = DocumentExtractor()._extract_with_camelot(str(table_pdf))
    assert "error" not in result
    assert len(result["tables"]) == 1
    assert result["tables"][0]["rows"] == [
        ["County", "Year", "Population"],
        ["Samburu", "2019", "310327"],
    ]


def test_knbs_maintained_reader_fallback_extracts_text(monkeypatch, table_pdf, caplog):
    monkeypatch.setattr(knbs_parser, "pdfplumber", None)
    assert knbs_parser.PdfReader is not None
    parser = knbs_parser.KNBSParser()
    with caplog.at_level(logging.INFO, logger=knbs_parser.__name__):
        text = parser._extract_text_from_pdf(table_pdf.read_bytes())
        assert parser._extract_text_from_pdf(b"not a PDF") == ""
    assert all(value in text for value in ("Samburu", "2019", "310327"))
    assert "using pypdf" in caplog.text
    assert "pypdf failed" in caplog.text
    assert "PyPDF2" not in caplog.text
