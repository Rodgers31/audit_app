"""FY2020/21 solid back covers must not make complete OAG reads partial.

The sole rectangle reproduces the actual PDF objects on source2395 p469 and
source2396 p232. Scanned conclusions remain evidence requiring real OCR.
"""
from pathlib import Path

import pytest

from seeding.extractors import oag_blue_book as bb


def write_pdf(path: Path, content: bytes, *, image=False, annotation=False):
    resources = b"/Font << /F1 5 0 R >>"
    if image:
        resources += b" /XObject << /Im1 6 0 R >>"
    annots = b" /Annots [6 0 R]" if annotation else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.276 841.89] "
        b"/Contents 4 0 R /Resources << " + resources + b" >>" + annots + b" >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    if image:
        objects.append(b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
                       b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream")
    if annotation:
        objects.append(b"<< /Type /Annot /Subtype /Text /Rect [20 20 40 40] "
                       b"/Contents (A report note) >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(out)


BACKGROUND = b"0.662 0.053 0.765 0.003 k 0 0.159 595.275 841.571 re f"


@pytest.mark.parametrize("content", [b"", BACKGROUND])
def test_provably_decorative_page_does_not_fail_or_use_ocr(tmp_path, monkeypatch, content):
    pdf = tmp_path / "decorative.pdf"
    write_pdf(pdf, content)
    def forbidden_ocr(*args):
        pytest.fail("an empty/vector-only page must not spend the OCR budget")
    monkeypatch.setattr(bb, "_ocr_page", forbidden_ocr)
    pages = bb.read_pages(pdf, ocr_enabled=True)
    assert pages[0].method == "blank"
    assert pages[0].text == ""


@pytest.mark.parametrize("content,image,annotation", [
    (b"0.3 g 20 20 100 100 re f", False, False),
    (BACKGROUND + b" 0 g 20 20 10 10 re f", False, False),
    (b"0 g 0 0 595.276 841.89 re S", False, False),
    (BACKGROUND + b" 20 20 m 100 100 l S", False, False),
    (BACKGROUND + b" 20 20 m 30 40 50 60 70 80 c S", False, False),
    (BACKGROUND + b" /Im1 Do", True, False),
    (BACKGROUND, False, True),
    (b"/Im1 Do", True, False),
    (b"/Sh0 sh", False, False),
    (BACKGROUND + b" /Sh0 sh", False, False),
    (BACKGROUND + b" /Pattern cs /P0 scn", False, False),
    (BACKGROUND + b" /Missing gs", False, False),
    (BACKGROUND + b" 100 200", False, False),
    (BACKGROUND + b" BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI", False, False),
    (BACKGROUND + b"\nBI /W 1 /H 1 /BPC 8 /CS /G ID \x00\nEI\n", False, False),
    (BACKGROUND + b" (unterminated", False, False),
])
def test_possible_evidence_remains_rejected_without_ocr(tmp_path, content, image, annotation):
    pdf = tmp_path / "evidence.pdf"
    write_pdf(pdf, content, image=image, annotation=annotation)
    assert bb.read_pages(pdf, ocr_enabled=False)[0].method == "rejected"


def test_scanned_evidence_still_requires_ocr_and_failed_ocr_stays_rejected(tmp_path, monkeypatch):
    pdf = tmp_path / "scanned-conclusion.pdf"
    write_pdf(pdf, b"/Im1 Do", image=True)
    calls = []
    monkeypatch.setattr(bb, "_ocr_page", lambda *args: calls.append(args) or "")
    assert bb.read_pages(pdf, ocr_enabled=True)[0].method == "rejected"
    assert len(calls) == 1
    monkeypatch.setattr(bb, "_ocr_page", lambda *args: "CONCLUSION\nReport conclusion")
    assert bb.read_pages(pdf, ocr_enabled=True)[0].method == "ocr"


def test_cid_text_on_background_remains_rejected(tmp_path):
    pdf = tmp_path / "unmapped.pdf"
    write_pdf(pdf, BACKGROUND + b" BT /F1 12 Tf 72 700 Td (\\(cid:123\\)\\(cid:124\\)) Tj ET")
    page = bb.read_pages(pdf, ocr_enabled=False)[0]
    assert bb.cid_ratio(page.text) > bb.CID_REJECT_RATIO
    assert page.method == "rejected"


def test_visible_crop_does_not_certify_hidden_evidence_as_blank(tmp_path):
    pdf = tmp_path / "hidden.pdf"
    write_pdf(pdf, BACKGROUND + b" BT /F1 12 Tf -500 700 Td (REPORT EVIDENCE) Tj ET")
    assert bb.read_pages(pdf, ocr_enabled=False, visible_only=True)[0].method == "rejected"
