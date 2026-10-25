import importlib
import os
from pathlib import Path
import sys

import pytest

from test_qualify import q, URL


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.setenv(q.tls.FLAG,'1')
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    envfile = tmp_path/'github-env'
    envfile.touch(mode=0o600)
    monkeypatch.setenv('GITHUB_ENV',str(envfile))
    # macOS unit tests use a public fixture root; Linux keeps actual system roots.
    if not q.tls.SYSTEM_CA.is_file():
        monkeypatch.setattr(q.tls,'SYSTEM_CA',q.tls.CA)
    q.tls.prepare()
    line = envfile.read_text().strip()
    assert line.startswith('PGSSLROOTCERT=')
    monkeypatch.setenv('PGSSLROOTCERT',line.split('=',1)[1])
    return envfile


def test_preparation_does_not_copy_credentials(prepared, monkeypatch):
    monkeypatch.setenv('DATABASE_URL',URL)
    q.tls.prepare()
    output = prepared.read_text()
    assert 'private-fixture' not in output and 'DATABASE_URL' not in output
    args = q.tls.connection_args()
    assert args['sslmode'] == 'verify-full'
    assert args['hostaddr'] == '' and args['gssencmode'] == 'disable'
    assert Path(args['sslrootcert']).read_bytes() == q.tls.bundle_bytes()


def test_policy_is_default_off_and_never_silently_falls_back(monkeypatch):
    monkeypatch.delenv(q.tls.FLAG,raising=False)
    assert q.tls.connection_args() == {}
    for value in ('', 'false', '0', 'true'):
        monkeypatch.setenv(q.tls.FLAG,value)
        with pytest.raises(RuntimeError):
            q.tls.connection_args()
    monkeypatch.setenv(q.tls.FLAG,'1')
    monkeypatch.setenv('GITHUB_ACTIONS','false')
    with pytest.raises(RuntimeError):
        q.tls.connection_args()


def test_modified_root_or_environment_refuses(prepared, monkeypatch):
    args = q.tls.connection_args()
    Path(args['sslrootcert']).write_bytes(b'wrong root')
    with pytest.raises(RuntimeError):
        q.tls.connection_args()
    monkeypatch.setenv('PGSSLROOTCERT','/unrelated/ca')
    with pytest.raises(RuntimeError):
        q.tls.connection_args()


def test_real_application_engine_overrides_weak_uri_tls(prepared, monkeypatch):
    pytest.importorskip('sqlalchemy')
    if str(q.tls.SYSTEM_CA) != '/etc/ssl/certs/ca-certificates.crt':
        pytest.skip('Actual application-engine policy uses the Linux runner root store')
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'backend'))
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    monkeypatch.setenv('DATABASE_URL',URL+'?sslmode=require')
    database = importlib.import_module('database')
    from sqlalchemy import event
    class Intercepted(Exception):
        pass
    seen = []
    def capture(dialect, record, cargs, cparams):
        seen.append(cparams.copy())
        raise Intercepted()
    event.listen(database.engine,'do_connect',capture)
    try:
        with pytest.raises(Intercepted):
            database.engine.connect()
        assert len(seen) == 1
        assert seen[0]['sslmode'] == 'verify-full'
        assert seen[0]['sslrootcert'] == os.environ['PGSSLROOTCERT']
        assert seen[0]['dbname'] == 'postgres' and seen[0]['hostaddr'] == ''
    finally:
        event.remove(database.engine,'do_connect',capture)
        database.engine.dispose()


def test_source_cache_engine_uses_same_verified_options(prepared, monkeypatch):
    sqlalchemy = pytest.importorskip('sqlalchemy')
    if str(q.tls.SYSTEM_CA) != '/etc/ssl/certs/ca-certificates.crt':
        pytest.skip('Actual source-cache engine uses the Linux runner root store')
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'backend'))
    monkeypatch.setenv('DATABASE_URL',URL+'?sslmode=require')
    cache = importlib.import_module('seeding.source_cache')
    monkeypatch.setattr(cache,'reviewed_sources',lambda profile:object())
    seen = []
    class Intercepted(BaseException):
        pass
    def capture(url, **kwargs):
        seen.append(kwargs['connect_args'])
        raise Intercepted()
    monkeypatch.setattr(sqlalchemy,'create_engine',capture)
    with pytest.raises(Intercepted):
        cache.main(['--database-url-env','DATABASE_URL','--profile','county'])
    assert seen == [{'connect_timeout':8, **q.tls.connection_args()}]
