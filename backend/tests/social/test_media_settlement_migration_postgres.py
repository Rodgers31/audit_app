"""Actual legacy backfill, bounds, private permissions and downgrade protection."""
import importlib.util
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_domain_postgres import pg_engine


def settlement_migration():
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/b73e19a4f602_social_media_write_settlement.py'
    spec = importlib.util.spec_from_file_location('media_settlement_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_schema(engine):
    from test_connections_migration_postgres import connection_migration
    from test_media_migration_postgres import media_migration
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        connection_migration().upgrade()
        media_migration().upgrade()


def test_settlement_empty_upgrade_and_downgrade_preserve_rls(pg_engine):
    legacy_schema(pg_engine)
    with pg_engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        settlement_migration().upgrade()
        columns = {c['name']: c for c in inspect(conn).get_columns('social_media_uploads')}
        assert not columns['grant_renewal_deadline']['nullable']
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='social_media_uploads'::regclass")).scalar()
        assert not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='social_media_uploads'::regclass AND a.grantee=0)")).scalar()
        settlement_migration().downgrade()
        assert 'grant_epoch' not in {c['name'] for c in inspect(conn).get_columns('social_media_uploads')}


def test_legacy_grants_remain_unknown_with_exact_pending_markers(pg_engine):
    legacy_schema(pg_engine)
    ids = []
    with pg_engine.begin() as conn:
        for state, version, released in [('pending', 1, 0), ('inspecting', 1, 0), ('archived', 1, 0), ('ready', 2, 0), ('failed', 2, 0), ('archived', 2, 1)]:
            identity = uuid4(); ids.append((identity, version > 1 or released == 1))
            conn.execute(text("""INSERT INTO social_media_assets (id,storage_provider,bucket,storage_key,original_filename,state,created_by,mime_type,byte_size,sha256,codec_metadata)
                VALUES (:id,'r2','fixture',:key,'fixture.png',:state,:actor,'image/png',100,:sha,'{}')"""),
                {'id': identity, 'key': str(identity), 'state': state, 'actor': uuid4(), 'sha': 'a'*64})
            conn.execute(text("""INSERT INTO social_media_uploads (asset_id,actor_id,initiation_key,request_hash,quarantine_key,declared_mime_type,declared_size,version,expires_at,reservation_released,quarantine_cleaned,reserved_bytes,finalization_settled)
                VALUES (:id,:actor,:key,:hash,:object,'image/png',100,:version,now()+interval '1 day',:released,0,200,0)"""),
                {'id': identity, 'actor': uuid4(), 'key': uuid4(), 'hash': 'b'*64, 'object': 'q/'+str(identity), 'version': version, 'released': released})
        with Operations.context(MigrationContext.configure(conn)):
            settlement_migration().upgrade()
        for identity, pending_released in ids:
            row = conn.execute(text('SELECT * FROM social_media_uploads WHERE asset_id=:id'), {'id': identity}).mappings().one()
            assert row['grant_epoch'] == 1 and row['grant_settled_epoch'] == 0 and row['grant_expires_at'] is None
            assert row['write_quiescence_receipt_hash'] is None and row['pending_released'] == int(pending_released)
            assert row['grant_renewal_deadline'] <= row['created_at'] + __import__('datetime').timedelta(seconds=300)
    for clause in ('grant_epoch=-1', 'grant_settled_epoch=2', 'pending_released=2'):
        with pg_engine.begin() as conn, pytest.raises(IntegrityError):
            conn.execute(text('UPDATE social_media_uploads SET '+clause+' WHERE asset_id=:id'), {'id': ids[0][0]})
    with pg_engine.begin() as conn, Operations.context(MigrationContext.configure(conn)), pytest.raises(RuntimeError, match='history exists'):
        settlement_migration().downgrade()


@pytest.mark.parametrize('version', [1, 2])
def test_migrated_cleaned_ready_recovers_only_after_verified_fresh_delete(pg_engine, version):
    from social.media.config import MediaConfig
    from social.media.inspection import LocalInspector
    from social.media.models import SocialMediaUpload
    from social.media.runtime import MediaRuntime
    from social.media.service import MediaService
    from social.service import SocialError
    from test_media_maintenance import ledger, request_for
    from test_media_support import ACTOR, ENDPOINT, FakeStorage, png, settle_writes

    legacy_schema(pg_engine)
    identity = uuid4()
    storage = FakeStorage()
    content = png()
    digest = hashlib.sha256(content).hexdigest()
    original, quarantine = f'ready/{identity}/original', f'quarantine/{identity}/source'
    storage.objects[original] = (content, 'image/png', digest)
    snapshot = storage.head(original)
    storage.objects[quarantine] = (content, 'image/png', None)
    pending = int(version == 1)
    with pg_engine.begin() as conn:
        conn.execute(text("""INSERT INTO social_media_assets
            (id,storage_provider,bucket,storage_key,original_filename,state,created_by,mime_type,byte_size,sha256,width,height,codec_metadata)
            VALUES (:id,'r2',:bucket,:key,'legacy.png','ready',:actor,'image/png',:size,:sha,64,32,CAST(:metadata AS jsonb))"""),
            {'id': identity, 'bucket': storage.bucket, 'key': original, 'actor': ACTOR, 'size': len(content), 'sha': digest,
             'metadata': json.dumps({'storage_etag': snapshot.etag, 'storage_version': snapshot.version})})
        conn.execute(text("""INSERT INTO social_media_uploads
            (asset_id,actor_id,initiation_key,request_hash,quarantine_key,declared_mime_type,declared_size,version,
             expires_at,reservation_released,quarantine_cleaned,reserved_bytes,finalization_epoch,finalization_settled)
            VALUES (:id,:actor,:command,:hash,:key,'image/png',:size,:version,
                    clock_timestamp()-interval '1 second',0,1,:size,1,1)"""),
            {'id': identity, 'actor': ACTOR, 'command': uuid4(), 'hash': 'a'*64, 'key': quarantine, 'size': len(content), 'version': version})
        for scope in ('global', f'actor:{ACTOR}'):
            conn.execute(text('INSERT INTO social_media_budgets (scope,bytes_used,pending_count) VALUES (:scope,:bytes,:pending)'),
                {'scope': scope, 'bytes': len(content), 'pending': pending})
        with Operations.context(MigrationContext.configure(conn)):
            settlement_migration().upgrade()
        row = conn.execute(text('SELECT * FROM social_media_uploads WHERE asset_id=:id'), {'id': identity}).mappings().one()
        assert row['quarantine_cleaned'] == 1 and row['pending_released'] == 1 - pending
        assert row['grant_epoch'] == 1 and row['grant_settled_epoch'] == 0 and row['grant_expires_at'] is None

    config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket=storage.bucket, access_key='fixture', secret_key='fixture')
    runtime = MediaRuntime(config, storage, LocalInspector(config))
    with Session(pg_engine, expire_on_commit=False) as db:
        service = MediaService(db, runtime)
        with pytest.raises(SocialError, match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
            service.reconcile(ACTOR, identity, request_for(service, identity), uuid4())
        assert service.cleanup() == 0 and ledger(service) == (len(content), pending)
        assert 'delete' not in storage.operations
        assert settle_writes(service, identity).state == 'ready'
        assert ledger(service) == (len(content), pending)
        with db.begin():
            assert db.get(SocialMediaUpload, identity).quarantine_cleaned == 0
        assert service.cleanup() == 1 and service.cleanup() == 0
        assert ledger(service) == (len(content), 0)
        assert storage.objects == {original: (content, 'image/png', digest)}
        assert service.preview(identity).asset.sha256 == digest
