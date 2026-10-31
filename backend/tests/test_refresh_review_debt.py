"""Real producer→writer→qualification/API fallback attacks, entirely local.
Only PDF page-text extraction is controlled. Captured receipt and seal paths run.
"""
import asyncio,copy,inspect,json
from datetime import datetime,timezone
from decimal import Decimal
import httpx,pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Country,DebtTimeline,DocumentType,Extraction,SourceDocument
from seeding.config import SeedingSettings
from seeding.domains import debt_timeline as domain
from seeding.domains.debt_timeline import writer
from seeding.domains.national_debt import cbk_bulletin
from seeding.freshness import get,reset
from seeding.http_client import SeedingHttpClient
from seeding.types import DomainRunContext
from services.figure_qualification import qualify_rows
from services.receipt_store import LocalReceiptStore

URL='https://www.centralbank.go.ke/uploads/statistical_bulletin/standards-retained.pdf'
GENERIC='https://www.centralbank.go.ke/statistics/government-finance-statistics/'
PUB='Central Bank of Kenya / National Treasury'
TITLE='Historical declared CBK series'
TEXT='4.1.3 Deficit Financing and Public Debt\nShillings million\n2024/2025\nDecember 720000 480000 1200000\n2025/2026\nDecember 780000 520000 1300000'
@compiles(JSONB,'sqlite')
def jsonb_sqlite(element,compiler,**kw):return 'JSON'
@pytest.fixture
def db(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'owned.sqlite'))
    for model in (Country,SourceDocument,Extraction,DebtTimeline):model.__table__.create(engine)
    with Session(engine) as db:
        db.add(Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en'));db.commit();yield db
    engine.dispose()
@pytest.fixture(autouse=True)
def freshness():
    reset('debt_timeline');yield;reset('debt_timeline')

def run_source(db,tmp,monkeypatch,*,cbk=True,gdp=True,values=None):
    tmp.mkdir(exist_ok=True)
    base={'metadata':{'source':TITLE},'timeline':[
        {'year':year,'external':400,'domestic':600,'total':1000,'gdp':5000,'gdp_ratio':20,'source':TITLE} for year in (2024,2025)]}
    path=tmp/'base.json';path.write_text(json.dumps(base))
    settings=SeedingSettings(_env_file=None,debt_timeline_dataset_url=path.as_uri(),cbk_statistical_bulletin_url=URL,
        storage_path=tmp,http_cache_enabled=False,enrich_with_worldbank=True,rate_limit='1000/sec',max_retries=1,retry_backoff=.001)
    values={2024:10_000_000_000_000,2025:10_000_000_000_000} if values is None else values
    def transport(req):
        if str(req.url)==URL:
            return httpx.Response(200 if cbk else 503,content=b'%PDF-1.7\nowned source-shaped decoder fixture\n%%EOF',headers={'content-type':'application/pdf'})
        assert req.url.host=='api.worldbank.org'
        rows=[{'indicator':{'id':'NY.GDP.MKTP.CN'},'country':{'id':'KE'},'countryiso3code':'KEN','date':str(year),'value':value,'unit':''} for year,value in values.items()]
        return httpx.Response(200 if gdp else 503,json=[{'page':1,'pages':1,'total':len(rows)},rows])
    monkeypatch.setattr(cbk_bulletin,'_find_public_debt_page_text',lambda _:cbk_bulletin._located_text(TEXT,69))
    client=SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(transport)),receipt_store=LocalReceiptStore(tmp/'receipts'))
    monkeypatch.setattr(domain,'create_http_client',lambda _:client)
    reset('debt_timeline');result=domain.run(db,settings,DomainRunContext(None,False));db.commit()
    assert not result.errors,result.errors
    rows=list(db.scalars(select(DebtTimeline).order_by(DebtTimeline.year)));q=qualify_rows(db,'debt_timeline',rows)
    return result,rows,q,copy.deepcopy(get('debt_timeline'))

def snapshots(rows):
    return {r.year:{'external':r.external,'domestic':r.domestic,'total':r.total,'gdp':r.gdp,'ratio':r.gdp_ratio,'source_id':r.source_document_id,'meta':copy.deepcopy(r.meta)} for r in rows}
def stocks(row):return [copy.deepcopy(e) for e in row.meta['source_evidence'] if e['identity']['measure'] in ('total','external','domestic')]
def gdp_evidence(row):return [copy.deepcopy(e) for e in row.meta['source_evidence'] if e['identity']['measure']=='gdp']
def api(db):
    import main
    return asyncio.run(inspect.unwrap(main.get_debt_timeline)(db=db))

def document(db,*,url=GENERIC,publisher=PUB,country='KEN',kind=DocumentType.REPORT):
    c=db.scalar(select(Country).where(Country.iso_code==country))
    if not c:c=Country(iso_code=country,name=country,currency='KES',timezone='Africa/Nairobi',default_locale='en');db.add(c);db.flush()
    d=SourceDocument(country_id=c.id,title=TITLE,publisher=publisher,url=url,doc_type=kind,fetch_date=datetime.now(timezone.utc));db.add(d);db.commit();return d

