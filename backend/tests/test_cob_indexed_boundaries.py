"""Independent bounded selector/report controls with owned synthetic pages."""
from pathlib import Path

import pytest
from seeding import pdf_parsers as pdf


def document(monkeypatch):
    offset = 10
    entries = [('2.1','Own Source Revenue Collection',1),
               ('2.5','County Budget Allocation, Expenditure and Absorption Rate',5)]
    for index, county in enumerate(pdf.KENYAN_COUNTIES):
        entries.extend([(f'3.{index*2+1}', f'{county} County, Revenue Performance', 100+index*10),
                        (f'3.{index*2+2}', f'{county} County, Revenue Arrears',104+index*10)])
    texts = {}
    def rebuild_index():
        lines = [f'Table {number}: {title} ........ {page}' for number,title,page in entries]
        for number in range(1,7):
            texts[number] = '\n'.join(lines[(number-1)*20:number*20])
    rebuild_index()
    for number,title,page in entries:
        texts[page+offset] = f'Table {number}: {title}\nActual table cells'
    accessed, closed = [], []
    class Page:
        def __init__(self, number):
            self.number = number
        def extract_text(self):
            accessed.append(self.number)
            return texts.get(self.number,'')
        def close(self):
            closed.append(self.number)
    class Document:
        def __init__(self):
            self.pages = [Page(i) for i in range(1,611)]
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
    monkeypatch.setattr(pdf.pdfplumber,'open',lambda path:Document())
    return entries,texts,rebuild_index,accessed,closed


def test_complete_index_selects_every_county_and_closes_extracted_pages(monkeypatch):
    entries,texts,_,accessed,closed = document(monkeypatch)
    selected = pdf.indexed_county_table_pages(Path('owned.pdf'))
    assert selected == sorted(set(selected))
    for index in range(47):
        assert set(range(110+index*10,115+index*10)) <= set(selected)
    assert len(selected) < 400 and 610 not in selected
    assert sorted(accessed) == sorted(closed)


def test_forged_following_index_page_cannot_truncate_a_real_continuation(monkeypatch):
    entries,texts,_,_,_ = document(monkeypatch)
    # The index misprints the following table at PDF114. Its real caption is
    # PDF116, while PDF115 still contains the revenue grand total.
    texts[114] = 'Continuation of the revenue performance table'
    texts[115] = 'Grand total and final revenue rows'
    texts[116] = 'Table 3.2: Baringo County, Revenue Arrears\nActual table'
    with pytest.raises(pdf.CountyTableIncomplete):
        pdf.indexed_county_table_pages(Path('owned.pdf'))


def test_matching_revenue_start_does_not_authorize_an_unverified_stop_caption(monkeypatch):
    _,texts,_,_,_ = document(monkeypatch)
    texts[114] = 'Table 3.2: Entirely different subject\nActual table'
    with pytest.raises(pdf.CountyTableIncomplete):
        pdf.indexed_county_table_pages(Path('owned.pdf'))


@pytest.mark.parametrize('fault',['conflicting_entry','ambiguous_offset','missing_anchor_confirmation','missing_county_caption'])
def test_recognized_ambiguous_or_incomplete_index_refuses(monkeypatch,fault):
    entries,texts,rebuild,_,_ = document(monkeypatch)
    if fault == 'conflicting_entry':
        entries.append(('3.1','Baringo County, Revenue Performance',101));rebuild()
    elif fault == 'ambiguous_offset':
        texts[16] = texts[15]
    elif fault == 'missing_anchor_confirmation':
        texts[11] = 'Unrelated caption'
    else:
        texts[210] = 'Unrelated county caption'
    with pytest.raises(pdf.CountyTableIncomplete):
        pdf.indexed_county_table_pages(Path('owned.pdf'))


def test_unsupported_partial_toc_uses_full_scan(monkeypatch):
    entries,_,rebuild,_,_ = document(monkeypatch)
    entries[:] = [item for item in entries if item[0] != '3.1']
    rebuild()
    assert pdf.indexed_county_table_pages(Path('owned.pdf')) is None


@pytest.mark.parametrize('number,title', [
    ('4.1', 'County Personnel Emoluments Expenditure'),
    ('3.999', 'County Personnel Emoluments Expenditure'),
    ('3.999', 'County Personnel Emolument Expenditure'),
    ('3.999', 'Emolument Expenditure for County Personnel'),
])
def test_relevant_table_outside_chapter2_is_preserved_or_refused_not_silently_omitted(monkeypatch,number,title):
    entries,texts,rebuild,_,_ = document(monkeypatch)
    entries.append((number,title,590));rebuild()
    texts[600] = f'Table {number}: {title}\nActual table'
    rows = [[name,'100','80','80'] for name in pdf.KENYAN_COUNTIES]
    tables = [pdf.ExtractedTable(15,0,['County','Allocated','Absorbed','Rate'],
                                rows+[['Total','4700','3760','80']],(0,0,0,0)),
              pdf.ExtractedTable(600,0,['County Personnel Emoluments','Allocated','Absorbed','Rate'],
                                 rows,(0,0,0,0))]
    def extract(path,*,pages=None):
        return [table for table in tables if pages is None or table.page_number in pages]
    monkeypatch.setattr(pdf,'extract_all_tables',extract)
    def parse():
        parser = pdf.CoBQuarterlyReportParser(Path('owned.pdf'))
        parser._period = ('2025/26','Q1')
        return parser.parse()
    with monkeypatch.context() as control:
        control.setattr(pdf,'indexed_county_table_pages',lambda path:None)
        full = parse()
    assert sum(row['category']=='Personnel Emoluments' for row in full) == 47
    try:
        indexed = parse()
    except pdf.CountyTableIncomplete:
        return  # Explicitly unsupported/refused is safe; partial success is not.
    assert sum(row['category']=='Personnel Emoluments' for row in indexed) == 47, \
        'Recognized index silently omitted 47 valid records that the full parser emits'


@pytest.mark.parametrize('qualified',[False,True],ids=['unknown-bytes-full-walk','qualified-bytes-indexed'])
def test_optimization_requires_a_fully_compared_content_profile(tmp_path,monkeypatch,qualified):
    import hashlib
    path=tmp_path/'owned.pdf';path.write_bytes(b'%PDF-1.7\nowned scan profile\n%%EOF\n')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(pdf,'INDEXED_COUNTY_REPORT_SHA256',frozenset({digest}) if qualified else frozenset())
    indexed=[];walk=[]
    def select(path):indexed.append(path);return [1,2]
    class EnteredTableWalk(RuntimeError):pass
    def extract(path,*,pages=None):walk.append(pages);raise EnteredTableWalk()
    monkeypatch.setattr(pdf,'indexed_county_table_pages',select)
    monkeypatch.setattr(pdf,'extract_all_tables',extract)
    with pytest.raises(EnteredTableWalk):pdf.CoBQuarterlyReportParser(path).parse()
    assert bool(indexed) is qualified
    assert walk==[[1,2] if qualified else None]
