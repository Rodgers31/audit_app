"""Always-on view contract controls use actual retained PostgreSQL definitions."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import make_url

from social.worker import role_contract as contract
from test_report_authority_historical_schema import historical_report_role


@pytest.fixture
def definitions():
    path = (Path(__file__).resolve().parents[3] / 'docs/admin/implementation/'
            'issue749-worker-view-evidence/current-green.json')
    return json.loads(path.read_text())


def connection(definitions, kind):
    rows = [dict(relname=row['name'], definition=row['definition'],
                 source_owner=True, application_owner=True, exact_return_rule=True,
                 types=['integer', 'integer', 'text'], reloptions=['security_barrier=true'],
                 columns=['record_id', 'ingestion_id', 'authority_fingerprint'])
            for row in definitions[kind]['views']]
    def execute(sql, values):
        if 'pg_get_viewdef' in str(sql):
            return SimpleNamespace(mappings=lambda: rows)
        return SimpleNamespace(scalar=lambda: True)
    return SimpleNamespace(dialect=dialect(), execute=execute), rows


@pytest.mark.parametrize('kind', ['clean', 'historical'])
def test_actual_retained_view_definitions_are_accepted(definitions, kind):
    conn, _ = connection(definitions, kind)
    contract._views(conn, 'public')


@pytest.mark.parametrize('kind', ['clean', 'historical'])
@pytest.mark.parametrize('drift', ['unknown_definition', 'literal', 'snapshot_substitution',
                                 'source_owner', 'application_owner', 'return_rule',
                                 'types', 'options', 'columns', 'missing'])
def test_structural_and_hash_drift_still_refuses(definitions, kind, drift):
    conn, rows = connection(definitions, kind)
    if drift == 'unknown_definition': rows[0]['definition'] = 'SELECT 1,1,repeat(\'a\',64)'
    if drift == 'literal': rows[0]['definition'] = rows[0]['definition'].replace("'source_mode'", "'public.source_mode'")
    if drift == 'snapshot_substitution': rows[1]['definition'] = rows[0]['definition']
    if drift == 'source_owner': rows[0]['source_owner'] = False
    if drift == 'application_owner': rows[0]['application_owner'] = False
    if drift == 'return_rule': rows[0]['exact_return_rule'] = False
    if drift == 'types': rows[0]['types'] = ['text', 'integer', 'text']
    if drift == 'options': rows[0]['reloptions'] = ['security_barrier=true', 'security_invoker=true']
    if drift == 'columns': rows[0]['columns'] = ['wrong_record_id', 'ingestion_id', 'authority_fingerprint']
    if drift == 'missing': rows.pop()
    with pytest.raises(contract.WorkerRoleError):
        contract._views(conn, 'public')


def test_fixture_pins_physical_loopback_for_both_connections(monkeypatch):
    import test_report_authority_historical_schema as module
    calls = {}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def scalar(self, sql):
            return ('b17_view_clean' if 'current_database' in str(sql) else
                    'e621b17a0001' if 'version_num' in str(sql) else False)
    engine = SimpleNamespace(begin=Connection, dispose=lambda: None)
    def owner(url, **kwargs): calls['owner'] = kwargs; return engine
    def worker(config): calls['worker'] = make_url(config.database_url); return engine
    monkeypatch.setenv('B17_REPORT_ROLE_TEST_DB_URL', 'postgresql+psycopg2://postgres@127.0.0.1:55439/b17_view_clean')
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')  # Inert TEST-NET; no socket is opened.
    monkeypatch.setattr(module, 'create_engine', owner)
    monkeypatch.setattr(module, 'create_worker_engine', worker)
    monkeypatch.setattr(module, 'install_worker_role', lambda *args: None)
    monkeypatch.setattr(module, 'verify_worker_role', lambda *args: None)
    fixture = historical_report_role.__wrapped__()
    try:
        next(fixture)
        assert calls['owner']['connect_args']['hostaddr'] == '127.0.0.1'
        assert calls['worker'].query['hostaddr'] == '127.0.0.1'
    finally:
        fixture.close()
