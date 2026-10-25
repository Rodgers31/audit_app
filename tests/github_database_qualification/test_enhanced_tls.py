"""The alternate application Engine obeys the same GitHub transport policy."""
import importlib
import os
from pathlib import Path
import sys

import pytest

from test_qualify import URL, q
from test_writer_tls import prepared


@pytest.fixture
def load_enhanced(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.syspath_prepend(str(root / 'backend'))
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    modules = []

    def load(package):
        name = 'backend.database_enhanced' if package else 'database_enhanced'
        monkeypatch.delitem(sys.modules, name, raising=False)
        module = importlib.import_module(name)
        modules.append(module)
        return module

    yield load
    for module in modules:
        module.engine.dispose()


def driver_options(module):
    """Observe final DBAPI arguments; never let a driver open a socket."""
    from sqlalchemy import event

    class Captured(BaseException):
        pass

    seen = []

    def capture(dialect, record, cargs, cparams):
        seen.append(cparams.copy())
        raise Captured()

    event.listen(module.engine, 'do_connect', capture)
    try:
        with pytest.raises(Captured):
            module.engine.connect()
    finally:
        event.remove(module.engine, 'do_connect', capture)
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize('package', [False, True])
@pytest.mark.parametrize('suffix', ['', '?sslmode=require'])
def test_enhanced_engine_uses_verified_github_transport(
        prepared, monkeypatch, load_enhanced, package, suffix):
    if str(q.tls.SYSTEM_CA) != '/etc/ssl/certs/ca-certificates.crt':
        pytest.skip('Actual Engine policy uses the Linux runner root store')
    monkeypatch.setenv('DATABASE_URL', URL + suffix)
    module = load_enhanced(package)
    options = driver_options(module)
    assert options['sslmode'] == 'verify-full'
    assert options['sslrootcert'] == os.environ['PGSSLROOTCERT']
    assert Path(options['sslrootcert']).read_bytes() == q.tls.bundle_bytes()
    assert options['gssencmode'] == 'disable' and options['hostaddr'] == ''
    assert options['dbname'] == 'postgres'
    assert options['user'] == 'postgres.' + q.PROJECT
    assert options['connect_timeout'] == 10
    assert options['options'] == '-c timezone=utc'
    assert module.engine.dialect.driver == 'psycopg2'


@pytest.mark.parametrize('package', [False, True])
@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg2'])
def test_enhanced_engine_default_off_preserves_driver_and_uri_policy(
        monkeypatch, load_enhanced, package, scheme):
    monkeypatch.delenv(q.tls.FLAG, raising=False)
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('DATABASE_URL', URL.replace('postgresql:', scheme + ':') +
                       '?sslmode=disable')
    options = driver_options(load_enhanced(package))
    assert options['sslmode'] == 'disable'
    assert 'sslrootcert' not in options
    assert 'hostaddr' not in options and 'gssencmode' not in options
    assert options['connect_timeout'] == 10
    assert options['options'] == '-c timezone=utc'


@pytest.mark.parametrize('package', [False, True])
@pytest.mark.parametrize('flag,github', [('0', 'true'), ('1', 'false')])
def test_enhanced_engine_refuses_invalid_opt_in_context(
        monkeypatch, load_enhanced, package, flag, github):
    monkeypatch.setenv('DATABASE_URL', URL)
    monkeypatch.setenv(q.tls.FLAG, flag)
    monkeypatch.setenv('GITHUB_ACTIONS', github)
    with pytest.raises(RuntimeError, match='GITHUB_DATABASE_POLICY_REFUSED'):
        load_enhanced(package)
