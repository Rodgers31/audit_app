"""Owned offline producer/CLI/lineage/dispatch controls; finding parser is inert.

Actual PDF bytes, acquisition capabilities, fetch-document persistence, native
authority, per-document commits, CLI finalization and report dispatch are real.
Only discovery/download I/O and finding extraction/loading are fixture ports.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from models import Country,DocumentStatus,DocumentType,Extraction,IngestionJob,IngestionStatus,SourceDocument
from seeding import cli,oag_discovery
import seeding.domains.audits as producer
from seeding.config import SeedingSettings
from seeding.domains.audits.writer import PersistenceStats
from seeding.native_report_authority import capture_pdf_report,persist_native_report
from seeding.native_report_observations import read_native_report_record_ids,read_native_report_observation
from seeding.generation_dispatch import dispatch_committed_report_generation
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from seeding.types import DomainRunContext
from seeding.source_observations import SourceObservationUnavailable
from test_b83_generation_postgres import pg,no_publication
from test_b86_native_postgres import enable


def pdf(title,day):
    commands=[]
    for y,value in [(810,title),(790,'Publication date: '+day if day else 'Signed by the Auditor-General')]:
        value=value.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        commands.append(f'BT /F1 8 Tf 20 {y} Td ({value}) Tj ET')
    stream='\n'.join(commands).encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 700 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    body=bytearray(b'%PDF-1.4\n');offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(body));body.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(body);body.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(body)


def document(name='TEST MINISTRY',year=2025,day='2025-07-10',suffix='',combined=False):
    heading=(f'REPORT OF THE AUDITOR-GENERAL FOR THE COUNTY GOVERNMENTS FOR THE YEAR {year-1}/{year} VOLUME I COUNTY EXECUTIVES' if combined
        else f'REPORT OF THE AUDITOR-GENERAL ON {name} FOR THE YEAR ENDED 30 JUNE {year}')
    filename=(f'COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-{year-1}-{year}.pdf' if combined
        else f'national-government-{year-1}-{year}-{name.lower().replace(" ","-")}{suffix}.pdf')
    return 'https://www.oagkenya.go.ke/wp-content/uploads/'+filename,pdf(heading,day)


def install(monkeypatch,tmp_path,documents,*,already=False):
    store=LocalReceiptStore(tmp_path/'receipts')
    class Client:
        receipt_store=store
        receipts={}
        def download_receipt(self,url):return self.receipts.get(url)
    client=Client()
    @contextmanager
    def http(settings):yield client
    def download(owner,url,**kw):
        body=documents[url]
        receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'application/pdf'},request=httpx.Request('GET',url)),store,source_kind='pdf')
        client.receipts[url]=receipt
        path=tmp_path/(hashlib.sha256(url.encode()).hexdigest()+'.pdf');path.write_bytes(body);return path
    def parser(db,doc,settings):
        ext=Extraction(source_document_id=doc.id,page_number=1,extractor='oag_county_volume' if 'COUNTY-GOVERNMENTS' in doc.url else 'oag_blue_book',confidence=.9,extracted_json={'schema':'owned_inert_finding_parser'})
        db.add(ext);db.flush()
        return {'created':0 if already else 1,'skipped':1 if already else 0,'reason':'already_extracted' if already else 'owned_new','fresh_extraction_ids':[ext.id]}
    monkeypatch.setattr(producer,'create_http_client',http)
    monkeypatch.setattr('seeding.fetch_documents.get_or_download_pdf',download)
    monkeypatch.setattr('seeding.extractors.get_parser',lambda parser_id:parser)
    monkeypatch.setattr('seeding.domains.audits.loader.load_blue_book_extractions',lambda *a,**kw:PersistenceStats(processed=1,created=0 if already else 1,updated=1 if already else 0))
    volumes=[oag_discovery.OagDocument(url=u,fiscal_year='2024/2025',kind='executives',found_on='year_page',listed_at='https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/') for u in documents if 'COUNTY-GOVERNMENTS' in u]
    monkeypatch.setattr(oag_discovery,'discover_county_audit_documents',lambda *a,**kw:oag_discovery.CountyAuditDiscovery(listing_fiscal_years=['2024/2025'] if volumes else [],documents=volumes))
    national=[u for u in documents if 'national-government' in u]
    monkeypatch.setattr(producer,'_discovered_urls',lambda *a: (national,{'attempted_queries':1,'successful_queries':1,'failures':[],'status':'completed','candidate_count':len(national)}))


class Registry:
    def domains(self):return ['audits']
    def get(self,name):return producer.run


def run_cli(factory,monkeypatch,tmp_path):
    monkeypatch.setattr(cli,'SessionLocal',factory)
    monkeypatch.setattr(cli,'load_builtin_domains',lambda:None)
    monkeypatch.setattr(cli,'REGISTRY',Registry())
    args=argparse.Namespace(domain=['audits'],all=False,dry_run=False,since=None)
    result=cli.run_seed_command(args,SeedingSettings(cache_path=tmp_path/'cache',total_timeout_seconds=60,domain_timeout_seconds=30,audits_county_start_budget_seconds=20))
    with factory() as db:
        job=db.scalar(select(IngestionJob).where(IngestionJob.domain=='audits').order_by(IngestionJob.id.desc()))
        return result,job.id,dict(job.meta),job.status,list(job.errors)



@pytest.fixture
def audit_pg(pg,monkeypatch):
    _,engine=pg
    factory=sessionmaker(bind=engine,expire_on_commit=True)
    enable(factory,monkeypatch)
    return factory


@pytest.mark.parametrize('order',['older-first','newer-first'])
def test_audit_job_selects_latest_edition_independent_of_order(audit_pg,tmp_path,monkeypatch,order):
    old_url,old_body=document(year=2025,day='2025-07-10')
    new_url,new_body=document(year=2026,day='2026-07-10')
    old_url=old_url.replace('national-government-','national-government-'+('a-' if order=='older-first' else 'z-'))
    new_url=new_url.replace('national-government-','national-government-'+('z-' if order=='older-first' else 'a-'))
    install(monkeypatch,tmp_path,{old_url:old_body,new_url:new_body})
    code,job,meta,status,errors=run_cli(audit_pg,monkeypatch,tmp_path)
    assert code==0 and status==IngestionStatus.COMPLETED and not errors
    ids=read_native_report_record_ids(audit_pg,ingestion_id=job,domain='audits')
    assert len(ids)==1
    report=read_native_report_observation(audit_pg,record_id=ids[0],ingestion_id=job,domain='audits')['report']
    assert report['period']=='FY 2025/26' and report['published_on']=='2026-07-10'
    outcome=meta['post_commit_report_generation']
    assert outcome['state']=='completed' and outcome['baselines']==1 and outcome['drafts_created']==0 and outcome['refused']==0
    assert len(meta['native_report_records']['audits'])==2
    no_publication(audit_pg)


@pytest.mark.parametrize('case',['disjoint','mixed','missing-day','combined-scope'])
def test_audit_qualified_and_unsupported_source_scopes(audit_pg,tmp_path,monkeypatch,case):
    docs=dict([document(day=''if case=='missing-day'else'2025-07-10',combined=case=='combined-scope')])
    if case in {'disjoint','mixed'}:docs.update([document(name='OTHER MINISTRY',day=''if case=='mixed'else'2025-07-10')])
    install(monkeypatch,tmp_path,docs)
    code,job,meta,status,errors=run_cli(audit_pg,monkeypatch,tmp_path)
    assert code==0 and status==IngestionStatus.COMPLETED and not errors and meta['source_mode']=='live'
    outcome=meta['post_commit_report_generation']
    if case in {'missing-day','combined-scope'}:
        assert all(d['native_report_record_id']is None and d['native_report_authority_reason']for d in meta['documents'])
        with pytest.raises(SourceObservationUnavailable):read_native_report_record_ids(audit_pg,ingestion_id=job,domain='audits')
        assert outcome['state']=='unavailable' and outcome['processed']==0 and outcome['drafts_created']==0
    else:
        ids=read_native_report_record_ids(audit_pg,ingestion_id=job,domain='audits')
        reports=[read_native_report_observation(audit_pg,record_id=r,ingestion_id=job,domain='audits')['report']for r in ids]
        assert {r['entity']for r in reports}==({'TEST MINISTRY','OTHER MINISTRY'}if case=='disjoint'else{'TEST MINISTRY'})
        assert outcome['state']=='completed' and outcome['baselines']==len(ids) and outcome['drafts_created']==0
        replay=dispatch_committed_report_generation(audit_pg,domain='audits',ingestion_id=job,dry_run=False)
        assert replay['unchanged']==len(ids) and replay['drafts_created']==0
    no_publication(audit_pg)


def captured(tmp_path,*,year,day,url,extra=False):
    title=f'REPORT OF THE AUDITOR-GENERAL ON TEST MINISTRY FOR THE YEAR ENDED 30 JUNE {year}'
    body=pdf(title+('  'if extra else''),day)
    path=tmp_path/(hashlib.sha256(body).hexdigest()+'.pdf');path.write_bytes(body)
    receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'application/pdf'},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path/'receipts'),source_kind='pdf')
    authority,reason=capture_pdf_report(path,receipt,domain='audits')
    assert authority is not None,reason
    return authority,path,body


def persist_sequence(factory,tmp_path,sequence):
    refused=False
    with factory.begin() as db:
        job=IngestionJob(domain='audits',status=IngestionStatus.RUNNING,dry_run=False,started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();identity=job.id
        for url,year,day,extra in sequence:
            authority,path,body=captured(tmp_path,year=year,day=day,url=url,extra=extra)
            try:
                with db.begin_nested():
                    source=db.scalar(select(SourceDocument).where(SourceDocument.url==url))
                    if source is None:
                        source=SourceDocument(country_id=db.scalar(select(Country.id)),publisher='Office of the Auditor-General',title=url.rsplit('/',1)[-1],url=url,doc_type=DocumentType.AUDIT,fetch_date=datetime.now(timezone.utc),meta={})
                        db.add(source);db.flush()
                    source.md5=hashlib.md5(body).hexdigest();source.file_path=str(path)
                    source.status=DocumentStatus.AVAILABLE;source.content_type='application/pdf';source.http_status=200
                    persist_native_report(db,source,authority,context=DomainRunContext(None,False,identity),domain='audits')
            except ValueError:
                refused=True
        job=db.get(IngestionJob,identity);job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
    return identity,refused


@pytest.mark.parametrize('reverse',[False,True])
def test_same_source_url_cannot_leave_an_inaccessible_selected_head(audit_pg,tmp_path,reverse):
    url='https://www.oagkenya.go.ke/national-government-owned-report.pdf'
    sequence=[(url,2025,'2025-07-10',False),(url,2026,'2026-07-10',False)]
    if reverse:sequence.reverse()
    job,_=persist_sequence(audit_pg,tmp_path,sequence)
    try:
        ids=read_native_report_record_ids(audit_pg,ingestion_id=job,domain='audits')
        assert len(ids)==1
        report=read_native_report_observation(audit_pg,record_id=ids[0],ingestion_id=job,domain='audits')['report']
    except SourceObservationUnavailable:
        assert reverse
    else:
        assert report['period']=='FY 2025/26'
    no_publication(audit_pg)


@pytest.mark.parametrize('kind',['same-release-conflict','crossed-chronology'])
def test_ambiguous_audit_editions_refuse_current_scope(audit_pg,tmp_path,kind):
    a='https://www.oagkenya.go.ke/national-government-owned-a.pdf'
    b='https://www.oagkenya.go.ke/national-government-owned-b.pdf'
    sequence=([(a,2025,'2025-07-10',False),(b,2025,'2025-07-10',True)]if kind=='same-release-conflict'
        else[(a,2025,'2026-07-20',False),(b,2026,'2026-07-10',False)])
    job,refused=persist_sequence(audit_pg,tmp_path,sequence)
    if not refused:
        with pytest.raises(SourceObservationUnavailable):read_native_report_record_ids(audit_pg,ingestion_id=job,domain='audits')
    no_publication(audit_pg)
