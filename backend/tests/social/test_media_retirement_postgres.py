"""Owned Batch15 PostgreSQL, actual complete Alembic chain and controlled I/O."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.deletion import execute_deletion
from social.media.models import SocialMediaDeletion, SocialMediaUpload
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialRevisionAsset
from test_media_payload_retirement import Approved, FenceStorage, command, granted, rows
from test_media_support import ACTOR, ENDPOINT, png


@pytest.fixture
def retirement_pg():
    dsn = os.getenv('B15_MEDIA_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Owned Batch15 media PostgreSQL is not assigned')
    target = urlsplit(dsn)
    if (target.scheme != 'postgresql+psycopg2' or target.hostname != '127.0.0.1'
            or target.port != 55394 or target.username != 'b15_media' or target.password
            or target.path != '/b15_media_test' or target.query or target.fragment):
        raise ValueError('Refused an unowned Batch15 media database')
    database = 'b15_media_' + uuid4().hex
    admin = create_engine(dsn, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(make_url(dsn).set(database=database), pool_size=4)
    # Execute every checked-in revision's real upgrade in Alembic order. No
    # stamp/create_all shortcut, and no implicit production URL or .env load.
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / 'alembic'))
    chain = list(reversed(list(scripts.walk_revisions(base='base', head='a701b15a0001'))))
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        for revision in chain:
            revision.module.upgrade()
    config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture',
        secret_key='fixture', fenced_retirement_enabled=True)
    store = FenceStorage()
    runtime = MediaRuntime(config, store, LocalInspector(config), deletion_authority=Approved())
    try:
        yield engine, runtime
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE ' + database))
        admin.dispose()


def test_pg_chain_and_history_refuse_protocol_mutation_and_downgrade(retirement_pg):
    engine, runtime = retirement_pg
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        identity = granted(svc, runtime.storage)
        operation = command(identity)
        assert execute_deletion(svc, operation).verified_deleted
        assert rows(svc, identity) == (2, 2, 2, 0)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='social_media_deletions'::regclass")).scalar() is True
        assert conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='social_media_deletions'::regclass AND a.grantee=0)")).scalar() is False
    for sql in (
        "UPDATE social_media_uploads SET write_protocol=NULL",
        "UPDATE social_media_uploads SET fenced_copies=0",
        "DELETE FROM social_media_deletions",
        "DELETE FROM social_media_uploads",
        "UPDATE social_media_deletions SET policy_hash=repeat('a',64)",
    ):
        with engine.connect() as conn, pytest.raises(DBAPIError):
            with conn.begin(): conn.execute(text(sql))
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/a701b15a0001_media_payload_retirement.py'
    spec = importlib.util.spec_from_file_location('retirement_ddl', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as conn, pytest.raises(RuntimeError, match='prevents downgrade'):
        with conn.begin(), Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()


def test_pg_lost_put_response_concurrent_retry_and_byte_credit_once(retirement_pg):
    engine, runtime = retirement_pg
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        identity = granted(svc, runtime.storage)
        operation = command(identity)
        runtime.storage.sdk.lose_response = True
        assert execute_deletion(svc, operation).state == 'uncertain'
        assert rows(svc, identity)[2:] == (2 * len(png()), 1)
    entered, release = Event(), Event()
    def pause(params):
        entered.set()
        assert release.wait(5)
    runtime.storage.sdk.before_put = pause
    def run():
        with Session(engine, expire_on_commit=False) as db:
            return execute_deletion(MediaService(db, runtime), operation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        assert entered.wait(5)
        try:
            assert run().state == 'blocked'
        finally:
            release.set()
        assert future.result(5).verified_deleted
    assert run().verified_deleted
    with Session(engine, expire_on_commit=False) as db:
        assert rows(MediaService(db, runtime), identity) == (2, 2, 2, 0)
        with db.begin():
            assert len(list(db.scalars(select(SocialMediaDeletion)))) == 1


def test_pg_original_retirement_archives_before_io_and_prevents_new_reference(retirement_pg):
    from social.contracts import CreatePost
    from social.service import SocialService, SocialError
    engine, runtime = retirement_pg
    with Session(engine, expire_on_commit=False) as db:
        identity = granted(MediaService(db, runtime), runtime.storage, ready=True)
    entered, release = Event(), Event()
    def pause(params):
        entered.set()
        assert release.wait(5)
    runtime.storage.sdk.before_put = pause
    def retire():
        with Session(engine, expire_on_commit=False) as db:
            return execute_deletion(MediaService(db, runtime), command(identity))
    body = CreatePost.model_validate({'title': 'New reference', 'content_type': 'announcement',
        'document': {'master': {'media': [{'asset_id': str(identity)}]}, 'targets': []}})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(retire)
        assert entered.wait(5)
        try:
            with Session(engine, expire_on_commit=False) as db:
                domain = SocialService(db)
                with pytest.raises(SocialError, match='TARGET_VALIDATION_FAILED'):
                    domain.command(actor=ACTOR, route='fixture.reference', key=uuid4(),
                        body=body.model_dump(mode='json'), request_id=uuid4(), action=lambda: domain.create(body))
        finally: release.set()
        assert future.result(5).verified_deleted
    with Session(engine) as db:
        assert list(db.scalars(select(SocialRevisionAsset))) == []


@pytest.mark.parametrize('timing,body', [
    ('BEFORE INSERT', "NEW.policy_hash=repeat('f',64); RETURN NEW;"),
    ('BEFORE INSERT', 'RETURN NULL;'),
])
def test_pg_altered_or_suppressed_admission_never_reaches_storage(retirement_pg, timing, body):
    engine, runtime = retirement_pg
    with engine.begin() as conn:
        conn.execute(text('CREATE FUNCTION b15_alter() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN ' + body + ' END $$'))
        conn.execute(text('CREATE TRIGGER b15_alter ' + timing + ' ON social_media_deletions FOR EACH ROW EXECUTE FUNCTION b15_alter()'))
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        identity = granted(svc, runtime.storage)
        with pytest.raises(Exception):
            execute_deletion(svc, command(identity))
        assert runtime.storage.sdk.puts == []
        assert rows(svc, identity) == (2 * len(png()), 0, 2 * len(png()), 1)
        with db.begin():
            assert list(db.scalars(select(SocialMediaDeletion))) == []


def test_pg_deferred_completion_drift_never_certifies_or_releases_capacity(retirement_pg):
    engine, runtime = retirement_pg
    with engine.begin() as conn:
        conn.execute(text("""CREATE FUNCTION b15_drift() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.state='complete' THEN UPDATE social_media_budgets SET bytes_used=bytes_used+1; END IF;
          RETURN NEW; END $$"""))
        conn.execute(text('CREATE CONSTRAINT TRIGGER b15_drift AFTER UPDATE ON social_media_deletions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b15_drift()'))
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        identity = granted(svc, runtime.storage)
        operation = command(identity)
        from social.service import SocialError
        with pytest.raises(SocialError, match='MEDIA_RETIREMENT_PERSISTENCE_UNCONFIRMED'):
            execute_deletion(svc, operation)
        assert len(runtime.storage.sdk.puts) == 2
        assert rows(svc, identity) == (2 * len(png()), 0, 2 * len(png()), 1)
        with db.begin():
            assert db.get(SocialMediaDeletion, operation.operation_id).state == 'admitted'


def test_pg_retention_age_cannot_be_changed_by_admission_trigger(retirement_pg):
    from datetime import timedelta
    from social.models import SocialMediaAsset
    from social.service import SocialError
    engine, runtime = retirement_pg
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        identity = granted(svc, runtime.storage, ready=True)
        with db.begin():
            db.get(SocialMediaAsset, identity).created_at = svc.now() - timedelta(days=31)
    with engine.begin() as conn:
        conn.execute(text("""CREATE FUNCTION b15_age() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.state='archived' THEN NEW.created_at=clock_timestamp(); END IF; RETURN NEW; END $$"""))
        conn.execute(text('CREATE TRIGGER b15_age BEFORE UPDATE ON social_media_assets FOR EACH ROW EXECUTE FUNCTION b15_age()'))
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        with pytest.raises(SocialError, match='MEDIA_RETIREMENT_PERSISTENCE_UNCONFIRMED'):
            execute_deletion(svc, command(identity, purpose='retention_expiry'))
        assert runtime.storage.sdk.puts == []
