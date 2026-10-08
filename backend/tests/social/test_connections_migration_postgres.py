"""Actual encrypted-connection DDL, private permissions and account FK contract."""
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from test_domain_postgres import pg_engine


CURRENT_CONNECTION_DESCENDANTS = (
    'a42b86e1d310_social_private_media_intake.py',
    'b73e19a4f602_social_media_write_settlement.py',
    'd8f4a619b203_social_privacy_receipts.py',
)


def _migration(filename):
    path = Path(__file__).resolve().parents[2] / 'alembic/versions' / filename
    spec = importlib.util.spec_from_file_location('social_connection_' + filename, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connection_migration():
    return _migration('c96d13e2f411_social_meta_credentials.py')


def upgrade(engine, *, current=False):
    """Historical DDL by default; current ORM behavior needs its full chain."""
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            connection_migration().upgrade()
            if current:
                for filename in CURRENT_CONNECTION_DESCENDANTS:
                    _migration(filename).upgrade()


def test_connection_ddl_rls_account_fk_empty_downgrade(pg_engine):
    upgrade(pg_engine)
    with pg_engine.begin() as conn:
        tables = dict(conn.execute(text("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'")).all())
        assert len(tables) == 14 and all(tables.values())
        for table in connection_migration().TABLES:
            assert not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name': table}).scalar()
        fk = [f for f in inspect(conn).get_foreign_keys('social_accounts') if f['name'] == 'fk_social_account_credential']
        assert len(fk) == 1 and fk[0]['referred_table'] == 'social_credentials'
        with Operations.context(MigrationContext.configure(conn)):
            connection_migration().downgrade()
        assert len(inspect(conn).get_table_names()) == 12


def test_connection_commands_execute_on_actual_migration_and_history_blocks_downgrade(pg_engine):
    from test_connections_support import svc, start, complete, select_asset, FakeGraph, REDIRECT
    from social.connections.config import MetaConfig
    from social.connections.models import SocialCredential
    from social.models import SocialAccount
    from cryptography.fernet import Fernet
    from uuid import UUID
    upgrade(pg_engine, current=True)
    config = MetaConfig(enabled=True, app_configuration_validated=True, app_id='123', app_secret='fake', redirect_uris=(REDIRECT,), access_mode='owned_standard', active_key_version='v1', encryption_keys={'v1': Fernet.generate_key().decode()})
    with Session(pg_engine, expire_on_commit=False) as db:
        service = svc(db, config, FakeGraph())
        flow, state = start(service)
        complete(service, state)
        result = select_asset(service, UUID(flow['flow_id']))
        assert len(result['accounts']) == 2
        assert all(not a['publishing_enabled'] and not a['capabilities']['adapter_available'] for a in result['accounts'])
        credential_ids = set(db.scalars(select(SocialAccount.credential_id)))
        assert len(credential_ids) == 1
        assert len(list(db.scalars(select(SocialCredential)))) == 2
    with pg_engine.connect() as conn:
        # Exercise the current model above, then remove only empty descendants
        # through their real downgrades before testing historical connection DDL.
        with conn.begin(), Operations.context(MigrationContext.configure(conn)):
            for filename in reversed(CURRENT_CONNECTION_DESCENDANTS):
                _migration(filename).downgrade()
        with pytest.raises(RuntimeError, match='history exists'):
            with conn.begin():
                with Operations.context(MigrationContext.configure(conn)):
                    connection_migration().downgrade()
        with conn.begin():
            assert len(inspect(conn).get_table_names()) == 14


def test_account_listing_projects_only_safe_ui_fields(pg_engine):
    from sqlalchemy import event
    from social.service import SocialService
    upgrade(pg_engine)
    queries = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(pg_engine, 'before_cursor_execute', capture)
    try:
        with Session(pg_engine) as db:
            assert SocialService(db).accounts() == {'accounts': []}
    finally:
        event.remove(pg_engine, 'before_cursor_execute', capture)
    selection = next(sql for sql in queries if 'FROM social_accounts' in sql)
    assert 'credential_id' not in selection and 'rate_state' not in selection and 'publish_lease_token' not in selection
