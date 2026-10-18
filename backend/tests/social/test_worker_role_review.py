"""PR677 review regressions on disposable, scoped role fixtures only."""
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from social.worker import __main__ as worker_cli, role_admin
from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from test_worker_role_postgres import role_database


@pytest.mark.parametrize('privilege', ['schema_usage', 'database_connect', 'database_temp'])
@pytest.mark.parametrize('installed', [False, True])
def test_schema_database_delegation_refuses(role_database, privilege, installed):
    owner, worker, schema, role = role_database
    if installed: install_worker_role(owner, role, schema)
    grant, revoke = {
        'schema_usage': (f'GRANT USAGE ON SCHEMA {schema} TO {role} WITH GRANT OPTION',
                         f'REVOKE GRANT OPTION FOR USAGE ON SCHEMA {schema} FROM {role}'),
        'database_connect': (f'GRANT CONNECT ON DATABASE social_domain_test TO {role} WITH GRANT OPTION',
                             f'REVOKE CONNECT ON DATABASE social_domain_test FROM {role}'),
        'database_temp': (f'GRANT TEMP ON DATABASE social_domain_test TO {role} WITH GRANT OPTION',
                          f'REVOKE TEMP ON DATABASE social_domain_test FROM {role}'),
    }[privilege]
    try:
        with owner.begin() as conn: conn.execute(text(grant))
        with pytest.raises(WorkerRoleError):
            (verify_worker_role(worker, role, schema) if installed else install_worker_role(owner, role, schema))
        if not installed:
            with owner.connect() as conn:
                assert not conn.execute(text("SELECT has_table_privilege(:role,'social_controls','SELECT')"), {'role':role}).scalar()
    finally:
        with owner.begin() as conn: conn.execute(text(revoke))


@pytest.mark.parametrize('installed', [False, True])
def test_explicit_function_default_grant_refuses(role_database, installed):
    owner, worker, schema, role = role_database
    if installed: install_worker_role(owner, role, schema)
    try:
        with owner.begin() as conn:
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT EXECUTE ON FUNCTIONS TO {role}'))
        with pytest.raises(WorkerRoleError):
            (verify_worker_role(worker, role, schema) if installed else install_worker_role(owner, role, schema))
        if not installed:
            with owner.connect() as conn:
                assert not conn.execute(text("SELECT has_table_privilege(:role,'social_controls','SELECT')"), {'role':role}).scalar()
    finally:
        with owner.begin() as conn:
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE EXECUTE ON FUNCTIONS FROM {role}'))


@pytest.mark.parametrize('cli', [worker_cli, role_admin])
@pytest.mark.parametrize('initial,cleanup', [('success','interrupt'), ('failure','interrupt'),
    ('interrupt','interrupt'), ('interrupt','failure')])
def test_interrupt_precedence_in_cleanup_is_private(monkeypatch, capsys, caplog, cli, initial, cleanup):
    calls = []
    def dispose():
        calls.append('dispose')
        if cleanup == 'interrupt': raise KeyboardInterrupt('PRIVATE_CLEANUP_SQL')
        raise RuntimeError('PRIVATE_CLEANUP_SQL')
    monkeypatch.setenv('INERT_REVIEW_DSN', 'postgresql://inert:PRIVATE_DSN@localhost/inert')
    monkeypatch.setattr(cli, 'create_worker_engine', lambda config: SimpleNamespace(dispose=dispose))
    def verify(*args):
        if initial == 'interrupt': raise KeyboardInterrupt('PRIVATE_VERIFY_SQL')
        if initial == 'failure': raise RuntimeError('PRIVATE_VERIFY_SQL')
    monkeypatch.setattr(cli, 'verify_worker_role', verify)
    if cli is worker_cli:
        class Repository:
            def __init__(self, *args): pass
        class Worker:
            def __init__(self, *args, **kwargs): pass
            def stop(self): pass
            async def run(self, **kwargs): pass
            async def close(self): pass
        monkeypatch.setattr(cli, 'QueueRepository', Repository)
        monkeypatch.setattr(cli, 'SocialWorker', Worker)
        args = ['--worker-role','inert_worker','--once']
    else: args = ['--role','inert_worker','--verify']
    with caplog.at_level(logging.ERROR):
        try: result = cli.main(['--database-url-env','INERT_REVIEW_DSN', *args])
        except KeyboardInterrupt: pytest.fail('Cleanup interrupt escaped')
    assert result == 130 and calls == ['dispose']
    output = capsys.readouterr()
    assert 'PRIVATE_' not in output.out + output.err + caplog.text
    assert 'interrupted' in (output.out + caplog.text)


