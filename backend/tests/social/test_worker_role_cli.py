"""Role guards execute before provider, repository or worker construction."""
import logging
from types import SimpleNamespace

import pytest

from social.worker import __main__ as worker_cli
from social.worker import role_admin
from social.worker.config import WorkerConfig
from social.worker.role_contract import WorkerRoleError


@pytest.mark.parametrize('extra', [[], ['--worker-role', 'inert_worker']])
def test_native_role_refusal_precedes_all_runtime_and_queue_access(monkeypatch, caplog, extra):
    calls = []
    engine = SimpleNamespace(dispose=lambda: calls.append('dispose'))
    monkeypatch.setattr(worker_cli, 'create_worker_engine', lambda config: calls.append('engine') or engine)
    def reject(*args): calls.append('verify'); raise WorkerRoleError('PRIVATE_DRIVER_SECRET')
    monkeypatch.setattr(worker_cli, 'verify_worker_role', reject)
    monkeypatch.setattr(worker_cli, 'QueueRepository', lambda *args: pytest.fail('Queue must remain untouched'))
    monkeypatch.setattr(worker_cli, 'native_runtime', lambda *args: pytest.fail('Provider runtime must remain unopened'))
    with caplog.at_level(logging.ERROR):
        assert worker_cli.main(['--database-url', 'postgresql://inert:PRIVATE_DSN_SECRET@localhost/inert', '--native-meta', '--once', *extra]) == 1
    assert calls == (['engine','verify','dispose'] if extra else [])
    assert 'PRIVATE_' not in caplog.text


def test_explicit_environment_reference_has_no_implicit_application_fallback(monkeypatch, caplog):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://private@production.invalid/app')
    monkeypatch.delenv('NAMED_INERT_WORKER_DSN', raising=False)
    monkeypatch.setattr(worker_cli, 'create_worker_engine', lambda config: pytest.fail('No named worker DSN'))
    assert worker_cli.main(['--database-url-env','NAMED_INERT_WORKER_DSN','--once']) == 1
    assert 'production.invalid' not in caplog.text


@pytest.mark.parametrize('schema', ['', True, 'public;SET ROLE postgres', 'pg_temp', 'information_schema'])
def test_worker_schema_cannot_be_injected(schema):
    with pytest.raises(ValueError): WorkerConfig('postgresql://localhost/inert', database_schema=schema)


@pytest.mark.parametrize('extra,schema', [([], None), (['--worker-role', 'inert_worker'], 'public'),
                                          (['--database-schema', 'tenant'], 'tenant')])
def test_schema_is_pinned_only_when_requested(monkeypatch, extra, schema):
    configs = []
    def stop(config): configs.append(config); raise RuntimeError('stop before connecting')
    monkeypatch.setattr(worker_cli, 'create_worker_engine', stop)
    assert worker_cli.main(['--database-url', 'postgresql://inert@localhost/inert', '--once', *extra]) == 1
    assert [config.database_schema for config in configs] == [schema]


@pytest.mark.parametrize('cli', [worker_cli, role_admin])
def test_interrupt_during_verification_is_fixed_private_and_disposes(monkeypatch, capsys, caplog, cli):
    calls = []
    engine = SimpleNamespace(dispose=lambda: calls.append('dispose'))
    monkeypatch.setenv('NAMED_INERT_DSN', 'postgresql://inert:PRIVATE_SECRET@localhost/inert')
    monkeypatch.setattr(cli, 'create_worker_engine', lambda config: engine)
    def interrupt(*args): raise KeyboardInterrupt('PRIVATE_SQL_AND_DRIVER_TEXT')
    monkeypatch.setattr(cli, 'verify_worker_role', interrupt)
    args = ['--database-url-env', 'NAMED_INERT_DSN'] + (['--role', 'inert_worker', '--verify'] if cli is role_admin
                                                     else ['--worker-role', 'inert_worker', '--native-meta', '--once'])
    with caplog.at_level(logging.ERROR):
        try: result = cli.main(args)
        except KeyboardInterrupt: pytest.fail('The interrupt escaped with its private text and traceback')
    assert result == 130
    output = capsys.readouterr()
    assert calls == ['dispose'] and 'PRIVATE_' not in output.out + output.err + caplog.text
    assert ('"status":"interrupted"' in output.out) if cli is role_admin else ('worker_startup_interrupted' in caplog.text)