@pytest.mark.parametrize('wrong',['url','publisher'])
def test_fallback_document_requires_exact_registered_identity(db,wrong):
    old=document(db,**({'url':'https://unrelated.invalid/report.pdf'} if wrong=='url' else {'publisher':'Unrelated publisher'}))
    before=(old.url,old.publisher,old.country_id)
    selected=writer._get_or_create_source_document(db,{},title=TITLE)
    assert selected.id!=old.id
    assert selected.url==GENERIC and selected.publisher==PUB
    assert (old.url,old.publisher,old.country_id)==before

def test_exact_fallback_identity_is_reused(db):
    existing=document(db)
    assert writer._get_or_create_source_document(db,{},title=TITLE).id==existing.id

@pytest.mark.parametrize('wrong',['country','lane'])
def test_fallback_country_and_document_lane_remain_distinct(db,wrong):
    old=document(db,**({'country':'UGA'} if wrong=='country' else {'kind':DocumentType.BUDGET}))
    assert writer._get_or_create_source_document(db,{},title=TITLE).id!=old.id

def test_full_current_sources_still_write_genuinely_verified_rows(db,tmp_path,monkeypatch):
    result,rows,q,state=run_source(db,tmp_path/'initial',monkeypatch)
    assert result.items_created==2 and state['mode']=='live'
    assert [r.total for r in rows]==[Decimal('1200000000000'),Decimal('1300000000000')]
    assert all(q[r.id][m]['status']=='verified' for r in rows for m in ('total','external','domestic','gdp','gdp_ratio'))
    assert api(db)['timeline'][-1]['qualifications']['gdp_ratio']['status']=='verified'

def test_gdp_only_source_refresh_is_partial_not_fixture_only(db,tmp_path,monkeypatch):
    result,rows,q,state=run_source(db,tmp_path/'gdp_only',monkeypatch,cbk=False)
    assert result.metadata['refresh_components']['gdp']['state']=='live'
    assert result.metadata['refresh_components']['debt']['state']=='unavailable'
    assert state['mode']=='partial'

def test_fallback_cannot_replace_existing_observed_stocks_source_or_receipts(db,tmp_path,monkeypatch):
    _,rows,q,_=run_source(db,tmp_path/'first',monkeypatch);before=snapshots(rows);proof={r.year:stocks(r) for r in rows}
    assert all(q[r.id]['total']['status']=='verified' for r in rows)
    _,rows,q,_=run_source(db,tmp_path/'fallback',monkeypatch,cbk=False,values={2024:15_000_000_000_000,2025:15_000_000_000_000})
    assert all((r.external,r.domestic,r.total,r.source_document_id)==(before[r.year]['external'],before[r.year]['domestic'],before[r.year]['total'],before[r.year]['source_id']) for r in rows)
    assert all(stocks(r)==proof[r.year] and q[r.id]['total']['status']=='verified' for r in rows)
    body=api(db);assert body['timeline'][-1]['total']==1_300_000_000_000 and body['timeline'][-1]['qualifications']['total']['status']=='verified'

def test_gdp_only_ratio_uses_retained_observed_stock_not_fixture_stock(db,tmp_path,monkeypatch):
    run_source(db,tmp_path/'first',monkeypatch)
    _,rows,q,_=run_source(db,tmp_path/'fallback',monkeypatch,cbk=False,values={2024:15_000_000_000_000,2025:15_000_000_000_000})
    assert rows[-1].gdp==Decimal('15000000000000')
    assert rows[-1].gdp_ratio==Decimal('8.7')
    assert q[rows[-1].id]['gdp_ratio']['status']=='verified'
    assert api(db)['timeline'][-1]['gdp_ratio']==8.7

def test_no_current_sources_does_not_downgrade_existing_observed_data(db,tmp_path,monkeypatch):
    _,rows,_,_=run_source(db,tmp_path/'first',monkeypatch);before=snapshots(rows)
    _,rows,q,state=run_source(db,tmp_path/'none',monkeypatch,cbk=False,gdp=False)
    assert state['mode']!='live'
    assert snapshots(rows)==before
    assert all(q[r.id]['total']['status']=='verified' and q[r.id]['gdp']['status']=='verified' for r in rows)

def test_partial_gdp_keeps_missing_year_observation_and_its_receipt(db,tmp_path,monkeypatch):
    _,rows,_,_=run_source(db,tmp_path/'first',monkeypatch);before=snapshots(rows);proof=gdp_evidence(rows[0])
    _,rows,q,_=run_source(db,tmp_path/'partial',monkeypatch,cbk=False,values={2025:15_000_000_000_000})
    assert rows[0].gdp==before[2024]['gdp']
    assert gdp_evidence(rows[0])==proof and q[rows[0].id]['gdp']['status']=='verified'
    assert rows[-1].gdp_ratio==Decimal('8.7')

def test_extra_worldbank_year_cannot_manufacture_a_new_debt_stock_year(db,tmp_path,monkeypatch):
    _,rows,_,_=run_source(db,tmp_path/'extra',monkeypatch,values={2024:10_000_000_000_000,2025:10_000_000_000_000,2026:15_000_000_000_000})
    assert [r.year for r in rows]==[2024,2025]

def test_fixture_only_bootstrap_never_becomes_verified_stock_authority(db,tmp_path,monkeypatch):
    _,rows,q,state=run_source(db,tmp_path/'bootstrap',monkeypatch,cbk=False,gdp=False)
    assert state['mode']!='live'
    assert all(q[r.id]['total']['status']!='verified' for r in rows)
