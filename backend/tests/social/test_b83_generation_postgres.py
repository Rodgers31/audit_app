"""B83 current-head PostgreSQL contracts; wholly owned, offline PDF fixtures.

Prepare this assigned database with the unchanged Alembic head before running.
The inherited historical a708 acceptance cohort is exercised separately.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from models import Country, Entity, EntityType, IngestionJob, BudgetLine, SourceDocument
from seeding.generation_dispatch import dispatch_committed_generation, dispatch_committed_report_generation
from seeding.source_observations import read_county_budget_record_ids
from services.generation_outcome import safe_generation_outcome
from social.generation.models import SourceCursor, SourceEvent
from social.generation.preview import preview
from social.models import SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget, SocialCommandReceipt
from test_report_postgres import ingest, enabled
from test_api_admin import make_client, key


@pytest.fixture
def pg():
    raw = os.getenv('B83_SOCIAL_TEST_DB_URL')
    if not raw:
        pytest.skip('Requires prepared owned 55412/b83_social_test current-head fixture')
    url = make_url(raw)
    if (url.drivername != 'postgresql+psycopg2' or url.host != '127.0.0.1' or url.port != 55412
            or url.database != 'b83_social_test' or url.query
            or any(k.startswith('PG') for k in os.environ)):
        raise RuntimeError('Only the assigned owned PostgreSQL fixture is allowed')
    engine = create_engine(url.set(query={'hostaddr':'127.0.0.1'}), pool_size=4, max_overflow=0)
    with engine.begin() as db:
        assert db.scalar(text('SELECT current_database()')) == 'b83_social_test'
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'a756b20a0001'
        tables = db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename LIKE 'social_%'" )).all()
        db.execute(text('TRUNCATE '+','.join('"'+t+'"' for t in tables)+' CASCADE'))
        db.execute(text('TRUNCATE etl_dispatch_worker,etl_dispatch_commands,etl_dispatch_domains,seeding_domain_claims,ingestion_jobs RESTART IDENTITY CASCADE'))
        if db.scalar(text("SELECT to_regclass('b15_generation_effects')")) is not None:
            db.execute(text('TRUNCATE b15_generation_effects'))
        db.execute(text('TRUNCATE countries RESTART IDENTITY CASCADE'))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        country = Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en')
        db.add(country); db.flush()
        for name, slug in [('Nairobi City County','nairobi'),('Mombasa County','mombasa'),('Kisumu County','kisumu')]:
            db.add(Entity(country_id=country.id,type=EntityType.COUNTY,canonical_name=name,slug=slug))
    try:
        yield factory, engine
    finally:
        engine.dispose()


def body(record, job, **extra):
    return dict(domain='counties_budget',record_ids=[record],ingestion_id=job,reports=True,backfill=False,**extra)


def first_record(factory, job):
    return read_county_budget_record_ids(factory, ingestion_id=job)[0]


def no_publication(factory):
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
        assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0


def test_current_pg_actual_pdf_preview_baseline_change_replay_and_concurrency(pg,tmp_path,monkeypatch):
    factory,_ = pg
    enabled(factory,monkeypatch)
    first = ingest(factory,tmp_path)
    record = first_record(factory,first)
    before = preview(factory,body(record,first))
    assert before['results'][0]['status'] == 'baseline'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor)) == 0
    dispatch_committed_generation(factory,domain='counties_budget',ingestion_id=first,dry_run=False)
    assert preview(factory,body(record,first))['results'][0]['status'] == 'unchanged'
    newer = ingest(factory,tmp_path,year=2024,published='2025-07-01')
    record = first_record(factory,newer)
    assert preview(factory,body(record,newer))['results'][0]['status'] == 'eligible_change'
    def run(_):
        return dispatch_committed_report_generation(factory,domain='counties_budget',ingestion_id=newer,dry_run=False)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run,range(3)))
    assert all(r['state']=='completed' for r in results)
    assert sum(r['drafts_created'] for r in results) == 3
    with factory() as db:
        posts = list(db.scalars(select(SocialPost)))
        assert len(posts)==3 and {p.editorial_state for p in posts}=={'pending_review'}
        assert {p.content_type for p in posts} == {'dataset_availability'}
        for post in posts:
            revision = db.get(SocialPostRevision,post.current_revision_id)
            assert revision.evidence_snapshot['source']['facts']==[]
            assert 'KES' not in revision.document['master']['text']
    no_publication(factory)


def test_current_pg_explicit_backfill_and_idempotent_http_replay(pg,tmp_path,monkeypatch):
    factory,engine = pg
    enabled(factory,monkeypatch)
    job = ingest(factory,tmp_path)
    record = first_record(factory,job)
    client = make_client(engine)
    route = '/api/v1/admin/social/generation/detect-reports'
    request = dict(record_ids=[record],ingestion_id=job,backfill=True,reason='Owned reasoned explicit backfill')
    headers = key()
    before = client.post('/api/v1/admin/social/generation/preview',json=body(record,job)|{'backfill':True})
    assert before.status_code==200 and before.json()['results'][0]['status']=='eligible_change'
    first = client.post(route,json=request,headers=headers)
    assert first.status_code==200,first.text
    assert first.json()['results'][0]['status']=='draft_created'
    assert client.post(route,json=request,headers=headers).json()==first.json()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==1
        assert db.scalar(select(func.count()).select_from(SocialCommandReceipt))>=1
    no_publication(factory)


@pytest.mark.parametrize('broken',['missing_date','fixture','changed_value','wrong_scope'])
def test_current_pg_real_source_refusals_have_exact_telemetry(pg,tmp_path,monkeypatch,broken):
    factory,_ = pg
    enabled(factory,monkeypatch)
    job = ingest(factory,tmp_path)
    record = first_record(factory,job)
    with factory.begin() as db:
        row = db.get(BudgetLine,record)
        doc = db.get(SourceDocument,row.source_document_id)
        if broken=='missing_date':doc.meta={k:v for k,v in doc.meta.items() if k!='publication_date_evidence'}
        if broken=='fixture':db.get(IngestionJob,job).meta={'source_mode':'fixture'}
        if broken=='changed_value':row.actual_spent+=1
        if broken=='wrong_scope':db.get(Entity,row.entity_id).type=EntityType.MINISTRY
    result = preview(factory,body(record,job))
    assert result['results'][0]['status']=='refused'
    if broken!='fixture':
        outcome = dispatch_committed_report_generation(factory,domain='counties_budget',ingestion_id=job,dry_run=False)
        assert outcome['refused']>=1 and sum(outcome['refusal_reasons'].values())==outcome['refused']
        with factory() as db:
            persisted = safe_generation_outcome(db.get(IngestionJob,job).meta['post_commit_report_generation'])
            assert persisted['refusal_reasons']==outcome['refusal_reasons']
    no_publication(factory)


@pytest.mark.parametrize('error_kind',['database','evidence','deadline'])
def test_current_pg_lost_commit_acknowledgement_never_certifies_zero(pg,tmp_path,monkeypatch,error_kind):
    factory,_ = pg
    enabled(factory,monkeypatch)
    first = ingest(factory,tmp_path)
    dispatch_committed_generation(factory,domain='counties_budget',ingestion_id=first,dry_run=False)
    newer = ingest(factory,tmp_path,year=2024,published='2025-07-01')
    def lost(session):
        if error_kind == 'evidence':
            from social.service import SocialError
            raise SocialError('SOURCE_NOT_ELIGIBLE','Inert after-commit evidence error')
        if error_kind == 'deadline':
            from social.generation.integration import GenerationDeadlineExceeded
            raise GenerationDeadlineExceeded('Inert after-commit deadline')
        raise DBAPIError('COMMIT',{},RuntimeError('inert lost acknowledgement after durable commit'),connection_invalidated=True)
    event.listen(factory.class_,'after_commit',lost)
    try:
        # Independent factory for telemetry; only draft commits lose their ack.
        import seeding.generation_dispatch as bridge
        original = bridge._invoke_reports
        monkeypatch.setattr(bridge,'_invoke_reports',lambda _factory, records, job: original(factory,records,job))
        telemetry_factory = sessionmaker(bind=factory.kw['bind'],expire_on_commit=False)
        # sessionmaker subclasses have their own event target; remove inherited
        # listener from telemetry by using a fresh base Session explicitly.
        from sqlalchemy.orm import Session
        telemetry_factory = sessionmaker(bind=factory.kw['bind'],class_=Session,expire_on_commit=False)
        result = bridge.dispatch_committed_report_generation(telemetry_factory,domain='counties_budget',ingestion_id=newer,dry_run=False)
    finally:
        event.remove(factory.class_,'after_commit',lost)
    assert result['execution_unverified'] is True and result['drafts_created'] is None
    assert result['confirmed']['drafts_created']==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==1
        persisted = safe_generation_outcome(db.get(IngestionJob,newer).meta['post_commit_report_generation'])
        assert persisted['execution_unverified'] is True and persisted['processed'] is None
    no_publication(factory)


@pytest.mark.parametrize('alteration',['receipt','source_mode','job_counter'])
def test_current_pg_altered_telemetry_cannot_claim_exact_receipt(pg,tmp_path,monkeypatch,caplog,alteration):
    from seeding.generation_capabilities import skipped_generation
    factory,engine = pg
    enabled(factory,monkeypatch)
    job = ingest(factory,tmp_path)
    with factory.begin() as db:
        row = db.get(IngestionJob,job)
        row.meta = {**row.meta,**skipped_generation('counties_budget',dry_run=False,source_mode='live',completed=True)}
    with engine.begin() as db:
        mutation = {
            'receipt': "NEW.metadata=jsonb_set(NEW.metadata,'{post_commit_report_generation,reason}','\"altered_fixture_receipt\"');",
            'source_mode': "NEW.metadata=jsonb_set(NEW.metadata,'{source_mode}','\"fixture\"');",
            'job_counter': 'NEW.items_processed=NEW.items_processed+1;',
        }[alteration]
        db.execute(text("""CREATE FUNCTION b83_alter_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.metadata->'post_commit_report_generation'->>'reason' <> 'hook_not_executed' THEN
            """+mutation+"""
          END IF;
          RETURN NEW;
        END $$"""))
        db.execute(text('CREATE TRIGGER b83_alter_receipt BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION b83_alter_receipt()'))
    try:
        result = dispatch_committed_report_generation(factory,domain='counties_budget',ingestion_id=job,dry_run=False)
        assert result['baselines']==3
        with factory() as db:
            row = db.get(IngestionJob,job)
            assert row.status.value=='completed'
            assert row.meta['post_commit_report_generation']['reason']=='hook_not_executed'
            assert row.meta['source_mode']=='live'
            assert row.items_processed==0
            assert db.scalar(select(func.count()).select_from(BudgetLine))==3
            assert db.scalar(select(func.count()).select_from(SourceCursor))==3
        assert 'post_commit_generation_receipt_unavailable' in caplog.text
    finally:
        with engine.begin() as db:
            db.execute(text('DROP TRIGGER b83_alter_receipt ON ingestion_jobs'))
            db.execute(text('DROP FUNCTION b83_alter_receipt()'))


@pytest.mark.parametrize('mode',['disabled','ineligible','failed','malformed_flag','dry_run','timed_out','bad_result','source_exception'])
def test_current_pg_native_cli_commit_receipts_and_ownership(pg,monkeypatch,mode):
    # Reuse the existing API→native CLI→parser/writer controls with the complete
    # accepted schema; no second container or source request is introduced.
    from test_b15_etl_native import test_native_cob_commit_precedes_generation_and_preserves_outcomes
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','false')
    test_native_cob_commit_precedes_generation_and_preserves_outcomes(pg,monkeypatch,mode)


def test_current_pg_financial_reader_requires_retained_publisher_date(pg,tmp_path,monkeypatch):
    from seeding.source_observations import read_county_budget_observation, SourceObservationUnavailable
    factory,_=pg
    enabled(factory,monkeypatch)
    job=ingest(factory,tmp_path)
    record=first_record(factory,job)
    # Valid actual PDF/value/lineage controls remain intact. A bare date copied
    # into document metadata cannot establish the publisher date authority.
    with factory.begin() as db:
        row=db.get(BudgetLine,record)
        doc=db.get(SourceDocument,row.source_document_id)
        doc.meta={k:v for k,v in doc.meta.items() if k!='publication_date_evidence'}
    with pytest.raises(SourceObservationUnavailable,match='publisher date authority'):
        read_county_budget_observation(factory,record_id=record,ingestion_id=job)
    no_publication(factory)
