"""Current migrated PostgreSQL, wholly owned synthetic publisher controls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from copy import deepcopy
import httpx
import pytest
from sqlalchemy import select, func, text

from test_b83_generation_postgres import pg, no_publication
from models import Country, SourceDocument, IngestionJob, IngestionStatus, DocumentType
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from seeding.native_report_authority import capture_kra_release, capture_pdf_report, persist_native_report, KEY
from seeding.source_observations import read_native_report_record_ids, read_revenue_report_observation, SourceObservationUnavailable
from seeding.generation_dispatch import dispatch_committed_report_generation
from social.generation.models import GenerationControls, SourceCursor, SourceEvent
from social.generation.preview import preview
from social.models import SocialPost, SocialPostRevision
from social.service import SocialService, SocialError
from social.generation.service import consume_observation
from test_b86_native_authority import HTML, KRA_URL


def enable(factory, monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','false')
    with factory.begin() as db:
        db.add(GenerationControls(id=1,version=1,drafts_enabled=True,shadow_enabled=False,source_allowlist=['cob','kra','oag'],targets=[]))


def ingest(factory,tmp_path, *, year=2024, published='10/07/2025', extra=b'', domain='revenue_by_source', url=KRA_URL, complete=True):
    with factory.begin() as db:
        job=IngestionJob(domain=domain,status=IngestionStatus.RUNNING,dry_run=False,started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();job_id=job.id
        if domain=='revenue_by_source':
            body=HTML.replace(b'2024/2025',f'{year}/{year+1}'.encode()).replace(b'10/07/2025',published.encode())+extra
            receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'text/html'},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path))
            authority,reason=capture_kra_release(receipt)
        else:
            from test_cob_publication_producer import pdf_bytes
            title=(f'NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT FY {year}/{str(year+1)[-2:]}' if domain=='national_budget'
                   else f'REPORT OF THE AUDITOR-GENERAL ON TEST MINISTRY FOR THE YEAR ENDED 30 JUNE {year+1}')
            body=pdf_bytes('0','Publication date: '+published).replace(b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',title.encode())
            path=tmp_path/(domain+'.pdf');path.write_bytes(body)
            receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'application/pdf'},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path),source_kind='pdf')
            authority,reason=capture_pdf_report(path,receipt,domain=domain)
        assert authority is not None,reason
        source=db.scalar(select(SourceDocument).where(SourceDocument.url==url))
        if source is None:
            source=SourceDocument(country_id=db.scalar(select(Country.id)),publisher={'revenue_by_source':'Kenya Revenue Authority','national_budget':'Controller of Budget','audits':'Office of the Auditor-General'}[domain],title='Owned synthetic release',url=url,fetch_date=datetime.now(timezone.utc),doc_type=DocumentType.REPORT,meta={})
            db.add(source);db.flush()
        record=persist_native_report(db,source,authority,context=DomainRunContext(None,False,job_id),domain=domain)
        if complete:
            job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
    return job_id,record


def body(job,record,domain='revenue_by_source',**kw):
    return dict(domain=domain,record_ids=[record],ingestion_id=job,reports=True,backfill=False,**kw)


def test_kra_native_reader_baseline_change_concurrent_replay(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    assert read_native_report_record_ids(factory,ingestion_id=job,domain='revenue_by_source')==(record,)
    assert preview(factory,body(job,record))['results'][0]['status']=='baseline'
    result=dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)
    assert result['baselines']==1 and result['drafts_created']==0
    same,new_record=ingest(factory,tmp_path,extra=b'<!-- different layout -->')
    result=dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=same,dry_run=False)
    assert result['unchanged']==1 and result['drafts_created']==0
    newer,record=ingest(factory,tmp_path,year=2025,published='10/07/2026')
    assert preview(factory,body(newer,record))['results'][0]['status']=='eligible_change'
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=newer,dry_run=False),range(3)))
    assert sum(r['drafts_created'] for r in results)==1,results
    with factory() as db:
        posts=list(db.scalars(select(SocialPost)))
        assert len(posts)==1 and posts[0].editorial_state=='pending_review'
        revision=db.get(SocialPostRevision,posts[0].current_revision_id)
        assert revision.evidence_snapshot['source']['facts']==[]
        assert 'KES' not in revision.document['master']['text']
    no_publication(factory)


@pytest.mark.parametrize('broken',['fixture','failed','partial','running','errors','wrong_domain','wrong_job','future','date','scope','active','archived'])
def test_native_hostile_current_evidence_refuses(pg,tmp_path,monkeypatch,broken):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:
        j=db.get(IngestionJob,job)
        if broken=='fixture':j.meta={**j.meta,'source_mode':'fixture'}
        if broken in ('failed','partial','running'):j.status={'failed':IngestionStatus.FAILED,'partial':IngestionStatus.COMPLETED_WITH_ERRORS,'running':IngestionStatus.RUNNING}[broken]
        if broken=='errors':j.errors=['inert partial error']
        if broken=='wrong_domain':j.domain='counties_budget'
        if broken=='wrong_job':
            j.meta={**j.meta,'native_report_records':{'revenue_by_source':[True]}}
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(j,'meta')
        if broken=='future':j.finished_at=datetime(2099,1,1)
        source=db.scalar(select(SourceDocument))
        if broken=='active':source.meta={}
        if broken=='archived':
            from models import DocumentStatus
            source.status=DocumentStatus.ARCHIVED
        if broken in ('date','scope'):
            from models import Extraction
            ext=db.get(Extraction,record);value=deepcopy(ext.extracted_json)
            value['response_receipt']['observations'][0]['published_on' if broken=='date' else 'entity']='invented'
            ext.extracted_json=value
    assert preview(factory,body(job,record))['results'][0]['status']=='refused'
    no_publication(factory)


def test_stale_snapshot_cannot_create_draft_and_missing_proof_invalidates(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    ingest(factory,tmp_path,year=2025,published='10/07/2026')
    with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
        with factory.begin() as db:
            consume_observation(SocialService(db),value,backfill=True)
    with factory.begin() as db:
        source=db.scalar(select(SourceDocument));persist_native_report(db,source,None,context=DomainRunContext(None,False,None),domain='revenue_by_source')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
        assert db.scalar(select(func.count()).select_from(SourceCursor))==0
    no_publication(factory)


def test_native_actual_http_backfill_is_reasoned_and_idempotent(pg,tmp_path,monkeypatch):
    from test_api_admin import make_client,key
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    client=make_client(engine)
    request=dict(domain='revenue_by_source',record_ids=[record],ingestion_id=job,backfill=True,reason='Owned explicit review backfill')
    headers=key();route='/api/v1/admin/social/generation/detect-reports'
    response=client.post(route,json=request,headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['results'][0]['status']=='draft_created'
    assert client.post(route,json=request,headers=headers).json()==response.json()
    no_publication(factory)


@pytest.mark.parametrize('domain,url',[('national_budget','https://cob.go.ke/native-annual.pdf'),('audits','https://www.oagkenya.go.ke/native-audit.pdf')])
def test_actual_native_pdf_capture_to_preview_and_draft(pg,tmp_path,monkeypatch,domain,url):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,domain=domain,url=url,published='2025-07-10')
    assert preview(factory,body(job,record,domain))['results'][0]['status']=='baseline'
    result=dispatch_committed_report_generation(factory,domain=domain,ingestion_id=job,dry_run=False)
    assert result['baselines']==1,result
    job,record=ingest(factory,tmp_path,domain=domain,url=url,year=2025,published='2026-07-10')
    result=dispatch_committed_report_generation(factory,domain=domain,ingestion_id=job,dry_run=False)
    assert result['drafts_created']==1,result
    no_publication(factory)


def test_later_successful_job_without_authority_refuses_old_report(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:
        db.add(IngestionJob(domain='revenue_by_source',status=IngestionStatus.COMPLETED,dry_run=False,started_at=datetime.now(timezone.utc),finished_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'}))
    assert preview(factory,body(job,record))['results'][0]['reason']=='source_review_required'
    no_publication(factory)


def test_native_writer_rollback_retains_previous_authority(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with pytest.raises(RuntimeError,match='inert rollback'):
        with factory.begin() as db:
            source=db.scalar(select(SourceDocument))
            persist_native_report(db,source,None,context=DomainRunContext(None,False,None),domain='revenue_by_source')
            raise RuntimeError('inert rollback')
    assert preview(factory,body(job,record))['results'][0]['status']=='baseline'


def test_revenue_native_producer_overlay_parser_writer_retains_authority(pg,tmp_path,monkeypatch):
    from seeding.domains.revenue_by_source.fetcher import _read_release, _apply_kra_live
    from seeding.domains.revenue_by_source.parser import parse_revenue_payload
    from seeding.domains.revenue_by_source.writer import persist_revenue_records
    import seeding.domains.revenue_by_source.fetcher as producer
    from models import RevenueBySource
    factory,_=pg;enable(factory,monkeypatch)
    article=HTML.replace(b'<p>PAYE collection stood at Kshs. 560 Billion.</p>',b'<p>PAYE collection stood at Kshs. 560 Billion.</p><p>Corporation Tax collected Kshs. 300 Billion.</p><p>Domestic VAT collected Kshs. 320 Billion.</p><p>Domestic Excise collection stood at Kshs. 70 Billion.</p><p>Customs collection stood at Kshs. 800 Billion.</p>')
    class Client:
        receipt_store=LocalReceiptStore(tmp_path)
        def get(self,url,**kw):return httpx.Response(200,content=article,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    with factory.begin() as db:
        job=IngestionJob(domain='revenue_by_source',status=IngestionStatus.RUNNING,dry_run=False,started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();job_id=job.id
        release=_read_release(Client(),KRA_URL,None)
        monkeypatch.setattr(producer,'discover_kra_releases',lambda *a:([release],release.fiscal_year,release.url))
        payload,status=_apply_kra_live([],Client(),SeedingSettings())
        assert status.startswith('promoted'),status
        records=parse_revenue_payload(payload)
        assert len(records)>=5
        stats=persist_revenue_records(db,records,SeedingSettings(),DomainRunContext(None,False,job_id))
        assert not stats.errors,stats.errors
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
    ids=read_native_report_record_ids(factory,ingestion_id=job_id,domain='revenue_by_source')
    assert len(ids)==1
    assert preview(factory,body(job_id,ids[0]))['results'][0]['status']=='baseline'
    with factory() as db:
        assert len(list(db.scalars(select(RevenueBySource))))>=5
        assert all('_native_report_authority' not in (row.meta or {}) for row in db.scalars(select(RevenueBySource)))
    no_publication(factory)


@pytest.mark.parametrize('field',['md5','title','artifact'])
def test_changed_current_document_identity_invalidates_native_report(pg,tmp_path,monkeypatch,field):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:
        source=db.scalar(select(SourceDocument))
        if field=='artifact':source.meta={**source.meta,'pdf_artifact_v1':{'sha256':'b'*64}}
        else:setattr(source,field,'b'*32)
    assert preview(factory,body(job,record))['results'][0]['status']=='refused'


def test_native_country_binding_and_country_change_refuse(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with factory.begin() as db:db.scalar(select(Country)).iso_code='UGA'
    assert preview(factory,body(job,record))['results'][0]['status']=='refused'
    with pytest.raises(ValueError,match='Kenyan native report country required'):
        ingest(factory,tmp_path)


def test_suppressed_missing_proof_invalidation_rolls_back(pg,tmp_path,monkeypatch):
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    with engine.begin() as db:
        db.execute(text("CREATE FUNCTION b86_keep_native_metadata() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.metadata=OLD.metadata; RETURN NEW; END $$"))
        db.execute(text('CREATE TRIGGER b86_keep_native_metadata BEFORE UPDATE ON source_documents FOR EACH ROW EXECUTE FUNCTION b86_keep_native_metadata()'))
    try:
        with pytest.raises(ValueError,match='invalidation readback differs'):
            with factory.begin() as db:
                source=db.scalar(select(SourceDocument))
                persist_native_report(db,source,None,context=DomainRunContext(None,False,None),domain='revenue_by_source')
    finally:
        with engine.begin() as db:
            db.execute(text('DROP TRIGGER b86_keep_native_metadata ON source_documents'))
            db.execute(text('DROP FUNCTION b86_keep_native_metadata()'))
    assert preview(factory,body(job,record))['results'][0]['status']=='baseline'
