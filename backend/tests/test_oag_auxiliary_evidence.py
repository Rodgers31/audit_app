"""Independent classifier execution on real SQLite metadata projection and native receipt writer.
No source authority is granted by these synthetic owned receipts.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Base, Country, SourceDocument, Extraction, DocumentType
from seeding.domains.audits import scope
from services.response_receipts import capture_local_bytes, copy_receipt, seal_receipt, persist_receipt, capture_response
import httpx

@compiles(JSONB, 'sqlite')
def compile_jsonb(type_, compiler, **kw):
    return 'JSON'

class Store:
    storage_scope='owned_offline_test'
    def __init__(self):self.values={}
    def put(self,body):
        import hashlib
        key=hashlib.sha256(body).hexdigest();self.values[key]=body;return key
    def read(self,key):return self.values[key]

def test_fixture_ignores_external_database_environment(monkeypatch, request):
    monkeypatch.setenv('BOUNDED_OAG_PG_URL', 'unowned-invalid-database://refused')
    session, _doc, _entry = request.getfixturevalue('world')
    assert session.get_bind().dialect.name == 'sqlite'

@pytest.fixture
def world():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine,tables=[Country.__table__,SourceDocument.__table__,Extraction.__table__])
    with Session(engine) as session:
        country=Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en')
        session.add(country);session.flush()
        entry=json.loads((Path(__file__).resolve().parents[2] / 'docs/operations/2026-11-01-oag-catalogue-acceptance/manifest.json').read_text())['deferred_sources'][0]
        doc=SourceDocument(country_id=country.id,publisher='Office of the Auditor-General',title='Owned offline source',url=entry['source_url'],md5=entry['md5'],doc_type=DocumentType.AUDIT,fetch_date=datetime.now(timezone.utc))
        session.add(doc);session.flush()
        yield session,doc,entry
    Base.metadata.drop_all(engine,tables=[Extraction.__table__,SourceDocument.__table__,Country.__table__])
    engine.dispose()

def finding(session,doc,entry):
    row=Extraction(source_document_id=doc.id,extractor='oag_county_volume',page_number=7,extracted_json=dict(schema='oag_county_volume/v1',fiscal_year=entry['fiscal_year'],volume_kind=entry['institution'],finding_text='Owned inert finding with no public authority'))
    session.add(row);session.flush();return row

def auxiliary(session,doc,kind='pdf-receipt-v1',local=True):
    store=Store()
    if local:
        receipt=capture_local_bytes(b'%PDF-1.7 owned inert fixture bytes %%EOF',store,url=doc.url)
    else:
        receipt=capture_response(httpx.Response(200,content=b'%PDF-1.7 owned inert fixture bytes %%EOF',headers={'content-type':'application/pdf'},request=httpx.Request('GET',doc.url)),store,source_kind='pdf')
    receipt=copy_receipt(receipt,parser_version='native-report-authority-v1' if kind=='native-report-authority-v1' else 'native-report-input-v1')
    seal_receipt(receipt,[])
    return persist_receipt(session,doc,receipt,extractor=kind)

@pytest.mark.parametrize('kind',['native-report-authority-v1','pdf-receipt-v1'])
@pytest.mark.parametrize('local',[True,False],ids=['historical-local-bytes','fresh-owned-http'])
def test_mixed_canonical_receipts_do_not_refuse_existing_finding(world,kind,local):
    session,doc,entry=world;finding(session,doc,entry);row=auxiliary(session,doc,kind,local)
    assert set(row.extracted_json)=={'response_receipt'}
    if local:
        assert row.extracted_json['response_receipt']['acquisition_kind']=='local_cached_bytes'
        assert row.extracted_json['response_receipt']['status'] is None
    scope.verify_extraction_evidence(session,doc,entry)

@pytest.mark.parametrize('kind',['native-report-authority-v1','pdf-receipt-v1'])
def test_receipts_alone_never_satisfy_nonempty_finding_evidence(world,kind):
    session,doc,entry=world;auxiliary(session,doc,kind)
    with pytest.raises(scope.AuditSourceScopeError):scope.verify_extraction_evidence(session,doc,entry)

@pytest.mark.parametrize('mutation',['missing','null','list','empty-object','wrong-wrapper','finding-under-aux','extra-schema','extra-binding','wrong-extractor','wrong-parser','bad-version','boolean-version','boolean-size','nonpdf-source'])
def test_malformed_or_misnamed_auxiliary_is_not_silently_ignored(world,mutation):
    session,doc,entry=world;finding(session,doc,entry);row=auxiliary(session,doc)
    value=deepcopy(row.extracted_json)
    if mutation=='missing':value={}
    elif mutation=='null':value={'response_receipt':None}
    elif mutation=='list':value={'response_receipt':[]}
    elif mutation=='empty-object':value={'response_receipt':{}}
    elif mutation=='wrong-wrapper':value={'receipt':value['response_receipt']}
    elif mutation=='finding-under-aux':value=dict(schema='oag_county_volume/v1',fiscal_year=entry['fiscal_year'],volume_kind=entry['institution'])
    elif mutation=='extra-schema':value['schema']='oag_county_volume/v1'
    elif mutation=='extra-binding':value['pdf_artifact_binding_v1']=None
    elif mutation=='wrong-extractor':row.extractor='native-report-authority-v2'
    elif mutation=='wrong-parser':value['response_receipt']['parser_version']='unexpected-parser-v9'
    elif mutation=='bad-version':value['response_receipt']['version']=2
    elif mutation=='boolean-version':value['response_receipt']['version']=True
    elif mutation=='boolean-size':value['response_receipt']['byte_size']=True
    elif mutation=='nonpdf-source':value['response_receipt']['source_kind']='api'
    row.extracted_json=value;flag_modified(row,'extracted_json');session.flush()
    with pytest.raises(scope.AuditSourceScopeError):scope.verify_extraction_evidence(session,doc,entry)

@pytest.mark.parametrize('mutation',['wrong-fy','wrong-kind','wrong-schema','wrong-extractor','present-null-binding'])
def test_auxiliary_never_masks_bad_finding(world,mutation):
    session,doc,entry=world;row=finding(session,doc,entry);auxiliary(session,doc)
    value=deepcopy(row.extracted_json)
    if mutation=='wrong-fy':value['fiscal_year']='2020/2021'
    elif mutation=='wrong-kind':value['volume_kind']='executives'
    elif mutation=='wrong-schema':value['schema']='unknown/v9'
    elif mutation=='wrong-extractor':row.extractor='pdf-receipt-v1'
    elif mutation=='present-null-binding':value['pdf_artifact_binding_v1']=None
    row.extracted_json=value;flag_modified(row,'extracted_json');session.flush()
    with pytest.raises(scope.AuditSourceScopeError):scope.verify_extraction_evidence(session,doc,entry)


def test_no_full_payload_or_receipt_transfer(world,monkeypatch):
    session,doc,entry=world;row=finding(session,doc,entry);aux=auxiliary(session,doc)
    sentinel='PRIVATE_FINDING_OR_FULL_RECEIPT_SENTINEL' * 10000
    row.extracted_json={**row.extracted_json,'finding_text':sentinel}
    aux.extracted_json={'response_receipt':{**aux.extracted_json['response_receipt'],'observations':[sentinel]}}
    session.flush(); captured=[]; execute=session.execute
    class Projection:
        def __init__(self,result):self.result=result
        def all(self):
            rows=self.result.all();captured.extend(rows);return rows
    monkeypatch.setattr(session,'execute',lambda *a,**kw:Projection(execute(*a,**kw)))
    scope.verify_extraction_evidence(session,doc,entry)
    assert len(captured)==2
    assert all(sentinel not in str(cell) for row in captured for cell in row)
    assert all(not isinstance(cell,dict) or 'response_receipt' not in cell for row in captured for cell in row)

@pytest.mark.parametrize('state',['missing','conflict'])
def test_historical_failed_retention_receipts_remain_metadata_without_authority(world,state):
    session,doc,entry=world;finding(session,doc,entry)
    receipt=capture_local_bytes(b'owned historical local bytes',None if state=='missing' else Store(),url=doc.url,claimed_receipt={'digest':'0'*64,'byte_size':0} if state=='conflict' else None)
    receipt=copy_receipt(receipt,parser_version='native-report-input-v1');seal_receipt(receipt,[])
    row=persist_receipt(session,doc,receipt,extractor='pdf-receipt-v1')
    assert row.extracted_json['response_receipt']['byte_check']['status']==state
    assert row.extracted_json['response_receipt']['status'] is None
    scope.verify_extraction_evidence(session,doc,entry)

@pytest.mark.parametrize('count',[1000,1001])
def test_auxiliary_inventory_is_bounded(world,count):
    session,doc,entry=world;finding(session,doc,entry);row=auxiliary(session,doc)
    session.add_all([Extraction(source_document_id=doc.id,extractor=row.extractor,extracted_json=deepcopy(row.extracted_json)) for _ in range(count-1)])
    session.flush()
    if count==1001:
        with pytest.raises(scope.AuditSourceScopeError):scope.verify_extraction_evidence(session,doc,entry)
    else:scope.verify_extraction_evidence(session,doc,entry)

