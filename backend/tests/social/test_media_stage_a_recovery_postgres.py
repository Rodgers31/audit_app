"""Actual PG row closure/restore; explicitly inert inspector, no codec acceptance."""
from contextlib import contextmanager
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import InspectedMedia, LocalInspector
from social.media.recovery import capture_stage_a_rows, encode_rows, restore_stage_a_rows, RecoveryScopeError
from social.media.recovery_packet import publish_stage_a_packet, read_stage_a_packet
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from current_social_schema import upgrade_current_social_runtime
from test_domain_postgres import owned_domain_engine
from test_media_stage_a_recovery import intake
from test_media_support import ACTOR, ENDPOINT, FakeStorage
from test_media_recovery_packet import CONTEXT


@contextmanager
def target():
    with owned_domain_engine() as engine:
        upgrade_current_social_runtime(engine)
        yield engine


@pytest.fixture
def packet_source(monkeypatch):
    # Isolate data/transaction contracts from the emulated child-decoder limit.
    def inspect(self, path, mime, size):
        return InspectedMedia(mime, size, hashlib.sha256(path.read_bytes()).hexdigest(),
            1080, 1080, None, None, {})
    monkeypatch.setattr(LocalInspector, 'inspect', inspect)
    with target() as engine, Session(engine, expire_on_commit=False) as db:
        config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture', secret_key='fixture')
        svc = MediaService(db, MediaRuntime(config, FakeStorage(), LocalInspector(config)))
        io, _, asset, post = intake((svc, None), monkeypatch)
        try: yield svc, asset, post
        finally: io.sdk.close()


def capture(svc, asset, post, *, row_security='off'):
    with svc.db.begin():
        svc.db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        svc.db.execute(text('SET LOCAL row_security = ' + row_security))
        return encode_rows(capture_stage_a_rows(svc.db, ACTOR, asset, post))


def test_real_pg_capture_refuses_rls_filtered_snapshot(packet_source):
    svc, asset, post = packet_source
    with pytest.raises(RecoveryScopeError): capture(svc, asset, post, row_security='on')


def test_actual_cross_schema_incoming_history_refuses_capture(packet_source):
    svc, asset, post = packet_source
    outside = 'capsule_dependency_' + uuid4().hex
    try:
        with svc.db.begin():
            schema = svc.db.scalar(text('SELECT current_schema()'))
            svc.db.execute(text('CREATE SCHEMA ' + outside))
            svc.db.execute(text(f'CREATE TABLE {outside}.history(post_id uuid REFERENCES {schema}.social_posts(id))'))
            svc.db.execute(text(f'INSERT INTO {outside}.history VALUES (:post)'), {'post': post})
        with pytest.raises(RecoveryScopeError): capture(svc, asset, post)
    finally:
        with svc.db.begin(): svc.db.execute(text('DROP SCHEMA ' + outside + ' CASCADE'))


def test_nonempty_migrated_pg_capsule_restores_exact_rows(packet_source):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    with target() as engine:
        with engine.begin() as connection:
            connection.execute(text('SET LOCAL row_security=off'))
            restore_stage_a_rows(connection, raw)
        with Session(engine) as db:
            restored = MediaService(db, svc.runtime)
            assert capture(restored, asset, post) == raw
        # Restore cannot overwrite an existing target, even with identical input.
        with engine.begin() as connection, pytest.raises(RecoveryScopeError):
            connection.execute(text('SET LOCAL row_security=off'))
            restore_stage_a_rows(connection, raw)


def test_pg_packet_binds_the_actual_read_only_snapshot(packet_source, tmp_path):
    svc, asset, post = packet_source
    root = tmp_path / 'approved-existing'; root.mkdir(mode=0o700)
    custody = uuid4()
    with svc.db.begin():
        svc.db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        svc.db.execute(text('SET LOCAL row_security=off'))
        digest = publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR, asset, post, root, custody, CONTEXT)
    _, _, manifest = read_stage_a_packet(root, custody, digest)
    snapshot = manifest['source_snapshot']
    assert snapshot['dialect'] == 'postgresql' and snapshot['read_only'] is True
    assert snapshot['isolation'] == 'repeatable read' and snapshot['row_security'] == 'off'
    assert snapshot['snapshot'] and snapshot['transaction_started_at'] and snapshot['observed_at']
