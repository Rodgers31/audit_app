"""PR860 independent regressions: actual extraction/reader/gates/cache, fake PDF/OCR only."""
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from decimal import Decimal

import pytest
from PIL import Image
import pdfplumber
from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fiscal_framework as ff
from seeding.domains.fiscal_summary import fetcher
from seeding import pdf_download

TITLE='Annex Table 2a: Fiscal Framework (KSh billion)'
FY='FY 2026/27'
URL='https://www.treasury.go.ke/sites/default/files/Budget-Summary-FY-2026-27.pdf'


def require(condition, detail):
    if not condition: raise AssertionError(detail)


def corpus():
    data=json.loads((Path(__file__).parent / 'fixtures/budget_summary/fy2026_27.json').read_text())
    return [data['pages'].get(str(i),'') for i in range(1,74)]


def harness(tmp_path,monkeypatch,*,partial=None,images=True,second=False,enabled=True):
    source=corpus();annex=source[62]
    state={'calls':0,'renders':0,'version':'5.5.0','error':None,'ocr_text':annex,
           'text':TITLE if partial is None else partial,'images':images,'second':second}
    fake=ModuleType('pytesseract')
    fake.get_tesseract_version=lambda:state['version']
    fake.get_languages=lambda **kw:['eng']
    def ocr(*args,**kwargs):
        state['calls']+=1
        require(kwargs.get('timeout')==20,'OCR must remain bounded to20seconds')
        if state['error'] is not None:raise state['error']
        return state['ocr_text']
    fake.image_to_string=ocr
    monkeypatch.setitem(sys.modules,'pytesseract',fake)
    class Page:
        width=612;height=792
        def __init__(self,i):self.index=i;self.page_number=i+1
        @property
        def images(self):
            return [dict(x0=30,x1=580,top=60,bottom=740)] if state['images'] and (self.index==62 or state['second'] and self.index==63) else []
        def extract_text(self):
            if self.index==62:return state['text']
            if self.index==63 and state['second']:return TITLE
            return source[self.index]
        def to_image(self,**kw):
            state['renders']+=1
            require(kw=={'resolution':300,'antialias':True},'changed OCR rendering bounds')
            return SimpleNamespace(original=Image.new('RGB',(120,160),'white'))
    class PDF:
        def __enter__(self):return SimpleNamespace(pages=[Page(i) for i in range(73)])
        def __exit__(self,*args):return False
    monkeypatch.setattr(pdfplumber,'open',lambda *a,**kw:PDF())
    pdf=tmp_path/'owned.pdf';pdf.write_bytes(b'%PDF-1.7\nownedstableOCRcachefixture\n%%EOF')
    monkeypatch.setattr(pdf_download,'get_or_download_pdf',lambda *a,**kw:pdf)
    client=SimpleNamespace(get=lambda *a,**kw:SimpleNamespace(text=f'<a href="{URL}">Budget Summary</a>'))
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',parse_cache_enabled=enabled)
    return SimpleNamespace(state=state,pdf=pdf,client=client,settings=settings,annex=annex,
                           extract=lambda:ff.extract_page_texts(pdf),fetch=lambda:fetcher._fetch_budget_summary_editions(client,settings))


def split_records(records):
    edition=ff.read_edition([r['text'] for r in records],fiscal_year=FY)
    return ff.split_for_fiscal_year(edition,FY,known_ordinary_revenue=2985.7)


def full_apply(editions):
    require(len(editions)==1,'needexactonequalifiededition')
    split=ff.split_for_fiscal_year(editions[0][1],FY,known_ordinary_revenue=2985.7)
    require(split.values['expenditure']==Decimal('4785.2'),'unexpectedfullfinancialvalue')
    payload,status=fetcher._apply_fiscal_framework({'fiscal_years':[{'fiscal_year':FY}]},editions)
    require(payload['fiscal_years'][0].get('fiscal_framework') is not None,'fullfinancialapplicationdidnotexecute')
    return {'status':status,'expenditure':str(split.values['expenditure']),'checks':split.checks}


@pytest.mark.parametrize('kind',['one_complete_row','one_short_row'])
def test_partial_image_text_must_try_bounded_ocr_and_reach_full_gates(tmp_path,monkeypatch,kind):
    table=corpus()[62]
    row=next(line for line in table.splitlines() if line.startswith('TOTAL REVENUE '))
    partial=TITLE+'\n'+(row if kind=='one_complete_row' else 'TOTAL REVENUE 3,629.7')
    with pytest.raises(ff.FiscalFrameworkError,match='rows_not_found'):
        ff.parse_annex_lines(partial.splitlines(),page=63)
    h=harness(tmp_path,monkeypatch,partial=partial)
    records=h.extract()
    got={'kind':kind,'ocr_calls':h.state['calls'],'record':records[62]}
    try:got['split']=str(split_records(records).values['expenditure'])
    except Exception as e:got['refusal']=str(e)
    require(h.state['calls']==1,'incompleteimageannexneverattemptedOCR')
    require(split_records(records).values['expenditure']==Decimal('4785.2'),'validrecoveryfailedfinancialgates')


