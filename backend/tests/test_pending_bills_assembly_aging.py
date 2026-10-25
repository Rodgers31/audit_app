"""Table 2.12 cells are genuine; acquisition envelopes in tests are synthetic."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from seeding.domains.pending_bills import aging
from test_pending_bills_aging_persistence import payables_entries, synthetic_tables

SCOPE = 'county_assembly'

def fixture():
    return json.loads((Path(__file__).parent/'fixtures/cbirr_2025_26_assembly_aging.json').read_text())

def entries():
    from seeding.pdf_parsers import county_payables_rows, classify_payables_row
    from fixtures.cbirr_county_payables_tables import FY2526_TABLE_PAGES
    rows, _ = county_payables_rows(FY2526_TABLE_PAGES)
    result=[]
    for row in rows.values():
        entry=classify_payables_row(row)
        entry.update(as_at=aging.AS_AT, table='Table 2.10')
        result.append(entry)
    return result

def parsed(tables=None, stock=None):
    return aging.parse_aging_tables(fixture()['tables'] if tables is None else tables,
                                    entries() if stock is None else stock, scope=SCOPE)

def test_executive_control_still_keeps_nandi_unavailable():
    result=aging.parse_aging_tables(synthetic_tables(),payables_entries())
    assert result['scope']=='county_executive'
    assert next(r for r in result['rows'] if r['county']=='Nandi')['amounts']==[None]*5

def test_genuine_assembly_source_bands_missing_and_printed_zero():
    result=parsed()
    assert result['version']==2 and result['scope']==SCOPE and result['table']=='Table 2.12'
    assert result['summary']['amounts']==['2481980000.00','1780020000.00','639070000.00','1402370000.00','6321350000.00']
    rows={r['county']:r for r in result['rows']}
    assert len(rows)==47
    assert rows['Narok']['raw_cells']==['','','','','17.92']
    assert rows['Narok']['amounts']==[None]*4+['17920000.00']
    assert rows['Kirinyaga']['amounts']==[None]*4+['0.00']
    assert rows['Nandi']['amounts']==['0.00']*5
    assert rows['Uasin Gishu']['amounts']==[None]*4+['0.00']
    assert any(n['code']=='bands_differ_from_printed_total' for n in result['summary']['reader_notes'])
    assert any(n['code']=='cob_marked_inconsistent' for n in rows['Kisumu']['reader_notes'])
    assert all(c['status']=='not_reconciled_missing_cells' for c in result['reconciliation'][:4])
    aging.validate_cohort(result)

@pytest.mark.parametrize('mutation',['missing_page','duplicate','executive','units','currency','bands','foreign_county','wrong_page'])
def test_source_boundaries(mutation):
    tables=deepcopy(fixture()['tables'])
    if mutation=='missing_page': tables=tables[:1]
    elif mutation=='duplicate': tables[1][1].append(tables[0][1][2])
    elif mutation=='executive': tables=synthetic_tables()
    elif mutation=='units': tables[0][1][0][5]='Total (Millions)'
    elif mutation=='currency': tables[1][1][0][5]='Total (USD Millions)'
    elif mutation=='bands': tables[0][1][1][1]='0-30d'
    elif mutation=='foreign_county': tables[0][1][2][0]='Unknown County'
    elif mutation=='wrong_page': tables[1][0]=53
    with pytest.raises(ValueError): parsed(tables)

@pytest.mark.parametrize('bad',[True,False,-1,'NaN','Infinity','-Infinity',{},[],'1,23.00'])
def test_hostile_assembly_cells(bad):
    tables=deepcopy(fixture()['tables']); tables[0][1][2][1]=bad
    with pytest.raises(ValueError): parsed(tables)


def source_pair(tmp_path, monkeypatch):
    """Genuine Table 2.12 cells, INERT acquired bytes; never live qualification."""
    from test_pending_bills_aging_persistence import source_input
    from seeding.parse_cache import parse_with_cache
    from seeding.pdf_evidence import bind_parse_receipt
    from services.response_receipts import copy_receipt
    records, executive = source_input(tmp_path, monkeypatch)
    cohort=parsed()
    fresh=parse_with_cache(tmp_path/'input.pdf', cache_dir=tmp_path/'assembly-parse',
                           kind='b86-inert-source-derived-assembly',parse_fn=lambda:[cohort],enabled=False)
    import httpx
    from services.response_receipts import capture_response
    from services.receipt_store import LocalReceiptStore
    from test_pending_bills_aging_persistence import URL
    receipt=capture_response(httpx.Response(200,content=(tmp_path/'input.pdf').read_bytes(),
        headers={'content-type':'application/pdf'},request=httpx.Request('GET',URL)),
        LocalReceiptStore(tmp_path/'assembly-receipts'),source_kind='pdf')
    receipt=copy_receipt(receipt,parser_version='b86-inert-assembly')
    assembly=aging.prepare_aging(fresh,bind_parse_receipt(receipt,fresh))
    return records, executive, assembly


def write_pair(db,records,executive,assembly,**kwargs):
    from test_pending_bills_aging_persistence import write
    return write(db,records,executive,assembly_aging=assembly,**kwargs)


def test_both_source_cohorts_replay_api_and_history(client,db_session,seed_country,tmp_path,monkeypatch):
    from models import Extraction,SourceDocument
    from services.pending_bills_aging import aging_observations
    from test_pending_bills_aging_persistence import populate_counties
    populate_counties(db_session,seed_country.id)
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    assert write_pair(db_session,records,executive,assembly)==(46,0)
    before=db_session.query(Extraction).count()
    assert write_pair(db_session,records,executive,assembly)==(0,46)
    assert db_session.query(Extraction).count()==before
    result=client.get('/api/v1/pending-bills/summary').json()
    assert result['aging_buckets'] is None
    assert result['aging_observations'][SCOPE]['reported_total']==6321350000
    assert result['aging_observations'][SCOPE]['chart_supported'] is False
    assert result['aging_observations']['county_executive']['reported_total']==460000000
    assert result['aging_observations']['combined']['buckets'] is None
    county=client.get('/api/v1/pending-bills/counties/narok').json()
    assert [b['amount'] for b in county['aging_observations'][SCOPE]['buckets']]==[None]*4
    assert county['aging_observations'][SCOPE]['reported_total']==17920000
    assert county['aging_observations'][SCOPE]['chart_supported'] is False
    # An ordinary stock write clears both pointers but retains history.
    write_pair(db_session,records,None,None)
    assert aging_observations(db_session,as_at=aging.AS_AT)[SCOPE]['status']=='unavailable'
    assert db_session.query(Extraction).count()==before
    assert db_session.query(SourceDocument).one().meta['pending_bills_assembly_aging_v2'] is None


@pytest.mark.parametrize('change',['serialized','late_cell','wrong_population','wrong_fy','empty_stock','wrong_publication','filtered_empty'])
def test_refused_assembly_leaves_no_effect(db_session,seed_country,tmp_path,monkeypatch,change):
    from models import Extraction,SourceDocument,Loan
    from test_pending_bills_aging_persistence import populate_counties
    populate_counties(db_session,seed_country.id)
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    kwargs={}
    if change=='serialized': assembly=dict(assembly)
    elif change=='late_cell': assembly['rows'][-1]['source_evidence'][0]['value']='123'
    elif change=='wrong_population': assembly=executive
    elif change=='wrong_fy': records[0].fiscal_year='FY2024/25'
    elif change=='empty_stock': records=[]
    elif change=='wrong_publication': kwargs['publication']='unsupported'
    elif change=='filtered_empty':
        for r in records: r.entity_type='ministry';r.category='ministry'
    with pytest.raises(ValueError): write_pair(db_session,records,executive,assembly,**kwargs)
    assert db_session.query(Loan).count()==db_session.query(SourceDocument).count()==db_session.query(Extraction).count()==0


def test_assembly_summary_read_has_bounded_queries_without_source_io(db_session,seed_country,tmp_path,monkeypatch):
    from sqlalchemy import event
    from services.receipt_store import LocalReceiptStore
    from services.pending_bills_aging import aging_observations
    from test_pending_bills_aging_persistence import populate_counties
    populate_counties(db_session,seed_country.id)
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    write_pair(db_session,records,executive,assembly)
    def refuse(*a,**k): raise AssertionError('source I/O on page request')
    monkeypatch.setattr(LocalReceiptStore,'read',refuse)
    queries=[]
    def query(*args): queries.append(args[2])
    event.listen(db_session.bind,'before_cursor_execute',query)
    try: result=aging_observations(db_session,as_at=aging.AS_AT)
    finally: event.remove(db_session.bind,'before_cursor_execute',query)
    assert result[SCOPE]['reported_total']==6321350000
    assert len(queries)<=5

@pytest.mark.parametrize('assembly_flag',[None,'false','TRUE','true'])
@pytest.mark.parametrize('executive_flag',['false','true'])
def test_fetcher_assembly_flag_shares_one_download_and_fresh_parse(tmp_path,monkeypatch,assembly_flag,executive_flag):
    from types import SimpleNamespace
    from hashlib import sha256
    import httpx
    from seeding import cob_cbirr,pdf_evidence,pdf_parsers
    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher
    from services.response_receipts import capture_response,copy_receipt
    from services.receipt_store import LocalReceiptStore
    from seeding.domains.counties_budget import fetcher as budget_fetcher
    body=b'%PDF-INERT-B86-FETCHER'
    path=tmp_path/'shared.pdf';path.write_bytes(body)
    monkeypatch.setattr(aging,'ARTIFACT_SHA256',sha256(body).hexdigest())
    stock=entries()
    for entry in stock: entry['status']='reported'
    class StockParser:
        def __init__(self,path): pass
        def parse(self): return stock
    opens=[]
    def parse_scopes(path,entries,scopes):
        opens.append(scopes)
        return [aging.parse_aging_tables(fixture()['tables'] if scope==SCOPE else synthetic_tables(),entries,scope=scope) for scope in scopes]
    class ExecutiveParser:
        def __init__(self,path,entries): self.path=path;self.entries=entries
        def parse(self): return parse_scopes(self.path,self.entries,['county_executive'])
    url='https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482'
    receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'application/pdf'},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path/'receipts'),source_kind='pdf')
    downloads=[]
    def download(*args): downloads.append(args[1]);return SimpleNamespace(path=path)
    monkeypatch.setattr(cob_cbirr,'download_cbirr',download)
    monkeypatch.setattr(pdf_parsers,'CbirrYearEndPayablesParser',StockParser)
    monkeypatch.setattr(aging,'_parse_pdf_scopes',parse_scopes)
    monkeypatch.setattr(aging,'ExecutiveAgingParser',ExecutiveParser)
    monkeypatch.setattr(pdf_evidence,'receipt_for_pdf',lambda *a:copy_receipt(receipt,parser_version='b86-inert-fetcher'))
    monkeypatch.setattr(fetcher,'year_end_cbirr_links',lambda _: [url])
    monkeypatch.setattr(fetcher,'county_payables_payload',lambda *a,**k:{'stock':True})
    monkeypatch.setattr(budget_fetcher,'_pdf_stack_versions',lambda:'inert')
    monkeypatch.setenv('SEED_PENDING_BILLS_AGING_ENABLED',executive_flag)
    if assembly_flag is None: monkeypatch.delenv('SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED',raising=False)
    else: monkeypatch.setenv('SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED',assembly_flag)
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path,live_pdf_fetch_enabled=True,parse_cache_enabled=True)
    client=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(text='inert listing'))
    result=fetcher.fetch_county_payables_payload(client,settings)
    assert downloads==[url]
    expected=(['county_executive'] if executive_flag=='true' else [])+([SCOPE] if assembly_flag=='true' else [])
    assert opens==([expected] if expected else [])
    assert ('assembly_aging' in result)==(assembly_flag=='true')
    assert ('aging' in result)==(executive_flag=='true')
    for key in ['aging','assembly_aging']:
        if key in result: aging.require_intact_aging(result[key])

@pytest.mark.parametrize('change',['missing_notes','none_notes','bad_notes','missing_reconciliation','bad_reconciliation'])
def test_malformed_public_cohort_is_structured_absence(db_session,seed_country,tmp_path,monkeypatch,change):
    from models import Extraction,SourceDocument
    from services.pending_bills_aging import ASSEMBLY_EXTRACTOR
    from test_pending_bills_aging_persistence import populate_counties
    populate_counties(db_session,seed_country.id)
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    write_pair(db_session,records,None,assembly)
    doc=db_session.query(SourceDocument).one()
    retained=db_session.query(Extraction).filter(Extraction.extractor==ASSEMBLY_EXTRACTOR).one()
    bad=deepcopy(retained.extracted_json)
    if change=='missing_notes': bad['summary'].pop('reader_notes')
    elif change=='none_notes': bad['rows'][0]['reader_notes']=None
    elif change=='bad_notes': bad['summary']['reader_notes']=[True]
    elif change=='missing_reconciliation': bad.pop('reconciliation')
    else: bad['reconciliation']={}
    ref=deepcopy(doc.meta['pending_bills_assembly_aging_v2'])
    ref['fingerprint']=aging.cohort_fingerprint(bad)
    candidate=Extraction(source_document_id=doc.id,extractor=ASSEMBLY_EXTRACTOR,extracted_json=bad)
    result=aging.public_observation(db_session,doc,candidate,ref,scope=SCOPE)
    assert result['status']=='unavailable'
