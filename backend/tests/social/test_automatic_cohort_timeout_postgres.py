"""46-county automatic hook rehearsal with disclosed synthetic latency.

The PDF, HTTP envelopes, extraction cells, jobs and database are owned fixtures.
This tests the committed-source/qualification/authority/transaction path, not an
actual CoB acquisition or production network performance.
"""
from collections import Counter
from unittest.mock import patch
from datetime import datetime, timezone
from decimal import Decimal
import json
import time

import pytest
from sqlalchemy import event, select, func, delete, text
from models import Country, Entity, EntityType, IngestionJob, IngestionStatus, Loan, SourceDocument
from seeding.types import DomainRunContext
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import write_pending_bills
from seeding.native_report_authority import capture_pdf_report
from seeding.parse_cache import parse_with_cache
from seeding.pdf_evidence import bind_parse_receipt, cell_evidence, seal_pdf_observations
from seeding.pdf_parsers import KENYAN_COUNTIES
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION
from services.response_receipts import copy_receipt, capture_response, capture_retained_pdf
from services.receipt_store import LocalReceiptStore
from social.generation.models import SourceCursor
from social.models import SocialPost
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable
from test_native_publisher_metadata import inputs, acquisition, listing, COUNTY_TITLE, COUNTY_PAGE
from native_worker_fixture import restricted


