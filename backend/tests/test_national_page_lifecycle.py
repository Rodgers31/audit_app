"""Executable resource invariant over the real producer extraction function."""
import pytest
from seeding.domains.national_budget.fetcher import _extract_page_texts

class Page:
    def __init__(self,pdf,number,text,fail=False):self.pdf,self.number,self.text,self.fail=pdf,number,text,fail;self.closed=False
    def extract_text(self):
        assert not self.pdf.live,'Prior page layout retained before next extraction'
        self.pdf.live.add(self.number)
        if self.fail:raise RuntimeError('controlled text failure')
        return self.text
    def close(self):self.closed=True;self.pdf.live.discard(self.number)
class PDF:
    def __init__(self,fail=False):self.live=set();self.pages=[Page(self,1,'first',fail),Page(self,2,None)]
    def __enter__(self):return self
    def __exit__(self,*exc):return False

def test_layout_is_released_before_next_page_with_exact_text_and_order(monkeypatch):
    import pdfplumber
    pdf=PDF();monkeypatch.setattr(pdfplumber,'open',lambda *a,**k:pdf)
    assert _extract_page_texts('owned.pdf')==[{'page':1,'text':'first'},{'page':2,'text':''}]
    assert not pdf.live and all(p.closed for p in pdf.pages)

def test_failed_page_is_released_before_extraction_error_escapes(monkeypatch):
    import pdfplumber
    pdf=PDF(fail=True);monkeypatch.setattr(pdfplumber,'open',lambda *a,**k:pdf)
    with pytest.raises(RuntimeError,match='controlled text failure'):_extract_page_texts('owned.pdf')
    assert pdf.pages[0].closed and not pdf.live
