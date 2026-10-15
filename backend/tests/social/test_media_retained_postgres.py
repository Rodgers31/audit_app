"""Retained recovery on real migrated PostgreSQL, without external storage."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.retention import recover_retained, retain_ready
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.media.storage import StorageFailure
from social.models import SocialMediaAsset
from social.service import SocialError
from test_domain_postgres import pg_engine
from test_media_migration_postgres import upgrade, retained_migration
from test_media_support import ACTOR, ENDPOINT, FakeStorage, intent, png


def fixture(engine):
    storage = FakeStorage()
    storage.retained_create_only = True
    cfg = MediaConfig(enabled=True, retained_writes_enabled=True,
        endpoint=ENDPOINT, bucket=storage.bucket, access_key='fixture', secret_key='fixture')
    return MediaRuntime(cfg, storage, LocalInspector(cfg))


def ready(engine, runtime):
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
        runtime.storage.objects[runtime.storage.last_key] = (png(), 'image/png', None)
        return svc.complete(ACTOR, grant.asset.id, uuid4(), 1, uuid4())


def test_retained_additive_migration_and_empty_downgrade(pg_engine):
    upgrade(pg_engine)
    with pg_engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        assert inspect(conn).get_columns('social_media_uploads')[-1]['name'] == 'retained_write_fence'
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='social_media_uploads'::regclass")).scalar()
        assert not conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='social_media_uploads'::regclass AND a.grantee=0)")).scalar()
        retained_migration().downgrade()
        assert 'retained_write_fence' not in {c['name'] for c in inspect(conn).get_columns('social_media_uploads')}


@pytest.mark.parametrize('clause', [
    'retained_write_fence=NULL', "retained_write_fence='{}'", 'reservation_released=1',
    'quarantine_cleaned=1', 'grant_settled_epoch=grant_epoch', 'reserved_bytes=declared_size',
    'pending_released=0', 'finalization_settled=0',
])
def test_retained_database_cannot_clear_fence_or_release_reserved_copies(pg_engine, clause):
    upgrade(pg_engine)
    result = ready(pg_engine, fixture(pg_engine))
    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            conn.execute(text('UPDATE social_media_uploads SET '+clause+' WHERE asset_id=:id'), {'id':result.id})
    with pg_engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        with pytest.raises(RuntimeError, match='history'):
            retained_migration().downgrade()


def test_concurrent_retention_charges_once_and_cleanup_never_touches_keys(pg_engine):
    upgrade(pg_engine)
    runtime = fixture(pg_engine)
    # First complete without retained mode, then race two independent DB sessions.
    original = MediaRuntime(replace(runtime.config, retained_writes_enabled=False), runtime.storage, runtime.inspector)
    result = ready(pg_engine, original)
    def retain(_):
        with Session(pg_engine, expire_on_commit=False) as db:
            try:
                return retain_ready(MediaService(db, runtime), ACTOR, result.id, 2, uuid4()).state
            except SocialError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(retain, range(2)))
    assert 'ready' in outcomes and set(outcomes) <= {'ready','MEDIA_INSPECTION_BUSY'}
    with Session(pg_engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        assert retain_ready(svc, ACTOR, result.id, 2, uuid4()).state == 'ready'
        with db.begin():
            budgets = list(db.scalars(select(SocialMediaBudget)))
            assert all(b.pending_count == 0 and b.bytes_used == 2*len(png()) for b in budgets)
            db.get(SocialMediaUpload, result.id).expires_at = svc.now()
        assert svc.cleanup() == 0
        assert svc.backlog().retained_fences == 1
    assert len(runtime.storage.objects) == 2 and 'delete' not in runtime.storage.operations


def test_lost_finalization_response_recovers_on_migrated_postgresql(pg_engine):
    upgrade(pg_engine)
    runtime = fixture(pg_engine)
    with Session(pg_engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
        runtime.storage.objects[runtime.storage.last_key] = (png(),'image/png',None)
        finalize = runtime.storage.finalize
        def lost(*args):
            finalize(*args)
            raise StorageFailure('lost response')
        runtime.storage.finalize = lost
        with pytest.raises(SocialError, match='MEDIA_FINALIZATION_UNKNOWN'):
            svc.complete(ACTOR, grant.asset.id, uuid4(), 1, uuid4())
        runtime.storage.finalize = finalize
        with db.begin():
            upload = db.get(SocialMediaUpload, grant.asset.id)
            db.get(SocialMediaAsset, grant.asset.id).lease_expires_at = svc.now() - timedelta(seconds=1)
            scope = dict(expected_version=upload.version, expected_grant_epoch=upload.grant_epoch,
                         expected_finalization_epoch=upload.finalization_epoch)
        result = recover_retained(svc, ACTOR, grant.asset.id, scope, uuid4())
        assert result.state == 'ready'
        with db.begin():
            assert db.get(SocialMediaBudget, 'global').pending_count == 0
            assert db.get(SocialMediaBudget, 'global').bytes_used == 2*len(png())


def test_downgrade_serializes_retained_history_check_with_concurrent_writer(pg_engine):
    from threading import Event
    import time
    from sqlalchemy import event
    upgrade(pg_engine)
    runtime = fixture(pg_engine)
    result = ready(pg_engine, MediaRuntime(replace(runtime.config,retained_writes_enabled=False),
                                          runtime.storage,runtime.inspector))
    observed = Event()
    migration_pid = []
    def before_statement(conn, cursor, statement, *args):
        if statement.startswith(('LOCK TABLE social_media_uploads','DROP TRIGGER social_retained_fence_immutable')):
            observed.set()
    event.listen(pg_engine,'before_cursor_execute',before_statement)
    writer = pg_engine.connect()
    transaction = writer.begin()
    writer.execute(text("UPDATE social_media_uploads SET retained_write_fence='{}',pending_released=1 WHERE asset_id=:id"),{'id':result.id})
    def downgrade():
        with pg_engine.begin() as conn:
            migration_pid.append(conn.execute(text('SELECT pg_backend_pid()')).scalar())
            try:
                with Operations.context(MigrationContext.configure(conn)):
                    retained_migration().downgrade()
            except RuntimeError as error:
                assert 'history' in str(error)
                return 'refused'
            return 'dropped'
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(downgrade)
            try:
                assert observed.wait(5), 'Downgrade never reached its serializing DDL/lock'
                deadline = time.monotonic()+5
                with pg_engine.connect() as observer:
                    while time.monotonic()<deadline:
                        waiting = observer.execute(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"), {'pid':migration_pid[0]}).scalar()
                        if waiting: break
                        time.sleep(0.01)
                    assert waiting, 'Downgrade was not actually blocked by the in-flight writer'
                transaction.commit()
                assert future.result(timeout=5) == 'refused', 'Downgrade erased concurrently committed retained history'
            finally:
                if transaction.is_active:transaction.rollback()
    finally:
        writer.close()
        event.remove(pg_engine,'before_cursor_execute',before_statement)
    with pg_engine.begin() as conn:
        assert 'retained_write_fence' in {c['name'] for c in inspect(conn).get_columns('social_media_uploads')}
        assert conn.execute(text('SELECT retained_write_fence FROM social_media_uploads WHERE asset_id=:id'),{'id':result.id}).scalar() == '{}'
