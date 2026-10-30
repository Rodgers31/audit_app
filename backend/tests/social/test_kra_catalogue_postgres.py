"""Real retained KRA bytes through native producer/writer and owned PostgreSQL.

No network or production credentials. Transport/job clocks here are synthetic;
the independently pinned document contents were acquired on 27 October 2026.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
from pathlib import Path
import httpx
import pytest
from sqlalchemy import select, func
from models import IngestionJob, IngestionStatus, RevenueBySource, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from seeding.domains.revenue_by_source import fetcher, parser, writer
from seeding.source_observations import read_native_report_record_ids, read_revenue_report_observation
from seeding.generation_dispatch import dispatch_committed_report_generation
from services.receipt_store import LocalReceiptStore
from social.generation.preview import preview
from social.generation.models import SourceCursor, SourceEvent, GenerationControls
from social.generation.contracts import SourceObservation
from social.generation.service import consume_observation
from social.models import SocialPost, SocialPostRevision
from social.service import SocialService, SocialError
from test_b83_generation_postgres import pg, no_publication
from native_worker_fixture import restricted
from test_b86_native_postgres import enable
from test_api_admin import make_client, key
from test_kra_catalogue import URL, CATALOGUE

FIXTURES = Path(__file__).parents[1]/'fixtures/kra'


def primary(name, sha):
    body = gzip.decompress((FIXTURES/name).read_bytes())
    assert hashlib.sha256(body).hexdigest() == sha
    return body


class Publisher:
    def __init__(self,tmp_path, *, invalid=False):
        self.receipt_store=LocalReceiptStore(tmp_path); self.downloads=[]; self.receipts={}
        self.wrapper=primary('fy2025_26_wrapper_2026-10-27.html.gz','ad995d6a60db6388011520a4f26c29e37c4cee057f2db7d6af7f1483b213395f')
        self.catalogue=primary('catalogue_2026-10-27.html.gz','3d7c5eb4dfb10bfb3ede591eb547db1a6e19d883982b4eed766782cfb801176b')
        if invalid:self.catalogue=b'<html>No exact entry</html>'
        self.bundle=gzip.decompress((FIXTURES/'fy2025_26_dashboard_bundle.js.gz').read_bytes())
        self.shell=(FIXTURES/'fy2025_26_dashboard_shell.html').read_bytes()
    def get(self,url,**kwargs):
        if url==URL:body=self.wrapper
        elif url=='https://krarevenue2526testingdashboard.bolt.host':body=self.shell
        elif url.startswith('https://krarevenue2526testingdashboard.bolt.host/assets/'):body=self.bundle
        else:return httpx.Response(404,request=httpx.Request('GET',url))
        return httpx.Response(200,content=body,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    def download_to_file(self,url,path,**kwargs):
        from services.response_receipts import capture_response
        assert url==CATALOGUE and kwargs==dict(max_seconds=20,max_bytes=512*1024)
        self.downloads.append(url);path.write_bytes(self.catalogue)
        self.receipts[url]=capture_response(httpx.Response(200,content=self.catalogue,headers={'content-type':'text/html'},
            request=httpx.Request('GET',url)),self.receipt_store)
    def download_receipt(self,url):return self.receipts[url]


def ingest(factory,tmp_path,*,invalid=False):
    settings=SeedingSettings(kra_revenue_url=URL);client=Publisher(tmp_path,invalid=invalid)
    with factory.begin() as db:
        job=IngestionJob(domain='revenue_by_source',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush()
        rows,status=fetcher._apply_kra_live([],client,settings)
        assert status.startswith('promoted'),status
        assert client.downloads==[CATALOGUE]
        stats=writer.persist_revenue_records(db,parser.parse_revenue_payload(rows),settings,DomainRunContext(None,False,job.id))
        assert not stats.errors,stats.errors
        assert stats.processed>=5
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc);job_id=job.id
    ids=read_native_report_record_ids(factory,ingestion_id=job_id,domain='revenue_by_source') if not invalid else ()
    assert len(ids)==(0 if invalid else 1)
    return job_id,ids[0] if ids else None


def request(job,record,**kw):
    return dict(domain='revenue_by_source',record_ids=[record],ingestion_id=job,reports=True,backfill=False)|kw


def test_real_catalogue_producer_baseline_backfill_and_new_command_replay(pg,tmp_path,monkeypatch):
    factory,engine=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    assert value['report']['published_on'] is None and value['report']['catalogued_on']=='2026-07-08'
    assert preview(factory,request(job,record))['results'][0]['status']=='baseline'
    outcome=dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)
    assert outcome['baselines']==1 and outcome['drafts_created']==0,outcome
    client=make_client(engine);route='/api/v1/admin/social/generation/detect-reports'
    body={k:v for k,v in request(job,record,backfill=True,reason='Owner approved historical catalogue example').items() if k!='reports'}
    first=client.post(route,json=body,headers=key())
    assert first.status_code==200,first.text
    assert first.json()['results'][0]['status']=='draft_created'
    replay=client.post(route,json=body|{'reason':'Fresh command must not duplicate the current draft'},headers=key())
    assert replay.status_code==200 and replay.json()['results'][0]['status']=='unchanged',replay.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==1
        assert db.scalar(select(func.count()).select_from(SourceEvent))==1
        revision=db.scalar(select(SocialPostRevision));post=db.scalar(select(SocialPost))
        assert post.editorial_state=='pending_review'
        assert 'The report’s publication date is not stated. Human review is required.' in revision.document['master']['text']
        assert '2.8' not in revision.document['master']['text']
        assert revision.evidence_snapshot['source']['report']['evidence_kind']=='publisher_catalogue'
        assert db.scalar(select(func.count()).select_from(RevenueBySource))>=5
    no_publication(factory)


def test_reacquisition_is_not_a_new_report_and_concurrent_backfill_deduplicates(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    assert dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)['baselines']==1
    job,record=ingest(factory,tmp_path)
    assert dispatch_committed_report_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False)['unchanged']==1
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    def detect(_):
        with factory.begin() as db:return consume_observation(SocialService(db),value,backfill=True)
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(detect,range(3)))
    assert sum(r['status']=='draft_created' for r in results)==1
    no_publication(factory)


def test_bad_catalogue_preserves_numeric_observations_but_invalidates_report(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    ingest(factory,tmp_path,invalid=True)
    assert preview(factory,request(job,record))['results'][0]['status']=='refused'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RevenueBySource))>=5
        assert db.scalar(select(func.count()).select_from(SocialPost))==0


def test_catalogue_shadow_and_policy_require_human_even_with_future_automation(restricted,tmp_path,monkeypatch):
    from uuid import UUID
    from types import SimpleNamespace
    from test_domain_support import account, call
    from test_generation import rule, evaluate
    from social.automation.service import source_scope, candidate_gates
    factory,_,_,_=restricted;enable(factory,monkeypatch);job,record=ingest(factory,tmp_path)
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    parsed=SourceObservation.model_validate(value)
    with factory() as db:
        a=account(db)
        cfg=db.get(GenerationControls,1);cfg.shadow_enabled=True;db.commit()
        created=call(db,parsed,lambda s:consume_observation(s,parsed,backfill=True))[1]
        post=call(db,parsed,lambda s:s.detail(UUID(created['post_id'])))[1]
        policy=rule(db,[a],source_allowlist=['kra'])
        monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','true')
        decision=evaluate(db,post,policy)
        assert decision['outcome']=='human_review'
        assert 'CATALOGUE_HUMAN_REVIEW_REQUIRED' in decision['reasons']
        with pytest.raises(SocialError,match='CATALOGUE_HUMAN_REVIEW_REQUIRED'):source_scope(parsed)
        row=db.get(SocialPost,UUID(created['post_id']));revision=db.get(SocialPostRevision,row.current_revision_id)
        # Execute the real policy admission function; the source/revision checks
        # run before the immutable catalogue kind refuses automatic authority.
        with pytest.raises(SocialError,match='CATALOGUE_HUMAN_REVIEW_REQUIRED'):
            candidate_gates(SocialService(db),row,revision,SimpleNamespace(),SimpleNamespace(),datetime.now(timezone.utc))
    no_publication(factory)


@pytest.mark.parametrize('broken',['catalogue_day','publication_day','catalogue_url','catalogue_receipt','catalogue_clock','kind'])
def test_stored_catalogue_corruption_refuses(pg,tmp_path,monkeypatch,broken):
    factory,_=pg;enable(factory,monkeypatch);job,record=ingest(factory,tmp_path)
    with factory.begin() as db:
        ext=db.get(Extraction,record);raw=deepcopy(ext.extracted_json);value=raw['response_receipt']['observations'][0]
        if broken=='catalogue_day':value['catalogued_on']='2099-01-01'
        if broken=='publication_day':value['published_on']='2026-07-08'
        if broken=='catalogue_url':value['catalogue_url']='https://evil.invalid'
        if broken=='kind':value['evidence_kind']='publication'
        if broken=='catalogue_receipt':value['catalogue_authority']['receipt']['status']=True
        if broken=='catalogue_clock':value['catalogue_authority']['receipt']['acquired_at']='2000-01-01T00:00:00+00:00'
        ext.extracted_json=raw
    assert preview(factory,request(job,record))['results'][0]['status']=='refused'
    no_publication(factory)