def ingest_cohort(factory, tmp_path, *, correction=None, retained=False):
    """Real atomic writer with sealed source-shaped test extraction facts."""
    with factory.begin() as db:
        if db.scalar(select(func.count()).select_from(Loan)) == 0:
            db.execute(delete(Entity))
            for name in KENYAN_COUNTIES:
                db.add(Entity(country_id=db.scalar(select(Country.id)),type=EntityType.COUNTY,
                    canonical_name=f'{name} County',slug=name.lower().replace(' ','-')))
            db.flush()
        job=IngestionJob(domain='pending_bills',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();identity=job.id
        context=DomainRunContext(None,False,identity)
        if retained:
            path=tmp_path/'report.pdf'
            source=db.scalar(select(SourceDocument))
            receipt=capture_retained_pdf(db,context,LocalReceiptStore(tmp_path/'receipts'),
                domain='pending_bills',url=source.url,body=path.read_bytes())
            publisher=acquisition(tmp_path,listing(COUNTY_TITLE,COUNTY_PAGE,16482),COUNTY_PAGE,'text/html')
        else:
            def capture(response,store):
                return capture_response(response,store,source_kind='pdf' if response.headers.get('content-type')=='application/pdf' else 'api')
            with patch('test_native_publisher_metadata.capture_response',capture):
                path,receipt,publisher=inputs(tmp_path,'pending_bills')
        receipt=copy_receipt(receipt,parser_version='owned-cohort-extraction')
        authority,reason=capture_pdf_report(path,receipt,domain='pending_bills',publisher_receipt=publisher)
        assert authority is not None,reason
        parsed=parse_with_cache(path,cache_dir=tmp_path/'parse',kind='owned-cohort-extraction',
            parse_fn=lambda:[{'county':n,'raw_millions':'11.00'} for n in KENYAN_COUNTIES if n!='Nandi'],enabled=False)
        receipt=bind_parse_receipt(receipt,parsed)
        records,cells=[],[]
        for name in KENYAN_COUNTIES:
            if name=='Nandi':continue
            raw='12.00' if correction in (name,'all') else '11.00'
            amount=Decimal(raw)*1000000
            record=PendingBillRecord(entity_name=f'{name} County',entity_type='county',category='county',
                fiscal_year='FY2025/26',total_pending=amount,as_at='2026-06-30',source_table='Synthetic Table 2.10',source_page=1)
            cell=cell_evidence(receipt=receipt,identity=dict(measure='outstanding',entity_id=None,
                geography=record.entity_name,period='2026-06-30',unit='KES',basis='actual',
                dimensions={'lender':f'Pending Bills — County Governments ({record.entity_name})','debt_category':'pending_bills'}),
                raw_value=raw,value=str(amount),raw_unit='KES million',factor='1000000',
                locator={'page':1,'table':'Synthetic Table 2.10','cell':f'{name} / Grand Total'})
            record.source_evidence=[cell];records.append(record);cells.append(cell)
        seal_pdf_observations(cells)
        stats=write_pending_bills(db,records,source_url=authority.value['document_url'],source_title='Owned synthetic cohort report',
            publisher='Office of the Controller of Budget (OCOB)',publication=COUNTY_PENDING_BILLS_PUBLICATION,
            native_report_authority=authority,context=DomainRunContext(None,False,identity))
        assert sum(stats)==46,stats
        from services.figure_qualification import qualify_rows
        rows=list(db.scalars(select(Loan)))
        q=qualify_rows(db,'loans',rows)
        assert db.scalar(select(func.count()).select_from(Loan).where(Loan.publishable.is_(True)))==46, [(row.id,q[row.id]['outstanding']['reason']) for row in rows if not row.publishable]
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
    return identity


@pytest.mark.parametrize('mode',['fresh_baseline','retained_baseline','changed_cohort'])
def test_automatic_full_cohort_completes_with_bounded_query_latency(pg,tmp_path,monkeypatch,mode):
    factory,engine=pg;enable(factory,monkeypatch)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','false')
    retained=mode!='fresh_baseline'
    if retained:
        previous=ingest_cohort(factory,tmp_path)
        if mode=='changed_cohort':assert automatic(factory,previous)['baselines']==46
    job=ingest_cohort(factory,tmp_path,retained=retained,correction='all' if mode=='changed_cohort' else None)
    with engine.connect() as db:
        worker_authority_installed=db.scalar(text("SELECT to_regclass('public.social_native_source_authority_snapshot')")) is not None
    calls=Counter()
    latency=.020  # 20ms added per driver round trip; not a production RTT claim.
    def measured(_conn,_cursor,statement,_params,_context,_many):
        words=statement.lower().split()
        table=next((word for word in ('extractions','source_documents','ingestion_jobs','social_source_cursors','entities','countries') if word in statement.lower()),words[0] if words else 'empty')
        calls[table]+=1;time.sleep(latency)
    event.listen(engine,'after_cursor_execute',measured)
    started=time.monotonic()
    try:
        from seeding.cli import _post_commit_generation
        _post_commit_generation(factory,domain='pending_bills',ingestion_id=job,dry_run=False)
    finally:
        elapsed=time.monotonic()-started;event.remove(engine,'after_cursor_execute',measured)
    with factory() as db:
        outcome=db.get(IngestionJob,job).meta['post_commit_generation']
        baselines=db.scalar(select(func.count()).select_from(SourceCursor).where(SourceCursor.sequence==0))
        posts=db.scalar(select(func.count()).select_from(SocialPost))
    print('COHORT_PROFILE '+json.dumps({'mode':mode,'worker_authority_installed':worker_authority_installed,'retained_current_job':retained,'latency_per_call_seconds':latency,'elapsed_seconds':elapsed,'driver_calls':dict(calls),'outcome':outcome,'stored_baselines_including_source_marker':baselines,'stored_posts':posts},sort_keys=True))
    assert elapsed < 120, {'elapsed_seconds': elapsed, 'driver_calls': dict(calls)}
    changed=mode=='changed_cohort'
    assert outcome['state']=='completed' and outcome['processed']==46 and outcome['refused']==0,outcome
    assert outcome['baselines']==(0 if changed else 46) and outcome['drafts_created']==(46 if changed else 0)
    assert baselines==(1 if changed else 47) and posts==(46 if changed else 0)
    with factory() as db:
        assert all(p.editorial_state=='pending_review' for p in db.scalars(select(SocialPost)))
    no_publication(factory)


def test_full_changed_cohort_revalidates_installed_worker_authority(restricted,tmp_path,monkeypatch):
    from social.models import SocialPostRevision
    factory,engine,_,_=restricted
    test_automatic_full_cohort_completes_with_bounded_query_latency((factory,engine),tmp_path,monkeypatch,'changed_cohort')
    with factory() as db:
        revisions=list(db.scalars(select(SocialPostRevision)))
        assert len(revisions)==46
        assert all(revision.evidence_snapshot['worker_authority']['kind']=='financial' for revision in revisions)


def automatic(factory, job):
    from seeding.cli import _post_commit_generation
    _post_commit_generation(factory,domain='pending_bills',ingestion_id=job,dry_run=False)
    with factory() as db:
        return db.get(IngestionJob,job).meta['post_commit_generation']


def enabled(factory, monkeypatch):
    enable(factory,monkeypatch)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','false')


def test_automatic_cohort_replay_retained_refresh_and_one_meaningful_change(pg,tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from seeding.generation_dispatch import dispatch_committed_generation
    from social.generation.models import SourceEvent
    from social.models import SocialPostRevision
    factory,_=pg;enabled(factory,monkeypatch)
    first=ingest_cohort(factory,tmp_path)
    assert automatic(factory,first)['baselines']==46
    replay=automatic(factory,first)
    assert replay['state']=='completed' and replay['unchanged']==46 and replay['drafts_created']==0
    refreshed=ingest_cohort(factory,tmp_path,retained=True)
    unchanged=automatic(factory,refreshed)
    assert unchanged['state']=='completed' and unchanged['unchanged']==46 and unchanged['drafts_created']==0
    changed=ingest_cohort(factory,tmp_path,retained=True,correction='Nairobi')
    result=automatic(factory,changed)
    assert result['state']=='completed' and result['processed']==46 and result['drafts_created']==1 and result['unchanged']==45
    with ThreadPoolExecutor(max_workers=2) as pool:
        replays=list(pool.map(lambda _:dispatch_committed_generation(factory,domain='pending_bills',ingestion_id=changed,dry_run=False),range(2)))
    assert all(r['state']=='completed' and r['unchanged']==46 and r['drafts_created']==0 for r in replays)
    with factory() as db:
        posts=list(db.scalars(select(SocialPost)))
        assert len(posts)==1 and posts[0].editorial_state=='pending_review'
        revision=db.get(SocialPostRevision,posts[0].current_revision_id)
        fact=revision.evidence_snapshot['source']['facts'][0]
        assert fact['entity']=='Nairobi County' and fact['value']=='12000000.00'
        assert fact['unit']=='KES' and fact['scale']=='units' and fact['period']=='FY 2025/26'
        assert 'completeness is not assumed' in fact['comparison_basis']
        assert revision.evidence_snapshot['source']['ingestion_id']==str(changed)
        assert db.scalar(select(func.count()).select_from(SourceEvent))==1
    no_publication(factory)


def test_automatic_partial_body_timeout_preserves_confirmed_baselines_and_silent_replay(pg,tmp_path,monkeypatch):
    import social.generation.integration as integration
    factory,_=pg;enabled(factory,monkeypatch)
    job=ingest_cohort(factory,tmp_path)
    consume=integration.consume_committed_native_financial
    calls=0
    def interrupted(*args,**kwargs):
        nonlocal calls
        result=consume(*args,**kwargs);calls+=1
        if calls==12:raise integration.GenerationDeadlineExceeded('Owned body deadline before commit')
        return result
    monkeypatch.setattr(integration,'consume_committed_native_financial',interrupted)
    partial=automatic(factory,job)
    assert partial['state']=='failed' and partial['processed']==11 and partial['baselines']==11
    assert partial['drafts_created']==0 and not partial.get('execution_unverified')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor))==12
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
    monkeypatch.setattr(integration,'consume_committed_native_financial',consume)
    replay=automatic(factory,job)
    assert replay['state']=='completed' and replay['baselines']==35 and replay['unchanged']==11 and replay['drafts_created']==0
    no_publication(factory)