@pytest.mark.parametrize('cli,args', [(role_admin, ['--database-url', 'postgresql://PRIVATE_SECRET@localhost/x', '--role', 'r', '--verify']),
                                      (worker_cli, ['--database-url-e', 'NAMED_INERT_DSN', '--once'])])
def test_option_prefixes_are_never_expanded(cli, args, capsys):
    with pytest.raises(SystemExit) as stopped: cli.main(args)
    assert stopped.value.code == 2 and 'PRIVATE_' not in ''.join(capsys.readouterr())


@pytest.mark.parametrize('install', [False, True])
def test_operator_failure_closes_and_has_fixed_private_output(monkeypatch, capsys, install):
    calls = []
    engine = SimpleNamespace(dispose=lambda: calls.append('dispose'))
    monkeypatch.setenv('NAMED_INERT_DSN', 'postgresql://inert:PRIVATE_SECRET@localhost/inert')
    monkeypatch.setattr(role_admin, 'create_worker_engine', lambda config: engine)
    def reject(*args): raise RuntimeError('PRIVATE_DRIVER_SECRET')
    monkeypatch.setattr(role_admin, 'install_worker_role' if install else 'verify_worker_role', reject)
    assert role_admin.main(['--database-url-env','NAMED_INERT_DSN','--role','inert_worker', '--install' if install else '--verify']) == 1
    output = capsys.readouterr()
    assert 'unavailable' in output.out and 'PRIVATE_' not in output.out + output.err
    assert calls == ['dispose']


@pytest.mark.parametrize('cli', [worker_cli, role_admin])
def test_parser_errors_never_echo_mistaken_secret_arguments(cli, capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(['--unknown','PRIVATE_SECRET_ARGUMENT'])
    assert stopped.value.code == 2
    output = capsys.readouterr()
    assert 'PRIVATE_SECRET' not in output.out + output.err


def test_native_authority_operator_mode_is_explicit_and_private(monkeypatch,capsys):
    from social.worker import native_authority_schema
    calls=[]
    engine=SimpleNamespace(dispose=lambda:calls.append('dispose'))
    monkeypatch.setenv('NAMED_INERT_DSN','postgresql://inert:PRIVATE_SECRET@localhost/inert')
    monkeypatch.setattr(role_admin,'create_worker_engine',lambda config:engine)
    monkeypatch.setattr(native_authority_schema,'install_native_authority',lambda *args:calls.append(args))
    assert role_admin.main(['--database-url-env','NAMED_INERT_DSN','--role','inert_worker','--install','--native-authority'])==0
    assert calls==[(engine,'inert_worker','public'),'dispose']
    output=capsys.readouterr()
    assert '"status":"ok"' in output.out and 'PRIVATE_' not in output.out+output.err


@pytest.mark.parametrize('mode',[['--verify'],['--install','--native-platforms']])
def test_native_authority_rejects_other_operator_modes_before_engine(monkeypatch,capsys,mode):
    monkeypatch.setenv('NAMED_INERT_DSN','postgresql://inert:PRIVATE_SECRET@localhost/inert')
    monkeypatch.setattr(role_admin,'create_worker_engine',lambda config:pytest.fail('No engine for an unsupported profile'))
    assert role_admin.main(['--database-url-env','NAMED_INERT_DSN','--role','inert_worker','--native-authority',*mode])==1
    assert '"status":"unavailable"' in capsys.readouterr().out
