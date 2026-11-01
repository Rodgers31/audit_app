"""Public responses retain useful state without exposing private diagnostics."""
import copy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import database
import main
import importlib
auto_seeder = importlib.import_module("services.auto_seeder")
from supabase_auth import AdminUser, require_admin

PATH = '/private/review-only/operator/report.pdf'
DIAGNOSTIC = 'review-only-db.internal user=review-only-reader'
URL = 'https://publisher.invalid/report.pdf'
TITLE = 'Quarterly Economic and Budget Review Sector Policy Statement'


@pytest.fixture
def http():
    # Requests exercise the mounted routes; no lifespan or real DB/provider work.
    client = TestClient(main.app, raise_server_exceptions=False)
    yield client
    client.close()

@pytest.fixture
def manifest(monkeypatch):
    value = {'by_md5': {'a' * 32: {'url': URL, 'file_path': PATH,
             'title': TITLE, 'source': 'treasury', 'doc_type': 'report',
             'fetched': '2026-11-01T00:00:00Z'}}}
    monkeypatch.setattr(main, '_load_manifest', lambda: copy.deepcopy(value))
    monkeypatch.setattr(main, '_read_etl_manifest', lambda: copy.deepcopy(value))
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', False)
    monkeypatch.setattr(main, '_s3_client', None)
    return value


@pytest.mark.parametrize('route', [
    '/api/v1/docs/resolve',
    '/api/v1/dashboards/national/fiscal-outturns',
    '/api/v1/dashboards/national/sector-ceilings',
])
def test_manifest_paths_are_not_public(http, manifest, route):
    response = http.get(route, params={'url': URL} if route.endswith('resolve') else {})
    assert response.status_code == 200
    assert PATH not in response.text
    assert TITLE in response.text
    if route.endswith('resolve'):
        assert response.json()['local_path'] is None
    elif route.endswith('fiscal-outturns'):
        row = response.json()['series'][0]
        assert row['revenue'] is row['expenditure'] is row['balance'] is None
        assert row['provenance']['file'] is None
    else:
        assert response.json()['provenance'][0]['file'] is None


def test_document_mirror_and_public_metadata_still_resolve(http, manifest, monkeypatch):
    calls = []
    manifest['by_md5']['a' * 32]['s3_key'] = 'public/review-only.pdf'
    monkeypatch.setattr(main.settings, 'aws_bucket', 'review-only-bucket')
    def presign(operation, **kwargs):
        calls.append((operation, kwargs))
        return 'https://mirror.invalid/review-only.pdf?signature=dummy'
    monkeypatch.setattr(main, '_s3_client', SimpleNamespace(generate_presigned_url=presign))
    response = http.get('/api/v1/docs/resolve', params={'url': URL})
    assert response.status_code == 200
    body = response.json()
    assert body['mirrored'] is True and body['mirror_url'].startswith('https://mirror.invalid/')
    assert body['title'] == TITLE and body['original_url'] == URL
    assert body['source'] == 'treasury' and body['doc_type'] == 'report'
    assert calls == [('get_object', {'Params': {'Bucket': 'review-only-bucket',
                                               'Key': 'public/review-only.pdf'}, 'ExpiresIn': 3600})]


def test_unknown_document_keeps_nonmirrored_shape(http, manifest):
    response = http.get('/api/v1/docs/resolve', params={'url': URL + '?unknown'})
    assert response.status_code == 200
    assert response.json() == {'original_url': URL + '?unknown', 'mirrored': False,
                              'mirror_url': None, 'local_path': None}


class FailedDatabase:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def query(self, *args):
        raise OperationalError('SELECT private_internal_table', {}, Exception(DIAGNOSTIC))


@pytest.mark.parametrize('route', ['/api/v1/counties', '/api/v1/counties/nairobi/comprehensive'])
def test_county_failures_keep_status_without_database_diagnostics(http, monkeypatch, route):
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', True)
    monkeypatch.setattr(main, 'get_db', lambda: iter([FailedDatabase()]))
    response = http.get(route)
    assert response.status_code == 500
    assert DIAGNOSTIC not in response.text and 'private_internal_table' not in response.text
    assert response.json()['detail']


