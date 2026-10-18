"""A recovery engine and its exporter must have one explicit connection target."""
import pytest
from sqlalchemy.engine import make_url
import social.recovery_operator as operator

@pytest.mark.parametrize('suffix', ['?host=other', '?hostaddr=192.0.2.2', '?port=6543', '?dbname=other', '?service=other', '?options=-csearch_path=other', '?sslmode=require&sslmode=disable'])
def test_libpq_target_overrides_refuse_before_engine(monkeypatch, capsys, suffix):
    calls = []
    def factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError('inert factory guard')
    monkeypatch.setattr(operator, 'create_engine', factory)
    monkeypatch.setenv('INERT_REVIEW_DSN', 'postgresql://inert@127.0.0.1:55420/inert'+suffix)
    assert operator.main(['verify','--database-url-env','INERT_REVIEW_DSN']) == 1
    assert calls == []
    assert 'other' not in capsys.readouterr().out


def test_engine_url_pins_hostaddr_for_exporter_and_ignores_ambient_override(monkeypatch):
    calls = []
    monkeypatch.setenv('PGHOSTADDR','192.0.2.2')
    monkeypatch.setenv('INERT_REVIEW_DSN','postgresql://inert@127.0.0.1:55420/inert?sslmode=require')
    def factory(url, **kw):
        calls.append(make_url(url))
        raise RuntimeError('stop before database connection')
    monkeypatch.setattr(operator, 'create_engine', factory)
    assert operator.main(['verify','--database-url-env','INERT_REVIEW_DSN']) == 1
    assert len(calls) == 1
    assert calls[0].query.get('hostaddr') == '127.0.0.1'
    assert calls[0].query.get('sslmode') == 'require'


@pytest.mark.parametrize('option', ['host=other', 'port=6543', 'dbname=other', 'service=other', 'options=-csearch_path=other'])
def test_direct_export_refuses_target_override_before_connect(monkeypatch, tmp_path, option):
    from sqlalchemy import create_engine
    from social.recovery_database import export_database_backup, DatabaseRecoveryError
    engine = create_engine('postgresql://inert@127.0.0.1:55420/inert?'+option)
    attempts = []
    def connect():
        attempts.append(True)
        raise RuntimeError('inert network guard')
    monkeypatch.setattr(engine, 'connect', connect)
    try:
        with pytest.raises(DatabaseRecoveryError):
            export_database_backup(engine, schema='public', destination=tmp_path/'inert',
                signing_key=b'x'*32, pg_dump=tmp_path/'pg_dump')
        assert attempts == []
    finally: engine.dispose()
