"""Actual additive DDL and locks on the explicitly assigned disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_domain_postgres import pg_engine


def media_migration():
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/a42b86e1d310_social_private_media_intake.py'
    spec = importlib.util.spec_from_file_location('social_media_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade(engine):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            from test_connections_migration_postgres import connection_migration
            connection_migration().upgrade()
            media_migration().upgrade()


def test_media_upgrade_rls_no_public_grants_empty_downgrade(pg_engine):
    upgrade(pg_engine)
    with pg_engine.begin() as conn:
        tables = dict(conn.execute(text("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'" )).all())
        assert len(tables) == 16 and all(tables.values())
        for table in media_migration().TABLES:
            assert not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name': table}).scalar()
        assert inspect(conn).get_foreign_keys('social_media_uploads')[0]['referred_table'] == 'social_media_assets'
        with Operations.context(MigrationContext.configure(conn)):
            media_migration().downgrade()
        assert len(inspect(conn).get_table_names()) == 14


def test_media_budget_constraint_and_recorded_history_prevent_destructive_downgrade(pg_engine):
    upgrade(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO social_media_budgets(scope,bytes_used,pending_count) VALUES ('global',0,0)"))
    with pg_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin():
                conn.execute(text("UPDATE social_media_budgets SET bytes_used=-1 WHERE scope='global'"))
        with pytest.raises(RuntimeError, match='history exists'):
            with conn.begin():
                with Operations.context(MigrationContext.configure(conn)):
                    media_migration().downgrade()
    with pg_engine.begin() as conn:
        assert len(inspect(conn).get_table_names()) == 16


def test_media_intent_race_reserves_once_in_actual_postgresql(pg_engine):
    from social.media.config import MediaConfig
    from social.media.inspection import LocalInspector
    from social.media.runtime import MediaRuntime
    from social.media.service import MediaService
    from social.media.models import SocialMediaBudget, SocialMediaUpload
    from test_media_support import FakeStorage, ENDPOINT, ACTOR, png, intent
    upgrade(pg_engine)
    config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fake', secret_key='fake')
    key = uuid4()
    def create_once(_):
        with Session(pg_engine, expire_on_commit=False) as db:
            runtime = MediaRuntime(config, FakeStorage(), LocalInspector(config))
            return MediaService(db, runtime).initiate(ACTOR, key, intent(), uuid4()).asset.id
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_once, range(2)))
    assert results[0] == results[1]
    with Session(pg_engine) as db:
        assert len(list(db.scalars(select(SocialMediaUpload)))) == 1
        budgets = list(db.scalars(select(SocialMediaBudget)))
        assert len(budgets) == 2
        assert all(b.bytes_used == 2 * len(png()) and b.pending_count == 1 for b in budgets)
