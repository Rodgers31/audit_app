"""Owned PostgreSQL producer/commit/preview/draft checks; no provider access."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import select, func
from models import Country, SourceDocument, IngestionJob, IngestionStatus, DocumentType, Loan
from seeding.native_report_authority import capture_pdf_report, persist_native_report
from seeding.types import DomainRunContext
from seeding.source_observations import read_native_report_record_ids
from seeding.generation_dispatch import dispatch_committed_report_generation
from social.generation.preview import preview
from social.models import SocialPost
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable
from test_native_publisher_metadata import inputs, acquisition, listing, COUNTY_TITLE, COUNTY_PAGE
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import write_pending_bills
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION


def pending_write(db, authority, context, *, amount='100', year='FY2025/26', day='2026-06-30'):
    return write_pending_bills(db,[PendingBillRecord(entity_name='Mombasa County',entity_type='county',
        category='county',fiscal_year=year,total_pending=Decimal(amount),as_at=day,
        source_page=1,source_table='Synthetic stock table')],
        source_url=authority.value['document_url'] if authority is not None else COUNTY_PAGE+'?wpdmdl=16482',source_title='Owned CoB county annual report',
        publisher='Office of the Controller of Budget (OCOB)',publication=COUNTY_PENDING_BILLS_PUBLICATION,
        native_report_authority=authority,context=context)


def ingest(factory,tmp_path,*,domain='pending_bills',change=False,layout=False):
    with factory.begin() as db:
        job=IngestionJob(domain=domain,status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush()
        path,pdf,post=inputs(tmp_path,domain)
        if change:
            body=path.read_bytes().replace(b'2025/26',b'2024/25')
            path.write_bytes(body)
            pdf=acquisition(tmp_path,body,pdf['request_url'].replace('2025-26','2024-25'),'application/pdf')
            page=post['request_url'].replace('2025-26','2024-25')
            post=acquisition(tmp_path,listing(COUNTY_TITLE.replace('2025/26','2024/25'),page,16482),page,'text/html')
        if layout:
            post=acquisition(tmp_path,post._store.read(post['storage_key'])+b'<!-- layout -->',post['request_url'],'text/html')
        authority,reason=capture_pdf_report(path,pdf,domain=domain,publisher_receipt=post)
        assert authority is not None,reason
        if domain=='pending_bills':
            pending_write(db,authority,DomainRunContext(None,False,job.id),
                year='FY2024/25' if change else 'FY2025/26',day='2025-06-30' if change else '2026-06-30')
        else:
            source=SourceDocument(country_id=db.scalar(select(Country.id)),publisher='Controller of Budget',
                title='Owned national report',url=pdf['request_url'],fetch_date=datetime.now(timezone.utc),doc_type=DocumentType.REPORT,meta={})
            db.add(source);db.flush()
            persist_native_report(db,source,authority,context=DomainRunContext(None,False,job.id),domain=domain)
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
        job_id=job.id
    ids=read_native_report_record_ids(factory,ingestion_id=job_id,domain=domain)
    assert len(ids)==1
    return job_id,ids[0]


def request(job,record,domain='pending_bills',**kw):
    return dict(domain=domain,record_ids=[record],ingestion_id=job,reports=True,backfill=False,**kw)


@pytest.mark.parametrize('domain',['national_budget','pending_bills'])
def test_post_day_producer_commit_preview_and_reasoned_backfill(pg,tmp_path,monkeypatch,domain):
    from test_api_admin import make_client,key
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,domain=domain)
    assert preview(factory,request(job,record,domain))['results'][0]['status']=='baseline'
    client=make_client(engine)
    body=dict(domain=domain,record_ids=[record],ingestion_id=job,backfill=True,reason='Owned explicit source review')
    headers=key();route='/api/v1/admin/social/generation/detect-reports'
    response=client.post(route,json=body,headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['results'][0]['status']=='draft_created'
    assert client.post(route,json=body,headers=headers).json()==response.json()
    no_publication(factory)


def test_pending_silent_baseline_and_layout_replay(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    first=dispatch_committed_report_generation(factory,domain='pending_bills',ingestion_id=job,dry_run=False)
    assert first['baselines']==1 and first['drafts_created']==0,first
    job,record=ingest(factory,tmp_path,layout=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:dispatch_committed_report_generation(factory,domain='pending_bills',ingestion_id=job,dry_run=False),range(3)))
    assert all(r['unchanged']==1 and r['drafts_created']==0 for r in results),results
    with factory() as db:assert db.scalar(select(func.count()).select_from(SocialPost))==0
    no_publication(factory)


def test_pending_writer_bad_binding_rolls_back_amount_and_authority(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:
        current=db.scalar(select(Loan));before=(current.outstanding,deepcopy(db.scalar(select(SourceDocument)).meta))
        path,pdf,post=inputs(tmp_path,'pending_bills')
        authority,_=capture_pdf_report(path,pdf,domain='pending_bills',publisher_receipt=post)
        with pytest.raises(ValueError,match='edition differ'):
            pending_write(db,authority,DomainRunContext(None,False,job),amount='999',year='FY2024/25',day='2026-06-30')
        db.expire_all()
        assert (db.scalar(select(Loan)).outstanding,db.scalar(select(SourceDocument)).meta)==before
    assert preview(factory,request(job,record))['results'][0]['status']=='baseline'


def test_legacy_pending_writer_invalidates_report_authority(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:pending_write(db,None,None)
    assert preview(factory,request(job,record))['results'][0]['status']=='refused'


def test_retained_post_mutation_before_persistence_refuses(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    path,pdf,post=inputs(tmp_path,'pending_bills')
    authority,_=capture_pdf_report(path,pdf,domain='pending_bills',publisher_receipt=post)
    authority.publisher_receipt._store.read=lambda _:b'changed bytes'
    with factory.begin() as db:
        with pytest.raises(ValueError,match='Retained source bytes differ'):
            pending_write(db,authority,DomainRunContext(None,False,1))
        assert db.scalar(select(func.count()).select_from(Loan))==0


def test_pending_semantic_release_change_concurrent_dedup_and_supersession(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    old,record=ingest(factory,tmp_path,change=True)
    assert dispatch_committed_report_generation(factory,domain='pending_bills',ingestion_id=old,dry_run=False)['baselines']==1
    job,record=ingest(factory,tmp_path)
    assert preview(factory,request(job,record))['results'][0]['status']=='eligible_change'
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:dispatch_committed_report_generation(factory,domain='pending_bills',ingestion_id=job,dry_run=False),range(3)))
    assert sum(r['drafts_created'] for r in results)==1,results
    with factory() as db:
        post=db.scalar(select(SocialPost))
        assert post.editorial_state=='pending_review'
    no_publication(factory)


def test_actual_pending_domain_keeps_publisher_and_job_authority(pg,tmp_path,monkeypatch):
    from contextlib import nullcontext
    from seeding.domains import pending_bills as domain
    from seeding.domains.pending_bills.fetcher import county_payables_payload
    from seeding.config import SeedingSettings
    factory,_=pg;enable(factory,monkeypatch)
    monkeypatch.setattr(domain,'create_http_client',lambda _:nullcontext(None))
    def fetch(*_):
        path,pdf,post=inputs(tmp_path,'pending_bills')
        authority,reason=capture_pdf_report(path,pdf,domain='pending_bills',publisher_receipt=post)
        assert authority is not None,reason
        payload=county_payables_payload([dict(county='Mombasa',status='reported',
            fiscal_year='FY2025/26',as_at='2026-06-30',table='Synthetic stock',page=1,total_millions='1')],pdf['request_url'])
        payload['_native_report_authority']=authority
        return payload
    monkeypatch.setattr(domain.fetcher,'fetch_county_payables_payload',fetch)
    with factory.begin() as db:
        job=IngestionJob(domain='pending_bills',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();errors=[]
        processed,created,updated=domain._seed_counties(db,SeedingSettings(),DomainRunContext(None,False,job.id),errors)
        assert not errors,errors
        assert (processed,created,updated)==(1,1,0)
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc);job_id=job.id
    ids=read_native_report_record_ids(factory,ingestion_id=job_id,domain='pending_bills')
    assert len(ids)==1
    assert preview(factory,request(job_id,ids[0]))['results'][0]['status']=='baseline'
    no_publication(factory)


def test_pending_cli_commits_before_report_hook(pg,tmp_path,monkeypatch):
    from seeding import cli
    from seeding.config import SeedingSettings
    from seeding.registries import REGISTRY,load_builtin_domains
    from seeding.types import DomainRunResult
    from seeding import freshness
    factory,_=pg;enable(factory,monkeypatch)
    monkeypatch.setattr(cli,'SessionLocal',factory)
    load_builtin_domains()
    def handler(session,settings,context):
        path,pdf,post=inputs(tmp_path,'pending_bills')
        authority,reason=capture_pdf_report(path,pdf,domain='pending_bills',publisher_receipt=post)
        assert authority is not None,reason
        pending_write(session,authority,context)
        freshness.mark_live('pending_bills',detail='Owned synthetic native CLI report contract')
        return DomainRunResult(domain='pending_bills',items_processed=1,items_created=1)
    monkeypatch.setitem(REGISTRY._handlers,'pending_bills',handler)
    args=cli.build_parser().parse_args(['seed','--domain','pending_bills','--no-dry-run'])
    settings=SeedingSettings(log_path=tmp_path/'seed.log')
    assert cli.run_seed_command(args,settings)==0
    with factory() as db:
        job=db.scalar(select(IngestionJob).where(IngestionJob.domain=='pending_bills'))
        assert job.status==IngestionStatus.COMPLETED
        assert job.meta['post_commit_report_generation']['baselines']==1
        assert job.meta['post_commit_generation']['reason']=='financial_adapter_unavailable'
        assert job.meta['native_report_records']['pending_bills']
    no_publication(factory)
