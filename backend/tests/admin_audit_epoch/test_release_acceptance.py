"""Owned native release controls; no production certification or effects."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from tests.admin_audit_epoch.test_durable_storage import (
    ACTOR, durable, fields, insert, private_unavailable,
)


@pytest.mark.parametrize('principal', ['reader', 'audit_log_reader', 'audit_log_writer'])
@pytest.mark.parametrize('flag', ['CREATEROLE', 'CREATEDB', 'REPLICATION'])
def test_privileged_role_drift_refuses_private_route(durable, principal, flag):
    owner, factory, client, _, _, _, _, admin, reader_name, _ = durable
    insert(factory)
    role = reader_name if principal == 'reader' else principal
    try:
        with admin.connect() as c:
            c.execute(text(f'ALTER ROLE "{role}" {flag}'))
        private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    finally:
        with admin.connect() as c:
            c.execute(text(f'ALTER ROLE "{role}" NO{flag}'))
    assert client.get('/api/v1/admin/audit-log?days=0').status_code == 200
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance')) == 1


@pytest.mark.parametrize('group', ['audit_log_reader', 'audit_log_writer'])
def test_audit_group_login_or_parent_authority_drift_refuses(durable, group):
    _, factory, client, _, _, _, _, admin, *_ = durable
    insert(factory)
    try:
        with admin.connect() as c:
            c.execute(text(f'ALTER ROLE {group} LOGIN'))
        private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    finally:
        with admin.connect() as c:
            c.execute(text(f'ALTER ROLE {group} NOLOGIN'))
    try:
        with admin.connect() as c:
            c.execute(text(f'GRANT pg_monitor TO {group}'))
        private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    finally:
        with admin.connect() as c:
            c.execute(text(f'REVOKE pg_monitor FROM {group}'))
    assert client.get('/api/v1/admin/audit-log?days=0').status_code == 200


@pytest.mark.parametrize('privilege,resource,group', [
    ('INSERT', 'TABLE public.admin_audit_provenance', 'audit_log_writer'),
    ('UPDATE(certified)', 'TABLE public.admin_audit_storage', 'audit_log_writer'),
    ('UPDATE', 'TABLE public.admin_audit_log', 'audit_log_writer'),
    ('INSERT(id)', 'TABLE public.admin_audit_log', 'audit_log_writer'),
    ('UPDATE', 'SEQUENCE public.admin_audit_log_id_seq', 'audit_log_writer'),
    ('SELECT', 'SEQUENCE public.admin_audit_log_id_seq', 'audit_log_writer'),
    ('CREATE', 'SCHEMA public', 'audit_log_writer'),
    ('REFERENCES', 'TABLE public.admin_audit_log', 'audit_log_reader'),
    ('REFERENCES', 'TABLE public.admin_audit_log', 'reader-login'),
])
def test_effective_group_authority_drift_refuses(durable, privilege, resource, group):
    owner, factory, client, _, _, _, _, _, reader_name, _ = durable
    if group == 'reader-login':
        group = '"' + reader_name + '"'
    insert(factory)
    try:
        with owner.begin() as c:
            c.execute(text(f'GRANT {privilege} ON {resource} TO {group}'))
        private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    finally:
        with owner.begin() as c:
            c.execute(text(f'REVOKE {privilege} ON {resource} FROM {group}'))
    assert client.get('/api/v1/admin/audit-log?days=0').status_code == 200


def test_empty_legacy_and_continuously_captured_history_admit(durable):
    owner, factory, client, *_ = durable
    first = client.get('/api/v1/admin/audit-log?days=0')
    assert first.status_code == 200
    assert first.json()['total'] == 0
    insert(factory)
    assert client.get('/api/v1/admin/audit-log?days=0').json()['total'] == 1
    # The earlier empty population remains empty after a new committed write.
    old = client.get('/api/v1/admin/audit-log', params={'days': 0, **fields(first.json())})
    assert old.status_code == 200 and old.json()['total'] == 0
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance')) == 1


def test_more_than_64_subtransactions_capture_only_root_xid(durable):
    owner, factory, client, *_ = durable
    with factory() as db:
        root = db.scalar(text('SELECT pg_current_xact_id()::text'))
        for i in range(70):
            with db.begin_nested():
                db.execute(text("INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('subxid','etl.trigger','{}',now())"))
        db.commit()
    with owner.connect() as c:
        assert c.execute(text('SELECT DISTINCT root_xid::text FROM admin_audit_provenance')).all() == [(root,)]
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance')) == 70
    first = client.get('/api/v1/admin/audit-log?days=0&page_size=100')
    assert first.status_code == 200 and first.json()['total'] == 70


@pytest.mark.parametrize('xid,snapshot,visible', [
    ('4294967294', '4294967295:4294967298:4294967296', True),
    ('4294967295', '4294967295:4294967298:4294967296', True),
    ('4294967296', '4294967295:4294967298:4294967296', False),
    ('4294967297', '4294967295:4294967298:4294967296', True),
    ('4294967298', '4294967295:4294967298:4294967296', False),
])
def test_actual_xid8_visibility_across_32_bit_boundary(durable, xid, snapshot, visible):
    # Native PostgreSQL semantics with explicit xid8 operands, not a claim of
    # natural rollover or historical custody from resetting a cluster.
    owner, *_ = durable
    with owner.connect() as c:
        assert c.scalar(text('SELECT pg_visible_in_snapshot(CAST(:x AS xid8),CAST(:s AS pg_snapshot))'),
                        {'x': xid, 's': snapshot}) is visible


@pytest.mark.parametrize('writer', ['general-helper', 'users-provider', 'dispatch'])
def test_actual_application_writer_paths_capture_root_and_keep_ownership(durable, monkeypatch, writer):
    import database
    owner, _, client, *_ = durable
    factory = sessionmaker(bind=owner)
    monkeypatch.setattr(database, 'SessionLocal', factory)
    if writer == 'dispatch':
        from admin_etl_dispatch import TriggerBody, accept
        from admin_etl_dispatch_worker import register_worker
        monkeypatch.setenv('ADMIN_ETL_DISPATCH_ENABLED', 'true')
        monkeypatch.setenv('ADMIN_ETL_DISPATCH_SOURCES', 'oag')
        generation = register_worker(factory)
        with factory() as db:
            root = db.scalar(text('SELECT pg_current_xact_id()::text'))
            receipt = accept(db, ACTOR, 'oag', TriggerBody(dry_run=True, dispatch_generation=str(generation)), str(uuid4()))
        with owner.connect() as c:
            assert c.execute(text('SELECT p.root_xid::text FROM admin_audit_provenance p JOIN etl_dispatch_commands d ON d.audit_id=p.audit_id WHERE d.id=:id'),
                             {'id': receipt.command.id}).one() == (root,)
    else:
        if writer == 'general-helper':
            from utils.audit import record_admin_action
            action = 'etl.trigger'
        else:
            from admin_users_provider import record_admin_action
            action = 'users.update_roles'
        with factory() as caller:
            caller.execute(text("INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('rollback','etl.trigger','{}',now())"))
            result = record_admin_action(caller, actor=ACTOR, action=action,
                                         target_id='inert', payload={'access_token': 'INERT_SECRET', 'roles': ['admin']})
            if writer == 'users-provider':
                assert result is True
            caller.rollback()
    response = client.get('/api/v1/admin/audit-log?days=0')
    assert response.status_code == 200 and response.json()['total'] == 1
    assert 'INERT_SECRET' not in response.text
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log')) == 1
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance')) == 1
        assert int(c.scalar(text('SELECT root_xid::text FROM admin_audit_provenance'))) > 2**32


def test_actual_reconciliation_core_insert_captures_root(durable):
    from test_batch9_reconciliation import legacy, signed
    from seeding.reconciliation import make_plan, apply_plan
    owner, _, client, reader, writer, _, url, admin, *_ = durable
    name = owner.url.database
    # The real operator requires sole target-session custody; close pooled
    # probes before retaining its one backend. These are owned fixture engines.
    for engine in (owner, reader, writer):
        engine.dispose()
    operator = create_engine(url, poolclass=NullPool)
    factory = sessionmaker(bind=operator)
    connection = None
    errors = []
    def admission(allowed):
        with admin.connect() as c:
            c.execute(text(f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS {"true" if allowed else "false"}'))
    try:
        connection = operator.connect()
        connection.execute(text('SET search_path = public'))
        connection.execute(text("SET TimeZone = 'UTC'"))
        connection.commit()
        db = SimpleNamespace(factory=factory, connection=connection, admission=admission)
        selected = legacy(db)
        policy, evidence, _ = signed(db, selected)
        admission(False)
        plan = make_plan(connection, policy, evidence)
        result = apply_plan(connection, policy, evidence, plan)
        assert result['status'] == 'applied'
        row = connection.execute(text('SELECT a.action,p.root_xid::text FROM admin_audit_log a JOIN admin_audit_provenance p ON p.audit_id=a.id')).one()
        assert row[0] == 'seeding.reconcile' and int(row[1]) > 2**32
        connection.rollback()
    except BaseException as error:
        errors.append(error)
    finally:
        for cleanup in (lambda: connection.close() if connection is not None else None,
                        operator.dispose, lambda: admission(True)):
            try:
                cleanup()
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup('Owned operator rehearsal or cleanup failed', errors)
    response = client.get('/api/v1/admin/audit-log?days=0')
    assert response.status_code == 200 and response.json()['total'] == 1


def test_external_incarnation_revoke_refuses_retained_and_fresh_pages(durable, monkeypatch):
    _, factory, client, *_ = durable
    insert(factory)
    first = client.get('/api/v1/admin/audit-log?days=0').json()
    monkeypatch.setenv('ADMIN_AUDIT_INCARNATION', str(uuid4()))
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    private_unavailable(client.get('/api/v1/admin/audit-log', params={'days': 0, **fields(first)}))
