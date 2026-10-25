"""Missing direct transport is observed over real ASGI before implementation."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from social.connections.api import router
from social.http_boundary import require_admin
from test_connections_support import db, config, graph
from test_connections_api import client


def test_legacy_control_still_serves_authenticated_status(db, config, graph):
    response = client(db, config, graph).get('/api/v1/admin/social/connections/meta/status')
    assert response.status_code == 200
    assert response.json()['provider'] == 'meta'


def test_direct_backend_transport_is_available_but_held_by_default(db, config, graph):
    response = client(db, config, graph).post('/api/v1/admin/social/connections/meta/direct/start',
        json={'admin_origin': 'https://admin.example.test', 'reason': 'Inert control'},
        headers={'Idempotency-Key': '12345678-1234-4234-8234-123456789abc'})
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'CALLBACK_INGRESS_UNVERIFIED'
