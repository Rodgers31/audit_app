"""Independent users-lane replay using actual provider code and memory HTTP.

Every identity, credential, response and transport is inert. No production
environment, socket, database, email or deletion is used here.
"""
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import admin_users_provider as provider
import database
import supabase_auth
from routers import admin_users


ACTOR = "11111111-1111-4111-8111-111111111111"
TARGET = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT = "/api/v1/admin/users"


def user(**extras):
    return {"id": TARGET, "email": "fixture@example.invalid", "created_at": None,
            "app_metadata": {}, "user_metadata": {}, **extras}


@pytest.fixture
def memory(monkeypatch):
    state = SimpleNamespace(identity=user(), profile={"id": TARGET, "roles": ["citizen"]},
                            acknowledgment={}, envelope={"users": [user()]}, audits=[], requests=[])

    def transport(request):
        state.requests.append(request)
        if request.method in ("POST", "DELETE"):
            value = state.acknowledgment
        elif request.url.path.endswith("/admin/users"):
            value = state.envelope
        elif request.url.path.endswith("/profiles"):
            value = [state.profile]
        else:
            value = state.identity
        return httpx.Response(200, json=deepcopy(value))

    original_client = httpx.Client
    monkeypatch.setattr(provider, "_config", lambda: ("https://users-fixture.invalid", "inert-service-key"))
    monkeypatch.setattr(provider, "_headers", lambda: {"apikey": "inert-service-key", "Authorization": "Bearer inert-service-key"})
    monkeypatch.setattr(provider.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs))
    app = FastAPI()
    app.include_router(admin_users.router)
    app.dependency_overrides[supabase_auth.get_current_user] = lambda: supabase_auth.AdminUser(id=ACTOR, email=None, roles=["admin"])
    app.dependency_overrides[database.get_db] = lambda: object()

    def audit(_db, **details):
        state.audits.append(details)
        return True

    monkeypatch.setattr(admin_users, "record_admin_action", audit)
    with TestClient(app, raise_server_exceptions=False) as client:
        state.client = client
        yield state


@pytest.mark.parametrize("acknowledgment", [
    {"success": False}, {"ok": 0}, {"ok": "false"},
    {"error_code": "invalid_request"}, {"arbitrary": "unrecognized-provider-schema"},
])
@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/send-reset")])
def test_http_200_semantic_failure_does_not_certify_mutation(memory, acknowledgment, method, suffix):
    memory.acknowledgment = acknowledgment
    response = memory.client.request(method, ROOT + "/" + TARGET + suffix, json={} if method == "POST" else None)
    assert response.status_code == 502
    assert memory.audits == []


def test_http_200_failed_list_envelope_does_not_certify_zero_users(memory):
    memory.envelope = {"users": [], "error": "provider-failed", "ok": False}
    response = memory.client.get(ROOT)
    assert response.status_code == 502


@pytest.mark.parametrize("key", ["apiKey", "api-key", "authorization", "action_link", "email_otp", "private_key"])
def test_nested_provider_metadata_does_not_expose_credentials(memory, key):
    memory.identity["user_metadata"] = {"safe": "ordinary label", "nested": [{key: "inert-credential-marker", "label": "keep"}]}
    response = memory.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 200
    assert "inert-credential-marker" not in response.text
    assert response.json()["user_metadata"] == {"safe": "ordinary label", "nested": [{"label": "keep"}]}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10 ** 400])
def test_non_json_metadata_numbers_are_rejected_with_recoverable_json(memory, value, monkeypatch):
    # Direct fake of the parser boundary: Python's json decoder accepts NaN /
    # Infinity by default, despite these being invalid wire JSON numbers.
    monkeypatch.setattr(provider, "get_user", lambda _uid: user(user_metadata={"value": value}))
    response = memory.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("value", [None, True, 0, -1, float("nan"), float("inf")])
def test_direct_ack_guard_rejects_non_object_verdicts(value):
    with pytest.raises(HTTPException) as error:
        admin_users._ack(value)
    assert error.value.status_code == 502


def test_valid_no_content_acknowledgments_are_accepted_and_audited(memory):
    response = memory.client.post(ROOT + "/" + TARGET + "/send-reset", json={})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "email": "fixture@example.invalid", "audit_recorded": True}
    request = next(request for request in memory.requests if request.method == "POST")
    assert request.url.path == "/auth/v1/recover"
    assert len(memory.audits) == 1


def test_transport_invalid_json_is_sanitized(memory, monkeypatch):
    # Retain original through the superclass of TestClient, because the memory
    # fixture temporarily replaces the module-level httpx.Client constructor.
    original_client = TestClient.__bases__[0]
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b'{broken-json'))
    monkeypatch.setattr(provider.httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    response = memory.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 502
    assert "broken-json" not in response.text
