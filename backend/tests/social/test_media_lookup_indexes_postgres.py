"""Actual PostgreSQL DDL, retention and selective-query plans; local target only."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from test_domain_postgres import pg_engine
from test_media_lookup_indexes import LOOKUPS, assert_lookup_indexes


def index_migration():
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/a756b20a0001_media_lookup_indexes.py'
    spec = importlib.util.spec_from_file_location('media_lookup_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(connection, direction):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(index_migration(), direction)()


def retained(connection):
    return {
        'rows': {table: connection.scalar(text("SELECT md5(COALESCE(string_agg(to_jsonb(t)::text,chr(10) ORDER BY to_jsonb(t)::text),'')) FROM "+table+' t')) for table in LOOKUPS},
        'tables': connection.execute(text("SELECT relname,relowner,relrowsecurity,relforcerowsecurity,relacl::text FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r' ORDER BY relname")).all(),
        'triggers': connection.execute(text("SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid IN ('social_media_assets'::regclass,'social_revision_assets'::regclass) ORDER BY tgname")).all(),
    }


def seed(connection):
    # Synthetic local rows only. Target is selective; no provider/storage I/O.
    connection.execute(text("""INSERT INTO social_media_assets(id,parent_asset_id,storage_provider,bucket,storage_key,original_filename,codec_metadata,state,created_by)
      SELECT md5('asset-'||g)::uuid,NULL,'fixture','fixture',g::text,'fixture.png','{}','pending','00000000-0000-4000-8000-000000000001'::uuid
      FROM generate_series(1,20000) g"""))
    connection.execute(text("UPDATE social_media_assets SET parent_asset_id=md5('asset-1')::uuid WHERE id IN (md5('asset-19999')::uuid,md5('asset-20000')::uuid)"))
    connection.execute(text("""INSERT INTO social_posts(id,origin_type,creation_method,content_type,title,editorial_state,created_by)
      VALUES (md5('post')::uuid,'manual','admin','announcement','Synthetic history','draft','00000000-0000-4000-8000-000000000001')"""))
    connection.execute(text("""INSERT INTO social_post_revisions(id,post_id,revision_no,document,evidence_snapshot,content_hash,created_by)
      SELECT md5('revision-'||g)::uuid,md5('post')::uuid,g,'{}','[]',repeat('a',64),'00000000-0000-4000-8000-000000000001'::uuid FROM generate_series(1,20000) g"""))
    connection.execute(text("""INSERT INTO social_revision_assets(revision_id,asset_id)
      SELECT md5('revision-'||g)::uuid,md5('asset-'||CASE WHEN g%1000=0 THEN 1 ELSE g END)::uuid FROM generate_series(1,20000) g"""))
    for table in ['social_media_assets','social_revision_assets','social_post_revisions','social_posts']:
        connection.execute(text('ANALYZE '+table))


QUERIES = {
    'reference_count': 'SELECT count(*) FROM social_revision_assets WHERE asset_id=:asset',
    'reference_exists': 'SELECT asset_id FROM social_revision_assets WHERE asset_id=:asset LIMIT 1',
    'parent_exists': 'SELECT id FROM social_media_assets WHERE parent_asset_id=:asset LIMIT 1',
    'usage_page': '''SELECT p.id,p.title,r.id,r.revision_no FROM social_posts p JOIN social_post_revisions r ON r.post_id=p.id
      JOIN social_revision_assets a ON a.revision_id=r.id WHERE a.asset_id=:asset ORDER BY r.created_at DESC,r.id LIMIT 20 OFFSET 0''',
}


def plans(connection):
    asset = connection.scalar(text("SELECT md5('asset-1')::uuid"))
    result = {}
    for name, query in QUERIES.items():
        params = {'asset': asset}
        result[name] = {'rows': connection.execute(text(query), params).all(),
                        'plan': connection.scalar(text('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query), params)[0]}
    return result


def nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from nodes(child)


def test_pg_reverse_lookup_upgrade_downgrade_preserves_history(pg_engine):
    with pg_engine.begin() as conn:
        seed(conn)
    with pg_engine.begin() as conn:
        baseline = retained(conn)
        before = plans(conn)
        with pytest.raises(AssertionError): assert_lookup_indexes(conn)
    with pg_engine.begin() as conn:
        migrate(conn, 'upgrade')
    # Production requests see committed DDL and a new transaction/snapshot.
    with pg_engine.begin() as conn:
        assert_lookup_indexes(conn)
        assert retained(conn) == baseline
        after = plans(conn)
        for name in before:
            if name == 'parent_exists':
                # LIMIT 1 has no ordering; either matching child's ID is valid.
                assert bool(after[name]['rows']) == bool(before[name]['rows'])
            else:
                assert after[name]['rows'] == before[name]['rows']
            used = {n.get('Index Name') for n in nodes(after[name]['plan']['Plan'])}
            required = 'ix_social_asset_parent' if name == 'parent_exists' else 'ix_social_revision_asset_lookup'
            assert required in used, (name, after[name]['plan'])
            print('LOOKUP_PLAN', name, {'before': before[name]['plan'], 'after': after[name]['plan']})
        assert len(after['usage_page']['rows']) == 20
        assert after['reference_count']['rows'][0][0] == 21
    with pg_engine.begin() as conn:
        migrate(conn, 'downgrade')
    with pg_engine.begin() as conn:
        assert retained(conn) == baseline
        with pytest.raises(AssertionError): assert_lookup_indexes(conn)
    with pg_engine.begin() as conn:
        migrate(conn, 'upgrade')
    with pg_engine.begin() as conn:
        assert_lookup_indexes(conn)
        assert retained(conn) == baseline


def test_pg_second_index_lock_timeout_rolls_back_first_index(pg_engine):
    with pg_engine.begin() as blocker:
        blocker.execute(text('LOCK TABLE social_media_assets IN ACCESS EXCLUSIVE MODE'))
        with pytest.raises(DBAPIError, match='lock timeout'):
            with pg_engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout='100ms'"))
                migrate(conn, 'upgrade')
    with pg_engine.connect() as conn:
        assert not any(i['column_names'][0] == 'asset_id' for i in inspect(conn).get_indexes('social_revision_assets'))
        assert not any(i['column_names'][0] == 'parent_asset_id' for i in inspect(conn).get_indexes('social_media_assets'))
