import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import pytest
from social.http_boundary import SocialRoute
from social.service import SocialError

@pytest.mark.parametrize('failure', [False, True])
def test_http_telemetry_correlates_safe_asset_identity_without_query_or_body(caplog, failure):
    router = APIRouter(route_class=SocialRoute)
    @router.post('/api/v1/admin/social/media/uploads/{asset_id}/complete')
    def complete(asset_id: UUID):
        if failure:
            raise SocialError('MEDIA_FINALIZATION_UNKNOWN', 'Storage outcome is unknown.', 503)
        return {'state': 'ready'}
    app = FastAPI(); app.include_router(router)
    identity = uuid4()
    with caplog.at_level(logging.INFO, logger='social'):
        result = TestClient(app).post(f'/api/v1/admin/social/media/uploads/{identity}/complete?code=query-secret', json={'secret': 'body-secret'})
    assert result.status_code == (503 if failure else 200)
    records = [json.loads(r.message) for r in caplog.records if r.name == 'social' and json.loads(r.message).get('event') == 'social.http_completed']
    assert len(records) == 1
    record = records[0]
    assert record['request_id'] == result.headers['x-request-id']
    assert record['asset_id'] == str(identity)
    assert record['operation'] == 'POST /api/v1/admin/social/media/uploads/{asset_id}/complete'
    assert record['result'] == result.status_code
    assert isinstance(record['duration_ms'], int) and record['duration_ms'] >= 0
    assert record['error_code'] == ('MEDIA_FINALIZATION_UNKNOWN' if failure else None)
    assert 'query-secret' not in json.dumps(records) and 'body-secret' not in json.dumps(records)
