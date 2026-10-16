"""Actual optional role contract on the platforms lane's assigned PostgreSQL."""
from uuid import uuid4
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from social.models import SocialAccount, SocialControls
from social.platform_connections.models import PlatformCredential
from social.platform_budget import SocialPlatformBudget

from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from test_platforms_postgres import platform_pg


@pytest.fixture
def platform_role_pg(platform_pg):
    owner = platform_pg
    role = 'b15_platform_role_' + uuid4().hex
    password = secrets.token_urlsafe(32)
    with Session(owner) as db:
        db.add(SocialControls(id=1, publishing_enabled=False))
        db.commit()
    with owner.begin() as conn:
        schema = conn.execute(text('SELECT current_schema()')).scalar_one()
        conn.execute(text('CREATE ROLE ' + role + ' LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD :password'), {'password': password})
    worker = create_engine(owner.url.set(username=role, password=password), pool_size=1, max_overflow=0,
        hide_parameters=True, connect_args={'options': '-csearch_path=' + schema})
    try:
        yield owner, worker, schema, role
    finally:
        worker.dispose()
        with owner.begin() as conn:
            # The generated role is owned only by this fixture. DROP OWNED
            # removes its scoped grants/policies before the parent schema drops.
            conn.execute(text('DROP OWNED BY ' + role))
            conn.execute(text('DROP ROLE ' + role))
        with owner.connect() as conn:
            assert conn.execute(text('SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)'), {'role': role}).scalar_one()


def test_default_contract_works_with_platform_tables_present_but_denies_access(platform_role_pg):
    owner, worker, schema, role = platform_role_pg
    install_worker_role(owner, role, schema)
    with worker.connect() as conn:
        assert conn.execute(text('SELECT current_user')).scalar_one() == role
    verify_worker_role(worker, role, schema)
    with worker.begin() as conn:
        assert conn.execute(text('SELECT id FROM social_controls FOR UPDATE')).scalar_one() == 1
    for table in ('social_platform_credentials', 'social_platform_budgets', 'social_platform_event_inbox', 'social_platform_oauth_flows', 'social_platform_connection_budgets'):
        with pytest.raises(Exception) as denied:
            with worker.begin() as conn: conn.execute(text('SELECT * FROM ' + table))
        assert getattr(denied.value.orig, 'pgcode', None) == '42501'
    with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema, platforms=True)


def test_optional_contract_is_explicit_idempotent_and_keeps_oauth_denied(platform_role_pg):
    owner, worker, schema, role = platform_role_pg
    install_worker_role(owner, role, schema, platforms=True)
    install_worker_role(owner, role, schema, platforms=True)
    verify_worker_role(worker, role, schema, platforms=True)
    # Narrow verification refuses a login already holding optional authority;
    # it never silently calls the wider contract based on discovered grants.
    with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
    with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    now = datetime.now(timezone.utc)
    account_id, credential_id, event_id = uuid4(), uuid4(), uuid4()
    with Session(owner) as db:
        db.add(SocialAccount(id=account_id, platform='threads', api_product='threads', connection_method='fixture', external_account_id='fixture-role-subject', display_name='Fixture role subject', publishing_enabled=False))
        db.flush()
        db.add(PlatformCredential(id=credential_id, account_id=account_id, platform='threads', encrypted_bundle=b'nonsecret-fixture-envelope', key_version='fixture', access_expires_at=now + timedelta(hours=1), issued_at=now))
        db.add(SocialPlatformBudget(account_id=account_id, enabled=False, access_verified=False, limit_microusd=100))
        db.execute(text("INSERT INTO social_platform_event_inbox(id,provider,dedupe_hash,account_id,event_type,remote_id,event_at) VALUES(:id,'threads',:hash,:account,'fixture_role_event','fixture_remote',:now)"), {'id': event_id, 'hash': 'a' * 64, 'account': account_id, 'now': now})
        db.commit()
    with worker.begin() as conn:
        for table in ('social_platform_credentials', 'social_platform_budgets', 'social_platform_event_inbox'):
            assert conn.execute(text('SELECT count(*) FROM ' + table)).scalar_one() == 1
        assert conn.execute(text('SELECT id FROM social_platform_credentials FOR UPDATE')).scalar_one() == credential_id
        assert conn.execute(text('UPDATE social_platform_budgets SET reserved_microusd=1,version=version+1')).rowcount == 1
        assert conn.execute(text("UPDATE social_platform_event_inbox SET processing_state='processed',processed_at=clock_timestamp()")).rowcount == 1
        assert conn.execute(text('SELECT reserved_microusd,version FROM social_platform_budgets')).one() == (1, 2)
    for sql in ('SELECT * FROM social_platform_oauth_flows', 'SELECT * FROM social_platform_connection_budgets',
                'UPDATE social_platform_credentials SET id=id',
                'UPDATE social_platform_credentials SET encrypted_bundle=encrypted_bundle',
                'UPDATE social_platform_budgets SET enabled=enabled',
                'UPDATE social_platform_event_inbox SET post_id=post_id', 'DELETE FROM social_platform_event_inbox'):
        with pytest.raises(Exception) as denied:
            with worker.begin() as conn: conn.execute(text(sql))
        assert getattr(denied.value.orig, 'pgcode', None) == '42501'
