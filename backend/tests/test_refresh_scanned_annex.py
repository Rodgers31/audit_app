"""OCR is a bounded text-acquisition port; the financial gates remain real."""
from types import SimpleNamespace
from decimal import Decimal
import json
from pathlib import Path

from PIL import Image
import pdfplumber
import pytest
import pytesseract

from seeding.domains.fiscal_summary import fiscal_framework as ff


def _pages():
    source = Path(__file__).parent / 'fixtures/budget_summary/fy2026_27.json'
    doc = json.loads(source.read_text())
    return [doc['pages'].get(str(i), '') for i in range(1, doc['_source']['page_count'] + 1)]


def _image_pdf(monkeypatch, *, ocr_text=None, ocr_error=None):
    original = _pages()
    calls = []

    class Page:
        width, height = 612, 792

        def __init__(self, number, text):
            self.page_number, self.text = number, text
            self.images = ([dict(x0=30, x1=580, top=60, bottom=740)]
                           if number == 63 else [])

        def extract_text(self):
            return ('Annex Table 2a: Fiscal Framework (Ksh billion)'
                    if self.page_number == 63 else self.text)

        def to_image(self, *, resolution, **kwargs):
            calls.append((self.page_number, resolution))
            return SimpleNamespace(original=Image.new('L', (1200, 1600), 255))

    class PDF:
        pages = [Page(i + 1, text) for i, text in enumerate(original)]

        def __enter__(self): return self
        def __exit__(self, *args): return False

    def recognize(*args, **kwargs):
        if ocr_error is not None:
            raise ocr_error('owned OCR failure')
        return original[62] if ocr_text is None else ocr_text

    monkeypatch.setattr(pdfplumber, 'open', lambda *args: PDF())
    monkeypatch.setattr(pytesseract, 'image_to_string', recognize)
    return calls


def test_image_annex_reaches_existing_narrative_and_arithmetic_gates(monkeypatch):
    calls = _image_pdf(monkeypatch)
    records = ff.extract_page_texts('owned.pdf')
    edition = ff.read_edition([r['text'] for r in records], fiscal_year='FY 2026/27')
    split = ff.split_for_fiscal_year(edition, 'FY 2026/27', known_ordinary_revenue=2985.7)
    assert split.values['expenditure'] == Decimal('4785.2')
    assert calls == [(63, 300)]
    assert records[62]['ocr_status'] == 'read'


@pytest.mark.parametrize('error', [FileNotFoundError, RuntimeError])
def test_missing_or_failed_ocr_remains_an_explicit_refusal(monkeypatch, error):
    _image_pdf(monkeypatch, ocr_error=error)
    records = ff.extract_page_texts('owned.pdf')
    assert records[62]['ocr_status'] == 'unavailable'
    with pytest.raises(ff.FiscalFrameworkError, match='annex_has_no_rows'):
        ff.read_edition([r['text'] for r in records], fiscal_year='FY 2026/27')


@pytest.mark.parametrize('case', ['cover', 'annex', 'negative_recurrent', 'interest_exceeds_recurrent'])
def test_ambiguous_or_nonsensical_annex_is_not_published(monkeypatch, case):
    pages = _pages()
    if case == 'cover':
        pages[0] += '\nBUDGET SUMMARY FOR THE FISCAL YEAR 2025/26'
    elif case == 'annex':
        pages.append(pages[62].replace('3538.7', '9999.9'))
    else:
        lines = pages[62].splitlines()
        for i, line in enumerate(lines):
            if line.startswith('Recurrent expenditure '):
                values = line[len('Recurrent expenditure '):].split()
                values[5] = '-1.0' if case == 'negative_recurrent' else '0.0'
                lines[i] = 'Recurrent expenditure ' + ' '.join(values)
        pages[62] = '\n'.join(lines)
    with pytest.raises(ff.FiscalFrameworkError):
        edition = ff.read_edition(pages, fiscal_year='FY 2026/27')
        ff.split_for_fiscal_year(edition, 'FY 2026/27', known_ordinary_revenue=2985.7)