@pytest.mark.parametrize('failure', ['worker_close', 'signal_removal', 'native_exit', 'signal_interrupt'])
def test_native_interrupt_drains_owned_cleanup_before_exit130(monkeypatch, caplog, failure):
    events = []
    monkeypatch.setenv('INERT_REVIEW_DSN', 'postgresql://inert@localhost/inert')
    monkeypatch.setattr(worker_cli, 'create_worker_engine', lambda config: SimpleNamespace(dispose=lambda:events.append('dispose')))
    monkeypatch.setattr(worker_cli, 'verify_worker_role', lambda *args: None)
    monkeypatch.setattr(worker_cli, 'validate_worker_native_environment', lambda *args: None)
    monkeypatch.setattr(worker_cli, 'acquire_authority', lambda *args: object())
    monkeypatch.setattr(worker_cli, 'QueueRepository', lambda *args, **kwargs: SimpleNamespace(check_authority=lambda:None,drained=lambda:True))
    @asynccontextmanager
    async def native(engine):
        try: yield SimpleNamespace(adapters={}, credential_loader=None, media_access=None)
        finally:
            events.append('native_exit')
            if failure == 'native_exit': raise RuntimeError('PRIVATE_NATIVE_CLEANUP')
    monkeypatch.setattr(worker_cli, 'native_runtime', native)
    class Worker:
        failed = False
        def __init__(self, *args, **kwargs):
            from concurrent.futures import ThreadPoolExecutor
            self.executor = ThreadPoolExecutor(max_workers=2)
        def stop(self): pass
        async def run(self, **kwargs):
            if failure != 'signal_interrupt': raise KeyboardInterrupt('PRIVATE_RUN')
        async def close(self):
            self.executor.shutdown(wait=True)
            events.append('worker_close')
            if failure == 'worker_close': raise RuntimeError('PRIVATE_CLOSE')
    monkeypatch.setattr(worker_cli, 'SocialWorker', Worker)
    installed = []
    # Keep asyncio.Runner from independently installing its default SIGINT
    # wrapper; this fixture isolates the CLI's startup/finalization handlers.
    monkeypatch.setattr(worker_cli.signal, 'getsignal', lambda sig: object())
    def set_signal(sig, handler):
        installed.append(sig)
        if len(installed) > 2:
            events.append('signal_removal')
            if failure == 'signal_interrupt': raise KeyboardInterrupt('PRIVATE_SIGNAL')
            if failure == 'signal_removal': raise RuntimeError('PRIVATE_SIGNAL')
    monkeypatch.setattr(worker_cli.signal, 'signal', set_signal)
    assert worker_cli.main(['--database-url-env','INERT_REVIEW_DSN','--worker-role','inert_worker','--native-meta','--once']) == 130
    assert events == ['worker_close','native_exit','dispose','signal_removal','signal_removal']
    assert 'PRIVATE_' not in caplog.text


@pytest.mark.parametrize('kind', ['function', 'type', 'language'])
@pytest.mark.parametrize('installed', [False, True])
def test_remaining_object_delegation_refuses(role_database, kind, installed):
    owner, worker, schema, role = role_database
    if installed: install_worker_role(owner, role, schema)
    if kind == 'function':
        with owner.begin() as conn:
            conn.execute(text('CREATE FUNCTION ' + schema + '.inert_marker() RETURNS int LANGUAGE sql AS \'SELECT 1\''))
        grant = f'GRANT EXECUTE ON FUNCTION {schema}.inert_marker() TO {role} WITH GRANT OPTION'
        revoke = f'REVOKE EXECUTE ON FUNCTION {schema}.inert_marker() FROM {role}'
    elif kind == 'type':
        with owner.begin() as conn: conn.execute(text('CREATE TYPE ' + schema + ".inert_marker AS ENUM ('inert')"))
        grant = f'GRANT USAGE ON TYPE {schema}.inert_marker TO {role} WITH GRANT OPTION'
        revoke = f'REVOKE USAGE ON TYPE {schema}.inert_marker FROM {role}'
    else:
        grant = f'GRANT USAGE ON LANGUAGE plpgsql TO {role} WITH GRANT OPTION'
        revoke = f'REVOKE USAGE ON LANGUAGE plpgsql FROM {role}'
    try:
        with owner.begin() as conn: conn.execute(text(grant))
        with pytest.raises(WorkerRoleError):
            (verify_worker_role(worker, role, schema) if installed else install_worker_role(owner, role, schema))
    finally:
        with owner.begin() as conn: conn.execute(text(revoke))
