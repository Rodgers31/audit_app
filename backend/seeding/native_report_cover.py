"""Bounded native cover text with pdfplumber's existing glyph interpreter.

Availability parsing needs characters from the first three physical pages.
Vector artwork and image layout objects never supplied extract_text's chars;
discard those allocations while retaining every text, font and marked-content
operation. Do not use PDF.pages/close: they traverse the entire document even
with pages=[1, 2, 3]. The owned stream and every selected page close explicitly.
"""
from io import BytesIO

from pdfminer.pdfpage import PDFPage
from pdfplumber import PDF
from pdfplumber.page import Page, PDFPageAggregatorWithMarkedContent, PDFPageInterpreter
from pdfplumber.utils.exceptions import PdfminerException


class _CoverTextDevice(PDFPageAggregatorWithMarkedContent):
    def paint_path(self, *args, **kwargs):
        pass

    def render_image(self, *args, **kwargs):
        pass


class _CoverPage(Page):
    @property
    def layout(self):
        if hasattr(self, '_layout'):
            return self._layout
        device = _CoverTextDevice(self.pdf.rsrcmgr, pageno=self.page_number,
                                  laparams=self.pdf.laparams)
        try:
            PDFPageInterpreter(self.pdf.rsrcmgr, device).process_page(self.page_obj)
        except Exception as exc:
            raise PdfminerException(exc) from exc
        self._layout = device.get_result()
        return self._layout


def extract_cover_texts(body):
    result = []
    with BytesIO(body) as stream:
        pdf = PDF(stream)
        try:
            raw_pages = PDFPage.create_pages(pdf.doc)
            doctop = 0
            for number in range(1, 4):
                try:
                    raw_page = next(raw_pages)
                except StopIteration:
                    break
                except Exception as exc:
                    raise PdfminerException(exc) from exc
                page = _CoverPage(pdf, raw_page, page_number=number, initial_doctop=doctop)
                try:
                    text = page.extract_text() or ''
                    if len(text) > 100000:
                        raise ValueError('Bounded cover text required')
                    result.append((number, text))
                    doctop += page.height
                finally:
                    page.close()
        finally:
            pdf.flush_cache()
    return result
