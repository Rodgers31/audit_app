"""The supported county report is indexed by its own captions, never guessed pages."""
from contextlib import contextmanager
import pytest
from seeding import pdf_parsers as pdf


def source(monkeypatch, *, missing=None, wrong_offset=False):
    entries=[('2.1','Own Source Revenue Collection',1),
             ('2.5','County Budget Allocation, Expenditure and Absorption Rate',5)]
    entries += [(f'3.{i+1}',f'{name} County, Revenue Performance',20+i*10)
                for i,name in enumerate(pdf.KENYAN_COUNTIES)]
    # A following caption bounds each revenue table, including its continuations.
    entries += [(f'3.{100+i}',f'{name} County, Revenue Arrears',24+i*10)
                for i,name in enumerate(pdf.KENYAN_COUNTIES)]
    texts={1:'\n'.join(f'Table {num}: {title} ........ {page}' for num,title,page in entries)}
    for num,title,page in entries:
        texts[page+10]=f'Table {num}: {title}\nactual table'
    if missing is not None:texts.pop(missing+10,None)
    if wrong_offset:texts[11]='unrelated table'
    seen=[]
    class Page:
        def __init__(self,n):self.n=n
        def extract_text(self):seen.append(self.n);return texts.get(self.n,'')
        def close(self):pass
    class Document:
        pages=[Page(i) for i in range(1,520)]
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(pdf.pdfplumber,'open',lambda path:Document())
    return seen


def test_supported_report_selects_all_counties_and_continuations(monkeypatch):
    seen=source(monkeypatch)
    selected=pdf.indexed_county_table_pages('owned.pdf')
    assert selected is not None and len(selected)<300
    assert 15 in selected and 11 in selected
    for i in range(47):
        assert set(range(30+i*10,35+i*10))<=set(selected)
    assert 519 not in selected
    assert len(seen)<180  # bounded text indexing, no 935-page table walk


def test_indexed_caption_mismatch_is_a_refusal(monkeypatch):
    source(monkeypatch,missing=120)
    with pytest.raises(pdf.CountyTableIncomplete):
        pdf.indexed_county_table_pages('owned.pdf')


def test_unsupported_legacy_report_retains_existing_full_scan(monkeypatch):
    class Page:
        def extract_text(self):return 'legacy report, no list of tables'
        def close(self):pass
    class Document:
        pages=[Page()]*4
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(pdf.pdfplumber,'open',lambda path:Document())
    assert pdf.indexed_county_table_pages('owned.pdf') is None
