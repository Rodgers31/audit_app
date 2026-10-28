"""Prospective native producer -> migrated PG -> financial review contracts.

All HTTP responses, acquisition/job times and accounts are owned local fixtures.
No test labels synthetic live-job metadata as an actual production execution.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from copy import deepcopy
import httpx
import pytest
from sqlalchemy import select, func, text

from models import IngestionJob, IngestionStatus, RevenueBySource, SourceDocument, Extraction
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from seeding.generation_capabilities import capability
from seeding.generation_dispatch import dispatch_committed_generation
from services.receipt_store import LocalReceiptStore
from social.generation.preview import preview
from social.generation.models import SourceCursor, SourceEvent
from social.models import SocialPost, SocialPostRevision
from social.generation.service import consume_observation, verify_generated_revision
from social.service import SocialService, SocialError
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable as enable_reports
from test_b86_native_authority import HTML, KRA_URL


def enable(factory,monkeypatch):
    enable_reports(factory,monkeypatch)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','true')


def ingest_revenue(factory, tmp_path, monkeypatch, *, paye='560', extra=b'', complete=True):
    from seeding.domains.revenue_by_source.fetcher import _read_release, _apply_kra_live
    from seeding.domains.revenue_by_source.parser import parse_revenue_payload
    from seeding.domains.revenue_by_source.writer import persist_revenue_records
    import seeding.domains.revenue_by_source.fetcher as producer
    article=HTML.replace(b'560 Billion',f'{paye} Billion'.encode()).replace(
        b'</div>\n<div class="bottom-wrapper">',
        b'<p>Corporation Tax collected Kshs. 300 Billion.</p><p>Domestic VAT collected Kshs. 320 Billion.</p>'
        b'<p>Domestic Excise collection stood at Kshs. 70 Billion.</p><p>Customs collection stood at Kshs. 800 Billion.</p></div>\n<div class="bottom-wrapper">')+extra
    class Client:
        receipt_store=LocalReceiptStore(tmp_path/'receipts')
        def get(self,url,**kw):
            return httpx.Response(200,content=article,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    with factory.begin() as db:
        job=IngestionJob(domain='revenue_by_source',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();job_id=job.id
        release=_read_release(Client(),KRA_URL,None)
        monkeypatch.setattr(producer,'discover_kra_releases',lambda *a:([release],release.fiscal_year,release.url))
        payload,status=_apply_kra_live([],Client(),SeedingSettings())
        assert status.startswith('promoted'),status
        stats=persist_revenue_records(db,parse_revenue_payload(payload),SeedingSettings(),DomainRunContext(None,False,job_id))
        assert not stats.errors,stats.errors
        if complete:
            job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
        record=db.scalar(select(RevenueBySource.id).where(RevenueBySource.revenue_type=='PAYE'))
    return job_id,record


def request(job,record,**kw):
    return dict(domain='revenue_by_source',record_ids=[record],ingestion_id=job,reports=False,backfill=False,**kw)


def read(factory,job,record):
    assert capability('revenue_by_source').financial, 'Native financial adapter missing'
    from seeding.source_observations import read_revenue_financial_observation
    return read_revenue_financial_observation(factory,record_id=record,ingestion_id=job)


def test_actual_producer_metadata_then_existing_value_correction_reaches_one_draft(pg,tmp_path,monkeypatch):
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    from services.figure_qualification import qualify_rows
    with factory() as db:
        q=qualify_rows(db,'revenue_by_source',[db.get(RevenueBySource,record)])[record]['amount_billion_kes']
        assert q['status']=='verified',q
    before=preview(factory,request(job,record))
    assert before['results'][0]['status']=='baseline',before
    first=dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)
    assert first['baselines']>=5 and first['drafts_created']==0,first
    same,same_record=ingest_revenue(factory,tmp_path,monkeypatch,extra=b'<!-- new layout -->')
    assert same_record==record
    same_result=dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=same,dry_run=False)
    assert same_result['drafts_created']==0 and same_result['unchanged']>=5,same_result
    newer,new_record=ingest_revenue(factory,tmp_path,monkeypatch,paye='561')
    assert new_record==record
    assert preview(factory,request(newer,record))['results'][0]['status']=='eligible_change'
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=newer,dry_run=False),range(3)))
    assert sum(r['drafts_created'] for r in results)==1,results
    with factory() as db:
        posts=list(db.scalars(select(SocialPost)));assert len(posts)==1
        assert posts[0].editorial_state=='pending_review'
        revision=db.get(SocialPostRevision,posts[0].current_revision_id)
        fact=revision.evidence_snapshot['source']['facts'][0]
        assert fact['value']=='561.00' and fact['scale']=='billions' and fact['unit']=='KES'
        assert fact['published_on']=='2025-07-10'
        assert revision.evidence_snapshot['source']['financial']['record_id']==record
    from test_api_admin import make_client
    client=make_client(engine)
    response=client.get(f'/api/v1/admin/social/posts/{posts[0].id}/evidence')
    assert response.status_code==200,response.text
    assert response.json()['evidence']['source']['facts'][0]==fact
    no_publication(factory)


@pytest.mark.parametrize('broken',['missing_receipt','changed_value','missing_lineage','wrong_job','partial','running','fixture','future','scope','no_authority'])
def test_current_financial_evidence_refuses_stale_missing_partial_and_malformed(pg,tmp_path,monkeypatch,broken):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    value=read(factory,job,record)
    with factory.begin() as db:
        row=db.get(RevenueBySource,record);j=db.get(IngestionJob,job)
        if broken=='missing_receipt':
            ext_id=row.meta['source_evidence'][0]['receipt']['extraction_id']
            db.get(Extraction,ext_id).extracted_json={}
        if broken=='changed_value':row.amount_billion_kes+=1
        if broken=='missing_lineage':row.meta={k:v for k,v in row.meta.items() if k!='ingestion_job_id'}
        if broken=='wrong_job':
            db.execute(text("UPDATE revenue_by_source SET metadata=jsonb_set(metadata,'{ingestion_job_id}','true'::jsonb) WHERE id=:id"),{'id':record})
        if broken=='partial':j.status=IngestionStatus.COMPLETED_WITH_ERRORS
        if broken=='running':j.status=IngestionStatus.RUNNING
        if broken=='fixture':j.meta={**j.meta,'source_mode':'fixture'}
        if broken=='future':j.finished_at=datetime(2099,1,1)
        if broken=='scope':row.fiscal_year='FY 2025/26'
        if broken=='no_authority':db.get(SourceDocument,row.source_document_id).meta={}
    assert preview(factory,request(job,record))['results'][0]['status']=='refused'
    with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
        with factory.begin() as db:consume_observation(SocialService(db),value,backfill=True)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
        assert db.scalar(select(func.count()).select_from(SourceCursor))==0
    no_publication(factory)


def test_mutated_source_after_preview_cannot_become_a_draft(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    value=read(factory,job,record)
    ingest_revenue(factory,tmp_path,monkeypatch,paye='561')
    with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
        with factory.begin() as db:consume_observation(SocialService(db),value,backfill=True)
    no_publication(factory)


def test_actual_financial_admin_backfill_and_new_key_replay_are_audited(pg,tmp_path,monkeypatch):
    from test_api_admin import make_client,key
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    client=make_client(engine)
    body=dict(domain='revenue_by_source',record_ids=[record],ingestion_id=job,backfill=True,reason='Owned reasoned financial review')
    route='/api/v1/admin/social/generation/detect';headers=key()
    result=client.post(route,json=body,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['results'][0]['status']=='draft_created'
    assert client.post(route,json=body,headers=headers).json()==result.json()
    assert client.post(route,json=body,headers=key()).json()['results'][0]['status']=='unchanged'
    no_publication(factory)


def test_actual_reader_then_transaction_rollback_leaves_no_baseline_or_draft(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    value=read(factory,job,record)
    with pytest.raises(RuntimeError,match='owned rollback'):
        with factory.begin() as db:
            consume_observation(SocialService(db),value,backfill=True)
            raise RuntimeError('owned rollback')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor))==0
        assert db.scalar(select(func.count()).select_from(SourceEvent))==0
    no_publication(factory)


def test_new_native_lane_default_off_preserves_numeric_verdicts_and_report_hook(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    monkeypatch.delenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED')
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    with factory() as db:
        row=db.get(RevenueBySource,record)
        assert row.publishable is False and row.quarantine_reason is None
    result=dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)
    assert result['state']=='disabled' and result['reason']=='financial_environment_disabled'
    with factory() as db:
        j=db.get(IngestionJob,job)
        assert j.meta['post_commit_report_generation']['baselines']==1
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
    no_publication(factory)


@pytest.mark.parametrize('status',['ARCHIVED','FAILED'])
def test_numeric_gate_preserves_unavailable_source_refusal(pg,tmp_path,monkeypatch,status):
    from models import DocumentStatus
    from seeding.native_financial_gate import qualify_native_financial_rows
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest_revenue(factory,tmp_path,monkeypatch)
    with factory.begin() as db:
        row=db.get(RevenueBySource,record)
        db.get(SourceDocument,row.source_document_id).status=DocumentStatus[status]
        row.publishable=False;row.quarantine_reason=None
        db.flush()
        qualify_native_financial_rows(db,[row],domain='revenue_by_source',context=DomainRunContext(None,False,job))
        assert row.publishable is False


def test_revenue_financial_claim_preserves_public_departmental_scope(pg,tmp_path,monkeypatch):
    from seeding.source_observations import read_revenue_financial_observation
    factory,_=pg;enable(factory,monkeypatch)
    job,_=ingest_revenue(factory,tmp_path,monkeypatch)
    with factory() as db:
        record=db.scalar(select(RevenueBySource.id).where(RevenueBySource.revenue_type=='Customs & Import Duty'))
    value=read_revenue_financial_observation(factory,record_id=record,ingestion_id=job)
    assert value['facts'][0]['metric']=='Revenue collected: Customs departmental collections, including agency levies'


@pytest.mark.parametrize('head,expected',[
    ('Customs & Import Duty','Customs departmental collections, including agency levies'),
    ('VAT','Domestic VAT'),('Excise Duty','Domestic excise'),
])
def test_native_press_replaces_stale_measure_scope(pg,tmp_path,monkeypatch,head,expected):
    from seeding.domains.revenue_by_source import fetcher
    from seeding.source_observations import read_revenue_financial_observation
    factory,_=pg;enable(factory,monkeypatch)
    original=fetcher._apply_kra_live
    def seeded(payload,client,settings):
        stale=[dict(fiscal_year='FY 2024/25',revenue_type=head,category='tax',amount_billion_kes=None,
                    measure='Stale Exchequer-only estimate excluding agency levies',basis='projected')]
        return original(stale,client,settings)
    monkeypatch.setattr(fetcher,'_apply_kra_live',seeded)
    job,_=ingest_revenue(factory,tmp_path,monkeypatch)
    with factory() as db:
        record=db.scalar(select(RevenueBySource.id).where(RevenueBySource.revenue_type==head))
    value=read_revenue_financial_observation(factory,record_id=record,ingestion_id=job)
    assert value['facts'][0]['metric']=='Revenue collected: '+expected
    no_publication(factory)
