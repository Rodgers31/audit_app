"""Actual PostgreSQL DDL/uniqueness/locks on a separately owned disposable lane."""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from social.models import SocialAccount, SocialControls, SocialPostTarget, SocialPublishAttempt
from social.privacy.models import SocialPrivacyOwnership, SocialPrivacyReceipt
from social.connections.models import SocialOAuthFlow
from social.service import SocialError
from test_privacy_support import *


def migration(name):
    path = Path(__file__).resolve().parents[2] / 'alembic/versions' / name
    spec = importlib.util.spec_from_file_location(name.split('.')[0], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def privacy_pg():
    value = os.getenv('SOCIAL_PRIVACY_TEST_DATABASE_URL')
    if not value:
        pytest.skip('Set the private privacy disposable database lane')
    url = make_url(value)
    if (url.drivername not in {'postgresql','postgresql+psycopg2'} or url.host not in {'127.0.0.1','localhost'}
            or url.port != 62238 or url.database != 'privacy_disposable' or url.query):
        raise ValueError('Use only privacy_disposable on private loopback port 62238 without options')
    schema = 'privacy_' + uuid4().hex
    admin = create_engine(url.set(drivername='postgresql+psycopg2'), pool_size=1, max_overflow=0)
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    engine = create_engine(url.set(drivername='postgresql+psycopg2'), pool_size=5, max_overflow=0,
                           connect_args={'options': '-csearch_path=' + schema + ' -clock_timeout=5000 -cstatement_timeout=15000'})
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            for name in ('f38c61a9d203_social_manual_domain_queue.py', 'c96d13e2f411_social_meta_credentials.py',
                         'a42b86e1d310_social_private_media_intake.py', 'b73e19a4f602_social_media_write_settlement.py',
                         'd8f4a619b203_social_privacy_receipts.py'):
                migration(name).upgrade()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()


def test_actual_migration_private_rls_empty_downgrade(privacy_pg):
    with privacy_pg.begin() as conn:
        for name in ('social_privacy_ownership','social_privacy_receipts','social_privacy_request_variants'):
            assert conn.execute(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'), {'name':name}).scalar()
            assert not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name':name}).scalar()
        with Operations.context(MigrationContext.configure(conn)):
            migration('d8f4a619b203_social_privacy_receipts.py').downgrade()
        assert conn.execute(text("SELECT to_regclass('social_privacy_receipts')")).scalar() is None


def test_concurrent_receipt_insert_waits_then_returns_same_frozen_receipt(privacy_pg, config, graph):
    with Session(privacy_pg, expire_on_commit=False) as db:
        connected(db, config, graph)
    inserted, release, second_started = Event(), Event(), Event()
    first = True
    def pause(conn, cursor, statement, params, context, many):
        nonlocal first
        if statement.startswith('INSERT INTO social_privacy_receipts') and first:
            first = False
            inserted.set()
            assert release.wait(5)
    event.listen(privacy_pg, 'after_cursor_execute', pause)
    def receive(second=False):
        if second:
            second_started.set()
        with Session(privacy_pg) as db:
            return privacy(db, config).receive(signed(config), kind='data_deletion')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(receive)
            assert inserted.wait(5)
            two = pool.submit(receive, True)
            assert second_started.wait(5)
            # The uncommitted first insert exists, and second connection waits
            # for our common control lock. No in-memory replay set participates.
            import time
            deadline = time.monotonic() + 3
            waiting = 0
            with privacy_pg.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                while time.monotonic() < deadline:
                    observer.execute(text('SELECT pg_stat_clear_snapshot()'))
                    waiting = observer.execute(text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%social_controls%' AND pid<>pg_backend_pid() AND datname=current_database()")).scalar()
                    if waiting:
                        break
                    time.sleep(0.01)
            assert waiting >= 1
            assert not two.done()
            release.set()
            assert one.result(5) == two.result(5)
    finally:
        release.set()
        event.remove(privacy_pg, 'after_cursor_execute', pause)
    with Session(privacy_pg) as db:
        assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 1


def test_database_unique_and_immutable_history_and_downgrade_guard(privacy_pg, config, graph):
    with Session(privacy_pg) as db:
        connected(db, config, graph)
        privacy(db, config).receive(signed(config), kind='data_deletion')
    for sql in (
        'INSERT INTO social_privacy_receipts SELECT * FROM social_privacy_receipts',
        "UPDATE social_privacy_receipts SET state='ownership_unresolved'",
        "UPDATE social_privacy_ownership SET subject_digest=repeat('a',64)",
        'DELETE FROM social_privacy_request_variants',
        'INSERT INTO social_privacy_ownership SELECT * FROM social_privacy_ownership'):
        with pytest.raises(IntegrityError), privacy_pg.begin() as conn:
            conn.execute(text(sql))
    with pytest.raises(RuntimeError, match='Privacy history'), privacy_pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration('d8f4a619b203_social_privacy_receipts.py').downgrade()


def test_callback_in_external_exchange_blocks_late_inspected_save(privacy_pg, config, graph):
    fired = False
    original = graph.__call__
    def interleave(request):
        nonlocal fired
        if not fired:
            fired = True
            with Session(privacy_pg) as callback:
                privacy(callback, config).receive(signed(config), kind='deauthorization')
        return original(request)
    with Session(privacy_pg, expire_on_commit=False) as db:
        svc = connection(db, config, interleave)
        flow, state = start(svc)
        with pytest.raises(SocialError) as caught:
            complete(svc, state)
        assert caught.value.code == 'PRIVACY_OWNERSHIP_UNRESOLVED'
        assert db.get(SocialOAuthFlow, UUID(flow['flow_id'])).status == 'failed'
        assert list(db.scalars(select(SocialPrivacyOwnership))) == []


def test_indexed_query_positive_plan_and_legacy_miss(privacy_pg, config, graph):
    with Session(privacy_pg) as db:
        connected(db, config, graph)
    with privacy_pg.begin() as conn:
        conn.execute(text('SET LOCAL enable_seqscan=off'))
        plan = conn.execute(text("EXPLAIN SELECT id FROM social_privacy_ownership WHERE app_id='123' AND digest_version='d1' AND subject_digest=:subject"), {'subject':digester().digest('123','701')}).scalars().all()
        assert any('ix_social_privacy_subject' in line for line in plan)
    with Session(privacy_pg) as db:
        out = privacy(db, config).receive(signed(config, '777'), kind='deauthorization')
        assert out['resolution'] == 'unknown_or_legacy'


def test_active_uncertain_intent_checkpoint_provider_receipt_survive(privacy_pg, config, graph):
    from test_domain_support import call, draft_body, ACTOR
    from social.contracts import ApproveCommand
    from datetime import datetime, timedelta, timezone
    with Session(privacy_pg, expire_on_commit=False) as db:
        _, _, selected = connected(db, config, graph)
        row = db.get(SocialAccount, UUID(selected['accounts'][0]['id']))
        # Fixture capability supports text; existing domain validates approval.
        from test_domain_support import account
        sample = account(db)
        row.capability_snapshot = sample.capability_snapshot
        row.publishing_enabled = True
        db.commit()
        body = draft_body((row,))
        _, created = call(db, body, lambda s:s.create(body), route='create')
        approve = ApproveCommand(expected_version=1, revision_id=created['revision_id'])
        _, detail = call(db, approve, lambda s:s.approve(UUID(created['id']), approve), route='approve')
        target_id = UUID(detail['targets'][0]['id'])
        target = db.get(SocialPostTarget, target_id)
        token = uuid4()
        target.state, target.lease_token, target.lease_epoch = 'outcome_unknown', token, 1
        target.checkpoint = {'provider_container_id':'fixture-container', 'uncertain':True}
        row.publish_lease_target_id, row.publish_lease_token = target_id, token
        row.publish_lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        attempt = SocialPublishAttempt(id=uuid4(), target_id=target_id, sequence=1, operation_id=uuid4(), operation='publish',
            request_fingerprint='a'*64, lease_epoch=1, dispatch_started_at=datetime.now(timezone.utc), outcome='outcome_unknown',
            receipt={'provider_request_id':'fixture-provider-receipt','intent':{'mutating':True}})
        db.add(attempt)
        db.commit()
        checkpoint, receipt, operation = target.checkpoint, attempt.receipt, attempt.operation_id
        privacy(db, config).receive(signed(config), kind='deauthorization')
        db.refresh(target); db.refresh(attempt); db.refresh(row)
        assert target.state == 'outcome_unknown' and target.checkpoint == checkpoint
        assert attempt.receipt == receipt and attempt.operation_id == operation
        assert row.publish_lease_token == token and row.publish_lease_target_id == target_id
        assert row.connection_state == 'revoked' and not row.publishing_enabled


def test_same_second_actual_postgres_generation_is_ambiguous(privacy_pg,config,graph):
    with Session(privacy_pg) as db:
        connected(db,config,graph)
        owner=db.scalar(select(SocialPrivacyOwnership))
        issued=int(owner.generation_at.timestamp())
        db.rollback()
        out=privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':issued}),kind='deauthorization')
        assert out['state']=='ownership_unresolved' and out['resolution']=='ownership_timestamp_ambiguous'