def fail(*args, **kwargs):
    raise RuntimeError(DIAGNOSTIC)


def test_seeder_failure_reports_error_without_diagnostics(http, monkeypatch):
    monkeypatch.setattr(auto_seeder, 'get_seeder_status', fail)
    response = http.get('/api/v1/system/seeder-status')
    assert response.status_code == 200  # Preserve legacy error DTO/status.
    assert response.json()['status'] == 'error'
    assert response.json()['auto_seeder']['is_running'] is False
    assert DIAGNOSTIC not in response.text


def test_root_failure_does_not_echo_exception(http, monkeypatch):
    monkeypatch.setattr(main, 'datetime', SimpleNamespace(datetime=SimpleNamespace(now=fail)))
    response = http.get('/')
    assert response.status_code == 500
    assert DIAGNOSTIC not in response.text


@pytest.mark.parametrize('component', ['module', 'seeder', 'database'])
def test_pipeline_snapshot_errors_keep_failure_state_without_details(monkeypatch, component, caplog):
    real_import = main.importlib.import_module
    def import_module(name, *args, **kwargs):
        if name == 'etl.kenya_pipeline':
            if component == 'module': fail()
            return SimpleNamespace()
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(main.importlib, 'import_module', import_module)
    monkeypatch.setattr(auto_seeder, 'get_seeder_status',
                        fail if component == 'seeder' else lambda: {'is_running': False})
    monkeypatch.setattr(database, 'request_session', lambda: nullcontext(object()))
    stats = {'entities': {'counties': 47}, 'population': {'records': 47},
             'economic_indicators': {'records': 1}, 'loans': {'records': 1}}
    monkeypatch.setattr(main, '_pipeline_health_database_stats',
                        fail if component == 'database' else lambda db: stats)
    snapshot = main._pipeline_health_snapshot()
    import json
    assert DIAGNOSTIC not in json.dumps(snapshot)
    assert len(snapshot['alerts']) == 1
    if component == 'module': assert snapshot['modules']['etl.kenya_pipeline']['available'] is False
    if component == 'database': assert snapshot['database'] == {}
    assert DIAGNOSTIC in caplog.text  # Detailed failure stays available to operators.


@pytest.fixture
def health_snapshot(monkeypatch):
    async def snapshot(*, include_legacy_module=True):
        return {'alerts': [], 'database': {}, 'modules': {}, 'auto_seeder': {'is_running': False}}
    async def sources(): return {}
    monkeypatch.setattr(main, '_read_pipeline_health_snapshot', snapshot)
    monkeypatch.setattr(main, '_source_reachability', SimpleNamespace(legacy=sources))
    jobs = {'review-only-job': {'source': 'treasury', 'job_type': 'light', 'status': 'failed',
            'result': {'artifact': PATH}, 'error': DIAGNOSTIC}}
    monkeypatch.setattr(main, '_etl_jobs', jobs)
    return copy.deepcopy(jobs)


def test_public_health_does_not_publish_admin_queue(http, health_snapshot):
    response = http.get('/api/v1/system/pipeline-health')
    assert response.status_code == 200 and response.json()['status'] == 'healthy'
    assert response.json()['etl_jobs'] == []
    assert 'review-only-job' not in response.text and PATH not in response.text
    assert DIAGNOSTIC not in response.text
    assert main._etl_jobs == health_snapshot  # Projection cannot erase the private state.


def test_private_job_status_keeps_admin_guard_and_authorized_details(http, monkeypatch, health_snapshot):
    refused = http.get('/api/v1/admin/etl/status')
    assert refused.status_code in (401, 403)
    monkeypatch.setattr(main.app, 'dependency_overrides', {
        **main.app.dependency_overrides,
        require_admin: lambda: AdminUser(id='00000000-0000-4000-8000-000000000001', email=None, roles=['admin']),
    })
    accepted = http.get('/api/v1/admin/etl/status')
    assert accepted.status_code == 200
    assert accepted.json()['jobs'] == health_snapshot
