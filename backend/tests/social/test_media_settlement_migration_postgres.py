"""Actual legacy backfill, bounds, private permissions and downgrade protection."""
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
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
