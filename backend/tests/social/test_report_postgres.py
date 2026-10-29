"""Actual PDF→retained qualification→post-commit neutral policy, entirely offline.

Human-published outcomes below are explicitly synthetic operating-test fixtures.
No source/provider HTTP, credentials, uploads or production activation is used.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import Country, Entity, EntityType, FiscalPeriod, IngestionJob, IngestionStatus, BudgetLine, SourceDocument
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from seeding.domains.counties_budget.writer import persist_budget_records
from seeding.domains.counties_budget.fetcher import convert_county_pdf_records
from seeding.domains.counties_budget.parser import parse_budget_payload
from seeding.domains.counties_budget.publication import capture_publication_date
from seeding.pdf_evidence import bind_parse_receipt
from seeding.parse_cache import parse_with_cache
from seeding.pdf_parsers import CoBQuarterlyReportParser
from seeding.source_observations import read_county_report_observation, SourceObservationUnavailable
from seeding.generation_dispatch import dispatch_committed_generation
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from social.models import SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget, SocialControls
from social.generation.models import SourceCursor
from social.generation.contracts import SourceObservation
from social.generation.integration import maybe_generate_reports_committed
from social.automation.service import AutomationService, worker_gate
from social.automation.contracts import OperatingEvidenceCommand, SnapshotCommand, PolicyControlsCommand
from social.contracts import ApproveCommand
from test_domain_support import account, call
from test_generation import configure, rule, evaluate
from test_policy_hook_registry import validation_environment


@pytest.fixture
def pg():
    value = os.getenv('B15_NEUTRAL_TEST_DB_URL')
    if not value:
        pytest.skip('Requires owned 55412/b15_neutral_test full-chain fixture')
    url = make_url(value)
    if (url.drivername != 'postgresql+psycopg2' or url.host != '127.0.0.1' or url.port != 55412
            or url.database != 'b15_neutral_test' or url.query):
        raise RuntimeError('Only assigned owned loopback neutral database is allowed')
    engine = create_engine(url.set(query={'hostaddr': '127.0.0.1'}), pool_size=8, max_overflow=0)
    with engine.begin() as connection:
        assert connection.scalar(text('select current_database()')) == 'b15_neutral_test'
        assert connection.scalar(text('select version_num from alembic_version')) == 'a708b15a0001'
        tables = connection.scalars(text("select tablename from pg_tables where schemaname=current_schema() and tablename like 'social_%'" )).all()
        connection.execute(text('TRUNCATE '+','.join('"'+name+'"' for name in tables)+' CASCADE'))
        connection.execute(text('TRUNCATE countries RESTART IDENTITY CASCADE'))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        country = Country(iso_code='KEN', name='Kenya', currency='KES', timezone='Africa/Nairobi', default_locale='en')
        db.add(country); db.flush()
        for name, slug in [('Nairobi City County','nairobi'), ('Mombasa County','mombasa'), ('Kisumu County','kisumu')]:
            db.add(Entity(country_id=country.id, type=EntityType.COUNTY, canonical_name=name, slug=slug))
    try:
        yield factory, engine
    finally:
        engine.dispose()


def ingest(factory, tmp_path, *, year=2023, published='2024-07-01', amount='0', multiple_categories=False):
    from test_cob_publication_producer import pdf_bytes
    period = f'FY{year}/{str(year+1)[2:]}'
    if multiple_categories:
        from report_pdf_fixture import multicategory_pdf as pdf_bytes
    body = pdf_bytes(amount, 'Publication date: '+published).replace(b'FY2025/26', period.encode())
    path = tmp_path/('report-'+sha256(body).hexdigest()+'.pdf')
    path.write_bytes(body)
    url = f'https://cob.go.ke/owned-neutral-{year}.pdf'
    receipt = capture_response(httpx.Response(200, content=body, headers={'content-type':'application/pdf'},
        request=httpx.Request('GET', url)), LocalReceiptStore(tmp_path/'receipts'), source_kind='pdf')
    parsed = parse_with_cache(path, cache_dir=tmp_path/'cache', kind='neutral-control',
        parse_fn=CoBQuarterlyReportParser(path).parse, enabled=False)
    receipt = bind_parse_receipt(receipt, parsed)
    date, refusal = capture_publication_date(path, receipt)
    assert date is not None and refusal is None
    records = parse_budget_payload(convert_county_pdf_records(parsed, url, receipt['digest'], receipt=receipt,
        publication_evidence=date, publication_refusal=refusal))
    settings = SeedingSettings(storage_path=tmp_path/'store', cache_path=tmp_path/'cache',
        log_path=tmp_path/'logs/seed.log', cob_verified_qualification_enabled=True)
    with factory.begin() as db:
        job = IngestionJob(domain='counties_budget', status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
        db.add(job); db.flush()
        stats = persist_budget_records(db, records, settings, DomainRunContext(None, False, job.id))
        assert not stats.errors and stats.qualification['qualified'] == (6 if multiple_categories else 3)
        job.status = IngestionStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job_id = job.id
    return job_id


def enabled(factory, monkeypatch, *, target=False):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','false')
    with factory() as db:
        selected = None
        if target:
            validation_environment(monkeypatch)
            from social.adapters.validation_registry import load_native_validation_registry
            registry = load_native_validation_registry()
            selected = account(db)
            adapter = registry.adapters[('facebook','facebook_pages')]
            selected.api_product, selected.external_account_id = adapter.product, '123456'
            selected.granted_scopes = list(adapter.scopes)
            selected.capability_snapshot = adapter.capabilities(dict(platform=selected.platform, api_product=selected.api_product,
                external_account_id=selected.external_account_id, connection_state=selected.connection_state,
                granted_scopes=selected.granted_scopes, capability_snapshot=selected.capability_snapshot)).model_dump(mode='json')
            selected.capabilities_checked_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        configure(db, [selected] if selected else [])
        return selected.id if selected else None


def dispatch(factory, job):
    return dispatch_committed_generation(factory, domain='counties_budget', ingestion_id=job, dry_run=False)


def repository_gate(db, engine, publication_id, selected_id):
    from social.worker.repository import QueueRepository
    from social.worker.config import WorkerConfig
    connection=db.connection()
    controls=connection.execute(text('SELECT * FROM social_controls WHERE id=1 FOR UPDATE')).mappings().one()
    account_row=connection.execute(text('SELECT * FROM social_accounts WHERE id=:id FOR UPDATE'),{'id':selected_id}).mappings().one()
    publication=connection.execute(text('SELECT * FROM social_publications WHERE id=:id FOR UPDATE'),{'id':publication_id}).mappings().one()
    target=connection.execute(text('SELECT * FROM social_post_targets WHERE publication_id=:id FOR UPDATE'),{'id':publication_id}).mappings().one()
    return QueueRepository(engine,WorkerConfig(database_url=engine.url.render_as_string(hide_password=False)),uuid4())._gate(connection,controls,account_row,publication,target,datetime.now(timezone.utc),True)


def test_actual_postcommit_creates_neutral_baselines_without_relabelling_finance(pg, tmp_path, monkeypatch):
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest(factory, tmp_path)
    dispatch(factory, first)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor).where(SourceCursor.source_key.like('cob:county:%:reports'))) == 3
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
        assert db.get(IngestionJob, first).meta['post_commit_report_generation']['baselines'] == 3
    second = ingest(factory, tmp_path, year=2024, published='2025-07-01')
    dispatch(factory, second)
    dispatch(factory, second)
    with factory() as db:
        posts = list(db.scalars(select(SocialPost)))
        assert len(posts)==3 and {p.content_type for p in posts}=={'dataset_availability'}
        for post in posts:
            revision = db.get(SocialPostRevision, post.current_revision_id)
            assert revision.evidence_snapshot['source']['facts']==[]
            assert 'KES' not in revision.document['master']['text']
            assert revision.generator_metadata['template_version']=='report-availability-v2'
        assert db.scalar(select(func.count()).select_from(SocialPublication))==0


def queued_report(pg, tmp_path, monkeypatch):
    factory, engine = pg
    selected_id = enabled(factory, monkeypatch, target=True)
    first = ingest(factory, tmp_path)
    dispatch(factory, first)
    sample_job = ingest(factory, tmp_path, year=2024, published='2025-07-01')
    dispatch(factory, sample_job)
    from social.adapters.validation_registry import load_native_validation_registry
    adapters = load_native_validation_registry().adapters
    with factory() as db:
        selected = db.get(__import__('social.models',fromlist=['SocialAccount']).SocialAccount, selected_id)
        sample = db.scalar(select(SocialPost).where(SocialPost.title.like('%Nairobi City County%')))
        sample = call(db, SourceObservation.model_validate(db.get(SocialPostRevision,sample.current_revision_id).evidence_snapshot['source']), lambda s:s.detail(sample.id), adapters=adapters)[1]
        policy = rule(db, [selected])
        decision = evaluate(db, sample, policy)
        assert decision['outcome']=='would_allow', decision
        approval = ApproveCommand(expected_version=sample['version'], revision_id=sample['revision_id'], review_attestation={'facts_checked':True,'sources_checked':True})
        call(db, approval, lambda s:s.approve(UUID(sample['id']),approval), adapters=adapters)
        target = db.scalar(select(SocialPostTarget))
        target.state, target.published_at, target.primary_remote_id = 'published', datetime.now(timezone.utc), 'synthetic-neutral-human-outcome'
        target.visibility_state, target.confirmation_kind = 'public','fixture-only'
        db.commit()
        body = OperatingEvidenceCommand(rule_id=policy['id'],rule_version=1,rule_hash=policy['definition_hash'],shadow_decision_ids=[decision['id']],
            evidence_url='https://example.test/synthetic-neutral-pilot',evidence_sha256='e'*64,accuracy_accepted=True,reliability_accepted=True,corrections_reviewed=True,reason='Synthetic offline human outcome only')
        evidence = call(db,body,lambda s:AutomationService(s).accept_operating_evidence(body),adapters=adapters)[1]
        body = SnapshotCommand(operating_evidence_id=evidence['id'],rule_id=policy['id'],rule_version=1,rule_hash=policy['definition_hash'],
            valid_until=datetime.now(timezone.utc)+timedelta(hours=12),materiality_mode='new_reporting_release',reason='Synthetic offline report release scope')
        snapshot = call(db,body,lambda s:AutomationService(s).authorize_snapshot(body),adapters=adapters)[1]
        monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','true')
        controls = db.get(SocialControls,1)
        controls.publishing_enabled=True
        db.commit()
        body = PolicyControlsCommand(expected_version=controls.version,snapshot_id=snapshot['id'],auto_approve_enabled=True,auto_schedule_enabled=True,auto_publish_enabled=True,reason='Inert owned fixture activation only')
        call(db,body,lambda s:AutomationService(s).set_controls(body),adapters=adapters)
    genuine = ingest(factory,tmp_path,year=2025,published='2026-07-01')
    dispatch(factory,genuine)
    with factory() as db:
        publication = db.scalar(select(SocialPublication).where(SocialPublication.authorization_kind=='policy'))
        assert publication is not None and publication.dispatch_requested_at is not None
        target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id==publication.id))
        assert target.state=='queued'
        publication_id = publication.id
        assert worker_gate(db.connection(), publication.id, selected_id,'facebook',datetime.now(timezone.utc),public=True) is None
        assert repository_gate(db,engine,publication.id,selected_id) is None
    return factory, engine, selected_id, publication_id, genuine


def test_actual_report_hook_policy_queue_worker_admission_and_artifact_invalidation(pg, tmp_path, monkeypatch):
    factory, engine, selected_id, publication_id, _ = queued_report(pg, tmp_path, monkeypatch)
    changed = ingest(factory,tmp_path,year=2025,published='2026-07-01',amount='2')
    dispatch(factory,changed)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost).where(SocialPost.content_type=='dataset_availability'))==6
        financial = list(db.scalars(select(SocialPost).where(SocialPost.content_type=='budget_update')))
        assert financial and all(p.editorial_state=='pending_review' for p in financial)
        assert db.scalar(select(func.count()).select_from(SocialPublication).where(SocialPublication.authorization_kind=='policy'))==1
        assert worker_gate(db.connection(),publication_id,selected_id,'facebook',datetime.now(timezone.utc),public=True) is not None
        assert repository_gate(db,engine,publication_id,selected_id)=='CANCELLED'


def test_concurrent_actual_report_readers_create_one_draft(pg,tmp_path,monkeypatch):
    factory,_=pg
    enabled(factory,monkeypatch)
    dispatch(factory,ingest(factory,tmp_path))
    newer=ingest(factory,tmp_path,year=2024,published='2025-07-01')
    with factory() as db:
        record=db.scalar(select(BudgetLine.id).where(BudgetLine.provenance.contains([{'ingestion_job_id':newer}])).order_by(BudgetLine.id))
    barrier=Barrier(8)
    def run(_):
        barrier.wait(timeout=10)
        return maybe_generate_reports_committed(factory,record_ids=[record],ingestion_id=newer)
    with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(run,range(8)))
    assert all(r['state']=='completed' for r in results),results
    assert sum(r['drafts_created'] for r in results)==1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==1


@pytest.mark.parametrize('broken',['missing_proof','date_binding','withheld','ambiguous_period'])
def test_real_report_reader_requires_current_qualified_date_scope(pg,tmp_path,monkeypatch,broken):
    factory,_=pg
    enabled(factory,monkeypatch)
    job=ingest(factory,tmp_path)
    with factory.begin() as db:
        row=db.scalar(select(BudgetLine).order_by(BudgetLine.id))
        record=row.id
        source=db.get(SourceDocument,row.source_document_id)
        if broken=='missing_proof': source.meta={key:value for key,value in source.meta.items() if key!='publication_date_evidence'}
        if broken=='date_binding': source.meta={**source.meta,'publication_date_evidence':{**source.meta['publication_date_evidence'],'digest':'b'*64}}
        if broken=='withheld': row.publishable=False
        if broken=='ambiguous_period':
            older=FiscalPeriod(country_id=source.country_id,label='FY2022/23',start_date=datetime(2022,7,1),end_date=datetime(2023,6,30))
            db.add(older);db.flush()
            other=BudgetLine(entity_id=row.entity_id,period_id=older.id,category='ambiguous control',currency='KES',allocated_amount=0,actual_spent=0,source_document_id=source.id,provenance=[{'ingestion_job_id':job}])
            db.add(other)
    with pytest.raises(SourceObservationUnavailable): read_county_report_observation(factory,record_id=record,ingestion_id=job)


@pytest.mark.parametrize('broken', ['withheld', 'missing_date', 'missing_qualification', 'noncounty', 'regressive_date'])
def test_current_source_edits_refuse_both_admission_gates_before_and_after_hook(pg, tmp_path, monkeypatch, broken):
    factory, engine, account_id, publication_id, job = queued_report(pg, tmp_path, monkeypatch)
    if broken == 'regressive_date':
        job = ingest(factory, tmp_path, year=2025, published='2025-07-01', amount='2')
    else:
        with factory.begin() as db:
            publication = db.get(SocialPublication, publication_id)
            source = db.get(SocialPostRevision, publication.revision_id).evidence_snapshot['source']
            report = source['report']
            row = db.get(BudgetLine, report['source_record_id'])
            if broken == 'withheld': row.publishable = False
            if broken == 'noncounty': db.get(Entity, row.entity_id).type = EntityType.MINISTRY
            if broken == 'missing_date':
                doc = db.get(SourceDocument, row.source_document_id)
                doc.meta = {k:v for k,v in doc.meta.items() if k != 'publication_date_evidence'}
            if broken == 'missing_qualification':
                from models import Extraction
                db.delete(db.get(Extraction, report['qualification_extraction_id']))
    # Fresh source admission does not rely on an enabled/successful next hook.
    for after_hook in (False, True):
        if after_hook: dispatch(factory, job)
        with factory() as db:
            worker = worker_gate(db.connection(), publication_id, account_id, 'facebook', datetime.now(timezone.utc), public=True)
            repository = repository_gate(db, engine, publication_id, account_id)
            assert worker == 'SOURCE_REVIEW_REQUIRED'
            assert repository == 'SOURCE_REVIEW_REQUIRED'


def test_actual_multicategory_pdf_deduplicates_report_per_county(pg, tmp_path, monkeypatch):
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest(factory, tmp_path, multiple_categories=True)
    dispatch(factory, first)
    with factory() as db:
        baseline = db.get(IngestionJob, first).meta['post_commit_report_generation']
        assert baseline['state'] == 'completed' and baseline['baselines'] == 3 and baseline['unchanged'] == 3
        assert db.scalar(select(func.count()).select_from(SourceCursor).where(SourceCursor.source_key.like('cob:county:%:reports'))) == 3
    second = ingest(factory, tmp_path, year=2024, published='2025-07-01', multiple_categories=True)
    dispatch(factory, second)
    with factory() as db:
        result = db.get(IngestionJob, second).meta['post_commit_report_generation']
        assert result['state'] == 'completed' and result['drafts_created'] == 3 and result['unchanged'] == 3
        assert db.scalar(select(func.count()).select_from(SocialPost).where(SocialPost.content_type=='dataset_availability')) == 3


def test_fresh_shadow_rechecks_withheld_source_without_next_hook(pg,tmp_path,monkeypatch):
    from social.generation.models import AutomationRuleVersion
    from test_generation import evaluate
    from test_domain_support import call
    factory,engine,selected_id,publication_id,job=queued_report(pg,tmp_path,monkeypatch)
    with factory() as source_db:
        publication = source_db.get(SocialPublication, publication_id)
        record = source_db.get(SocialPostRevision, publication.revision_id).evidence_snapshot['source']['report']['source_record_id']
    with factory() as db:
        pub=db.get(SocialPublication,publication_id)
        post=db.get(SocialPost,pub.post_id)
        policy=db.scalar(select(AutomationRuleVersion))
        from social.service import SocialService
        clock=datetime.now(timezone.utc)+timedelta(hours=2)
        monkeypatch.setattr(SocialService,'now',lambda self:clock)
        detail={'id':str(post.id),'version':post.row_version,'revision_id':str(post.current_revision_id)}
        rule={'id':str(policy.rule_id),'version':policy.version}
        initial=evaluate(db,detail,rule)
        assert initial['outcome']=='would_allow',initial
    with factory.begin() as writer:writer.get(BudgetLine,record).publishable=False
    with factory() as db:
        decision=evaluate(db,detail,rule)
        print({'fresh_shadow':decision})
        assert decision['outcome']=='human_review' and 'SOURCE_REVIEW_REQUIRED' in decision['reasons'],decision


def test_preexisting_conflicting_writer_cannot_leave_stale_witness_after_lock_wait(pg,tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic
    from social.generation.authority import verify_report_authority
    from social.service import SocialError
    factory,engine,selected_id,publication_id,job=queued_report(pg,tmp_path,monkeypatch)
    with factory() as source_db:
        publication = source_db.get(SocialPublication, publication_id)
        record = source_db.get(SocialPostRevision, publication.revision_id).evidence_snapshot['source']['report']['source_record_id']
    with factory() as db:
        pub=db.get(SocialPublication,publication_id)
        post=db.get(SocialPost,pub.post_id)
        source=db.get(SocialPostRevision,post.current_revision_id).evidence_snapshot['source']
        row=db.get(BudgetLine,record)
        older=db.scalar(select(BudgetLine.source_document_id).where(BudgetLine.entity_id==row.entity_id,
            BudgetLine.source_document_id!=row.source_document_id).order_by(BudgetLine.id))
    started=Event()
    admission_pid=[]
    def admission():
        with factory() as db:
            db.execute(text("SET LOCAL statement_timeout='5000ms'"))
            admission_pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            started.set()
            try:verify_report_authority(db,source)
            except SocialError as error:return error.code
            return None
    writer=engine.connect()
    transaction=writer.begin()
    try:
        writer.execute(text("""INSERT INTO budget_lines(entity_id,period_id,category,subcategory,currency,source_document_id,provenance,publishable)
            SELECT entity_id,period_id,category||'_preexisting_phantom',subcategory,currency,:older,provenance,false
            FROM budget_lines WHERE id=:record"""),{'record':record,'older':older})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(admission)
            assert started.wait(2),'Admission did not start'
            deadline=monotonic()+2
            waiting=False
            while monotonic()<deadline:
                with engine.connect() as observer:
                    waiting=observer.scalar(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),{'pid':admission_pid[0]})
                if waiting or future.done():break
                Event().wait(0.01)
            assert waiting,'Authority query did not wait behind the preexisting cohort writer'
            transaction.commit()
            result=future.result(timeout=6)
            print({'admission_waited':waiting,'writer_committed':True,'authority_result_after_wait':result})
            assert result=='SOURCE_REVIEW_REQUIRED','Authority used pre-wait snapshot after conflicting source writer committed'
    finally:
        if transaction.is_active:transaction.rollback()
        writer.close()