@pytest.mark.parametrize('kind',['evidence','deadline','database'])
def test_automatic_lost_commit_acknowledgement_retains_unknown_progress(pg,tmp_path,monkeypatch,kind):
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session, sessionmaker
    import seeding.generation_dispatch as bridge
    from social.generation.integration import GenerationDeadlineExceeded
    from social.service import SocialError
    factory,engine=pg;enabled(factory,monkeypatch)
    job=ingest_cohort(factory,tmp_path)
    class MutationSession(Session):pass
    mutation_factory=sessionmaker(bind=engine,class_=MutationSession,expire_on_commit=False)
    def lost(_session):
        if kind=='evidence':raise SocialError('SOURCE_NOT_ELIGIBLE','Owned lost acknowledgement after commit')
        if kind=='deadline':raise GenerationDeadlineExceeded('Owned lost acknowledgement after commit')
        raise DBAPIError('COMMIT',{},RuntimeError('Owned lost acknowledgement'),connection_invalidated=True)
    event.listen(MutationSession,'after_commit',lost)
    invoke=bridge._invoke
    monkeypatch.setattr(bridge,'_invoke',lambda _factory,*args,**kwargs:invoke(mutation_factory,*args,**kwargs))
    try:
        result=automatic(factory,job)
    finally:
        event.remove(MutationSession,'after_commit',lost)
        monkeypatch.setattr(bridge,'_invoke',invoke)
    assert result['execution_unverified'] is True and result['processed'] is None and result['drafts_created'] is None
    assert result['confirmed']['processed']==0 and result['confirmed']['baselines']==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor))==2
        assert db.get(IngestionJob,job).status==IngestionStatus.COMPLETED
    replay=automatic(factory,job)
    assert replay['state']=='completed' and replay['baselines']==45 and replay['unchanged']==1 and replay['drafts_created']==0
    no_publication(factory)


def test_automatic_retained_cohort_refuses_changed_original_acquisition(pg,tmp_path,monkeypatch):
    from models import Extraction
    from seeding.native_report_authority import KEY
    factory,_=pg;enabled(factory,monkeypatch)
    ingest_cohort(factory,tmp_path)
    job=ingest_cohort(factory,tmp_path,retained=True)
    with factory.begin() as db:
        source=db.scalar(select(SourceDocument))
        current=db.get(Extraction,source.meta[KEY]['pending_bills']['extraction_id'])
        origin=current.extracted_json['response_receipt']['retained_pdf_validation']['origin_extraction_id']
        db.get(Extraction,origin).extracted_json={}
    result=automatic(factory,job)
    assert result['state']=='unavailable' and result['processed']==46 and result['refused']==46
    assert result['baselines']==0 and result['drafts_created']==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor))==0
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
        assert db.get(IngestionJob,job).status==IngestionStatus.COMPLETED
    no_publication(factory)
