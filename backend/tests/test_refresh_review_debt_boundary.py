"""Narrow new writer-admission attacks using real issued transport receipts."""
import copy
from decimal import Decimal
import httpx,pytest
from sqlalchemy import select
from test_refresh_review_debt import db,freshness,run_source,snapshots,document,URL
from models import DebtTimeline,SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.debt_timeline import fetcher,parser,writer
from seeding.domains.national_debt import cbk_bulletin
from seeding.http_client import SeedingHttpClient
from services.figure_qualification import qualify_rows
from services.receipt_store import LocalReceiptStore
from services.response_receipts import persist_evidence


def capture(tmp,monkeypatch,*,domestic=840000,external=560000,total=1400000):
    tmp.mkdir(exist_ok=True)
    text=f'4.1.3 Deficit Financing and Public Debt\nShillings million\n2025/2026\nDecember {domestic} {external} {total}'
    body=b'%PDF-1.7\n'+text.encode()+b'\n%%EOF'
    monkeypatch.setattr(cbk_bulletin,'_find_public_debt_page_text',lambda _:cbk_bulletin._located_text(text,70))
    settings=SeedingSettings(_env_file=None,storage_path=tmp,cbk_statistical_bulletin_url=URL,http_cache_enabled=False,rate_limit='1000/sec')
    client=SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=body,headers={'content-type':'application/pdf'}))),receipt_store=LocalReceiptStore(tmp/'receipts'))
    base={'metadata':{},'timeline':[{'year':2025,'external':1,'domestic':2,'total':3,'gdp':None,'gdp_ratio':None}]}
    with client:payload,count=fetcher._overlay_cbk_public_debt(base,client,settings)
    assert count==1
    return parser.parse_debt_timeline_payload(payload)[0]

@pytest.mark.parametrize('bad',['metadata_only','serialized','tampered_acquisition','normalized_mismatch','bound_other_doc'])
def test_noncurrent_or_changed_cells_cannot_replace_retained_stock(db,tmp_path,monkeypatch,bad):
    _,rows,_,_=run_source(db,tmp_path/'first',monkeypatch);before=snapshots(rows)
    record=capture(tmp_path/'new',monkeypatch)
    if bad=='metadata_only':record.source_evidence=[]
    elif bad=='serialized':
        for item in record.source_evidence:item['_response_receipt']=dict(item['_response_receipt'])
    elif bad=='tampered_acquisition':
        for item in record.source_evidence:item['_response_receipt']['acquired_at']='1900-01-01T00:00:00Z'
    elif bad=='normalized_mismatch':record.total=1301
    else:
        other=document(db,url=URL,publisher='Central Bank of Kenya');other.title='Different observation binding';db.flush()
        persist_evidence(db,other,[record.source_evidence[0]])
    writer.write_debt_timeline_records(db,[record],{'refresh_components':{'debt':{'state':'live'},'gdp':{'state':'live'}}});db.commit()
    rows=list(db.scalars(select(DebtTimeline).order_by(DebtTimeline.year)))
    assert snapshots(rows)==before

def test_complete_current_new_acquisition_replaces_stock_but_not_unobserved_gdp(db,tmp_path,monkeypatch):
    _,rows,_,_=run_source(db,tmp_path/'first',monkeypatch);prior_gdp=rows[-1].gdp
    record=capture(tmp_path/'new',monkeypatch)
    writer.write_debt_timeline_records(db,[record],{});db.commit()
    row=db.scalar(select(DebtTimeline).where(DebtTimeline.year==2025));q=qualify_rows(db,'debt_timeline',[row])[row.id]
    assert row.total==Decimal('1400000000000') and row.gdp==prior_gdp and row.gdp_ratio is None
    assert all(q[m]['status']=='verified' for m in ('total','external','domestic','gdp'))

def test_three_stock_cells_must_share_one_current_acquisition(db,tmp_path,monkeypatch):
    _,rows,_,_=run_source(db,tmp_path/'first',monkeypatch);before=snapshots(rows)
    older=capture(tmp_path/'older',monkeypatch,domestic=780000,external=520000,total=1300000)
    newer=capture(tmp_path/'newer',monkeypatch)
    old_external=next(e for e in older.source_evidence if e['identity']['measure']=='external')
    newer.source_evidence=[old_external if e['identity']['measure']=='external' else e for e in newer.source_evidence]
    newer.external=older.external
    assert newer.domestic+newer.external!=newer.total
    writer.write_debt_timeline_records(db,[newer],{});db.commit()
    rows=list(db.scalars(select(DebtTimeline).order_by(DebtTimeline.year)))
    assert snapshots(rows)==before