def test_original_annex_title_must_survive_row_only_ocr(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch)
    h.state['ocr_text']='\n'.join(h.annex.splitlines()[1:])
    records=h.extract()
    got={'ocr_calls':h.state['calls'],'record':records[62]}
    try:got['split']=str(split_records(records).values['expenditure'])
    except Exception as e:got['refusal']=str(e)
    require(h.state['calls']==1,'OCRwasnotattempted')
    require(TITLE in records[62]['text'],'knownoriginalannexheadingwasdiscarded')
    require(split_records(records).values['expenditure']==Decimal('4785.2'),'row-onlyOCRcannotreachfinancialgate')


def test_original_actual_column_heading_must_survive_ocr_rows(tmp_path,monkeypatch):
    table=corpus()[62]
    heading=next(x for x in table.splitlines() if x.startswith('Act. Prel. Budget'))
    h=harness(tmp_path,monkeypatch,partial=TITLE+'\n'+heading)
    h.state['ocr_text']='\n'.join(x for x in h.annex.splitlines() if not x.startswith('Act. Prel. Budget'))
    records=h.extract()
    edition=ff.read_edition([r['text'] for r in records],fiscal_year=FY)
    split=ff.split_for_fiscal_year(edition,'FY 2023/24',known_ordinary_revenue=2288.9)
    require(split.column_label=='Actual','originalActualcolumnqualificationwasdiscarded')


@pytest.mark.parametrize('failure',['timeout','empty','incomplete'])
def test_unavailable_ocr_cache_must_retry_after_same_engine_recovers(tmp_path,monkeypatch,failure):
    h=harness(tmp_path,monkeypatch)
    if failure=='timeout':h.state['error']=RuntimeError('ownedOCRtimeout')
    elif failure=='empty':h.state['ocr_text']=''
    else:h.state['ocr_text']='UnrecognizedincompleteOCRrows'
    first,firstfacts=h.fetch();first_calls=h.state['calls']
    require(first==[] and first_calls==1,'firstfailurefixturewasnotactuallyexercised')
    h.state['error']=None;h.state['ocr_text']=h.annex
    second,secondfacts=h.fetch();second_calls=h.state['calls']
    h.settings.parse_cache_enabled=False
    fresh,freshfacts=h.fetch();fresh_application=full_apply(fresh)
    require(len(second)==1 and second_calls==2,'cachedunavailableOCRmaskedrecoverywithoutretry')
    full_apply(second)


def test_same_unavailable_ocr_is_retried_each_invocation(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch);h.state['error']=RuntimeError('ownedpersistenttimeout')
    first,_=h.fetch();second,facts=h.fetch()
    require(first==[] and second==[],'failedOCRmustnotqualify')
    require(h.state['calls']==2,'unavailablecachedresultpermanentlysuppressessecondboundedattempt')


def test_successful_ocr_cache_hit_keeps_value_and_avoids_second_ocr(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch)
    first,_=h.fetch();full_apply(first)
    h.state['error']=RuntimeError('shouldnotneedengineforvalidmatchingcache')
    second,_=h.fetch();full_apply(second)
    require(h.state['calls']==1,'validmatchingOCRcachewasnotreused')


@pytest.mark.parametrize('changed',['pdf','engine'])
def test_changed_identity_invalidates_previously_unavailable_cache(tmp_path,monkeypatch,changed):
    h=harness(tmp_path,monkeypatch);h.state['error']=RuntimeError('ownedfirsttimeout')
    first,_=h.fetch();require(first==[],'firsttimeoutdidnotrefuse')
    h.state['error']=None
    if changed=='pdf':h.pdf.write_bytes(h.pdf.read_bytes()+b'changedsource')
    else:h.state['version']='5.5.1'
    second,_=h.fetch();full_apply(second)
    require(h.state['calls']==2,'changedidentitydidnotretry')


def test_complete_text_layer_never_needs_ocr_even_with_image(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch,partial=corpus()[62]);h.state['error']=RuntimeError('mustnotOCRvalidtext')
    require(split_records(h.extract()).values['expenditure']==Decimal('4785.2'),'completeTextrefused')
    require(h.state['calls']==0,'unnecessaryOCR')


def test_no_image_partial_text_is_still_a_refusal(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch,partial=TITLE+'\nTOTAL REVENUE 3,629.7',images=False)
    with pytest.raises(ff.FiscalFrameworkError):split_records(h.extract())
    require(h.state['calls']==0,'OCRusedwithouttitledimage')


def test_two_image_annexes_refuse_without_choosing_one(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch,second=True)
    with pytest.raises(ff.FiscalFrameworkError,match='ambiguous_annex'):split_records(h.extract())
    require(h.state['calls']==0,'ambiguouspagewasOCRed')


def test_ocr_text_success_cannot_bypass_arithmetic(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch)
    h.state['ocr_text']=h.annex.replace('3,538.7','9,999.9')
    with pytest.raises(ff.FiscalFrameworkError,match='does_not_reconcile'):split_records(h.extract())
    require(h.state['calls']==1,'actualOCRportwasnotexercised')


def test_no_cache_retries_and_recovers_same_ocr_engine(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch,enabled=False);h.state['error']=RuntimeError('ownedtimeout')
    first,_=h.fetch();require(first==[],'firsttimeoutdidnotrefuse')
    h.state['error']=None
    second,_=h.fetch();full_apply(second)
    require(h.state['calls']==2,'disabledcachedidnotretry')
