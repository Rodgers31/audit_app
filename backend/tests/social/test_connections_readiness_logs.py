"""Executed local redaction evidence, with inert values and no remote transport.

The inbound captures deliberately retain the current unsafe result. They are
evidence of a pending ingress/Sentry gate, never a readiness success verdict.
The synthetic route exercises SocialRoute; it installs no real callback.
"""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import traceback
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.exc import OperationalError

from social.connections.provider import MetaProvider
from social.http_boundary import SocialRoute
from social.service import SocialError
from test_connections_support import config


TOKEN = "inert-readiness-token-marker"
CODE = "inert-readiness-code-marker"
ERROR = "inert-readiness-error-marker"
PROOF = "inert-readiness-proof-marker"
BODY = "inert-readiness-body-marker"
MARKERS = (TOKEN, CODE, ERROR, PROOF, BODY)


class FailingStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b'{"data":'
        raise httpx.ReadTimeout(ERROR)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("mode,expected", [
    ("success", None),
    ("http_error", "PROVIDER_REJECTED"),
    ("revoked", "GRANT_REVOKED"),
    ("invalid_json", "PROVIDER_RESPONSE_INVALID"),
    ("wrong_shape", "PROVIDER_RESPONSE_INVALID"),
    ("compressed", "PROVIDER_RESPONSE_INVALID"),
    ("transport_failure", "PROVIDER_UNAVAILABLE"),
    ("stream_failure", "PROVIDER_UNAVAILABLE"),
])
def test_httpx_provider_requests_and_failures_hide_fixture_secrets(config, caplog, mode, expected):
    wire = []
    observed = []
    stream = FailingStream()

    def response(request):
        wire.append(request)
        if mode == "transport_failure":
            raise httpx.ReadTimeout(str(request.url) + CODE + ERROR, request=request)
        if mode == "stream_failure":
            return httpx.Response(200, stream=stream)
        if mode == "http_error":
            return httpx.Response(503, json={"error": {"code": 1, "message": ERROR}})
        if mode == "revoked":
            return httpx.Response(400, json={"error": {"code": 190, "message": ERROR}})
        if mode == "invalid_json":
            return httpx.Response(200, content=ERROR.encode())
        if mode == "wrong_shape":
            return httpx.Response(200, json=[ERROR])
        if mode == "compressed":
            return httpx.Response(200, headers={"Content-Encoding": "unexpected"}, content=ERROR.encode())
        return httpx.Response(200, json={"accepted": True})

    provider = MetaProvider(config, transport=httpx.MockTransport(response))
    provider.client.event_hooks["request"] = [lambda request: observed.append(str(request.url))]
    provider.client.event_hooks["response"] = [lambda response: observed.append(str(response.request.url))]
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            if expected:
                with pytest.raises(SocialError) as failure:
                    provider._request("POST", "oauth/access_token", token=TOKEN,
                                      params={"input_token": TOKEN, "appsecret_proof": PROOF},
                                      data={"code": CODE, "client_secret": config.app_secret, "fixture": BODY})
                assert failure.value.code == expected
                rendered = "".join(traceback.format_exception(type(failure.value), failure.value,
                                                             failure.value.__traceback__))
                assert all(marker not in rendered for marker in MARKERS)
            else:
                assert provider._request("POST", "oauth/access_token", token=TOKEN,
                                         params={"input_token": TOKEN, "appsecret_proof": PROOF},
                                         data={"code": CODE, "client_secret": config.app_secret, "fixture": BODY}) == {"accepted": True}
    finally:
        provider.close()
    assert len(wire) == 1 and wire[0].url.params["input_token"] == TOKEN
    assert wire[0].url.params["appsecret_proof"] == PROOF
    assert wire[0].headers["Authorization"] == "Bearer " + TOKEN
    assert CODE.encode() in wire[0].content and config.app_secret.encode() in wire[0].content
    assert observed and all(marker not in json.dumps(observed) for marker in MARKERS)
    messages = [record.getMessage() for record in caplog.records if record.name == "httpx"]
    if mode != "transport_failure":
        assert messages and "graph.facebook.com/v26.0/oauth/access_token" in messages[0]
    assert all(marker not in json.dumps(messages) for marker in (*MARKERS, config.app_secret))
    if mode == "stream_failure":
        assert stream.closed


@pytest.mark.parametrize("mode,status", [
    ("success", 200), ("social_error", 409), ("http_error", 403),
    ("validation", 422), ("database_error", 503), ("unexpected", 500),
])
def test_socialroute_logs_safe_static_operation_on_callback_shaped_requests(caplog, mode, status):
    router = APIRouter(route_class=SocialRoute)

    @router.post("/fixture/callback/{flow_id}")
    def callback(flow_id: UUID):
        if mode == "social_error":
            raise SocialError("FIXTURE_REJECTED", "The inert request was rejected.", 409)
        if mode == "http_error":
            raise HTTPException(403, detail=ERROR + CODE + TOKEN)
        if mode == "database_error":
            raise OperationalError("fixture " + BODY, {"token": TOKEN}, RuntimeError(ERROR))
        if mode == "unexpected":
            raise RuntimeError(ERROR + CODE + TOKEN)
        return {"accepted": True}

    app = FastAPI()
    app.include_router(router)
    identity = "00000000-0000-0000-0000-000000000001" if mode != "validation" else CODE
    with caplog.at_level(logging.INFO, logger="social"):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/fixture/callback/" + identity,
            params={"code": CODE, "access_token": TOKEN, "error": ERROR, "error_description": ERROR},
            json={"code": CODE, "access_token": TOKEN, "private": BODY})
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    social_records = [json.loads(record.getMessage()) for record in caplog.records if record.name == "social"]
    completed = [record for record in social_records if record["event"] == "social.http_completed"]
    assert len(completed) == 1
    assert completed[0]["operation"] == "POST /fixture/callback/{flow_id}"
    assert completed[0]["result"] == status
    assert completed[0]["request_id"] == response.headers["x-request-id"]
    assert all(marker not in json.dumps(social_records) for marker in MARKERS)
    assert all(marker not in response.text for marker in MARKERS)
    if mode in {"database_error", "unexpected"}:
        assert len([record for record in social_records if record["event"] == "social.request_failed"]) == 1


def test_testclient_httpx_logs_capture_callback_query_pending_ingress_gate(caplog):
    """Graph filtering does not certify logging by unrelated HTTP clients."""
    app = FastAPI()

    @app.get("/fixture/callback")
    def callback():
        return {"accepted": True}

    with caplog.at_level(logging.INFO, logger="httpx"):
        response = TestClient(app).get("/fixture/callback", params={"code": CODE, "access_token": TOKEN, "error": ERROR})
    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records if record.name == "httpx")
    assert messages and all(marker in messages for marker in (CODE, TOKEN, ERROR))


SENTRY_CAPTURE = r'''
import json
import sys
import httpx
import sentry_sdk
from sentry_sdk.transport import Transport
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from social.connections.config import MetaConfig
from social.connections.provider import MetaProvider
from social.http_boundary import SocialRoute
from social.service import SocialError
from monitoring.instrumentation import before_send_filter

token, code, error = "inert-sentry-token-marker", "inert-sentry-code-marker", "inert-sentry-error-marker"
sent = []
class MemoryTransport(Transport):
    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type in ("event", "transaction"):
                sent.append((item.type, item.payload.json))
sentry_sdk.init(dsn="https://fixture@example.test/1", transport=MemoryTransport(),
    integrations=[HttpxIntegration(), FastApiIntegration(), StarletteIntegration()],
    default_integrations=False, auto_enabling_integrations=False, traces_sample_rate=1.0,
    send_default_pii=False, before_send=before_send_filter)

if sys.argv[1] == "outbound":
    config = MetaConfig(enabled=True, app_configuration_validated=True, app_id="123",
        app_secret="inert-sentry-app-secret", redirect_uris=("https://admin.example.test/admin/social/accounts/callback",),
        access_mode="owned_standard", active_key_version="v1", encryption_keys={"v1":Fernet.generate_key().decode()})
    with sentry_sdk.start_transaction(name="unsafe_positive_control"):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,json={}))) as client:
            client.get("https://graph.facebook.com/v26.0/debug_token",params={"input_token":token})
    assert len(sent) == 1 and token in json.dumps(sent.pop()), "unsafe capture positive control failed"
    for mode, expected in (("success", None), ("http_error", "PROVIDER_REJECTED"),
                           ("parse_error", "PROVIDER_RESPONSE_INVALID"), ("transport_error", "PROVIDER_UNAVAILABLE")):
        def fake(request):
            assert request.url.params["input_token"] == token, "wire token was not transmitted"
            if mode == "transport_error":
                raise httpx.ReadTimeout(str(request.url)+error,request=request)
            if mode == "parse_error":
                return httpx.Response(200,content=(code+error).encode())
            if mode == "http_error":
                return httpx.Response(503,json={"error":{"message":error+code,"code":1}})
            return httpx.Response(200,json={"data":{"app_id":"123","type":"USER","user_id":"701",
                "is_valid":True,"scopes":["pages_show_list"],"expires_at":0}})
        with sentry_sdk.start_transaction(name="provider_"+mode):
            provider = MetaProvider(config,transport=httpx.MockTransport(fake))
            try:
                provider.inspect_token(token,expected_type="USER")
                assert expected is None, "expected provider rejection missing"
            except SocialError as failure:
                assert failure.code == expected, "wrong safe provider failure"
            finally:
                provider.close()
    sentry_sdk.flush()
    assert len(sent) == 4 and all(kind == "transaction" and item["spans"] for kind,item in sent), "missing traced request"
    encoded = json.dumps(sent)
    assert all(value not in encoded for value in (token,code,error,config.app_secret)), "secret in outbound capture"
    print(json.dumps({"unsafe_control":1,"secret_free_transactions":4,"wire_requests":4}))
else:
    app = FastAPI()
    app.router.route_class = SocialRoute
    @app.get("/fixture/callback/{outcome}")
    def callback(outcome: str):
        if outcome == "failure":
            raise RuntimeError("inert failure")
        return {"accepted":True}
    with TestClient(app,raise_server_exceptions=False) as client:
        for outcome,status in (("success",200),("failure",500)):
            response = client.get("/fixture/callback/"+outcome,
                params={"code":code,"access_token":token,"error":error,"error_description":error})
            assert response.status_code == status, "wrong application outcome"
    sentry_sdk.flush()
    transactions = [item for kind,item in sent if kind == "transaction"]
    assert len(transactions) == 2, "missing inbound transaction positive control"
    for item in transactions:
        request = item["request"]
        assert all(value in request["query_string"] for value in (code,token,error)), "pending unsafe query capture changed"
        assert request["url"].endswith(("/success","/failure")), "missing URL readback"
    # before_send only filters error events, and leaves query data even there.
    sentry_sdk.capture_event({"message":"inert capture", "request":{"url":"https://admin.example.test/fixture/callback?code="+code,
        "query_string":"access_token="+token+"&error="+error,"headers":{"Authorization":"inert-header","Cookie":"inert-cookie"}}})
    sentry_sdk.flush()
    events = [item for kind,item in sent if kind == "event"]
    assert len(events) == 1, "missing error-event positive control"
    request = events[0]["request"]
    assert request["headers"]["Authorization"] == "[Filtered]", "current header filter did not run"
    assert request["headers"]["Cookie"] == "[Filtered]", "current cookie filter did not run"
    assert code in request["url"] and token in request["query_string"] and error in request["query_string"], "pending error-event query capture changed"
    print(json.dumps({"unsafe_inbound_transactions":2,"unsafe_error_events":1,
                      "retained_fields":["request.url","request.query_string"],"pending_ingress_gate":True}))
'''


def sentry_capture(mode):
    root = Path(__file__).resolve().parents[3]
    # No inherited DSN, keyring, dotenv or provider credentials enter this child.
    environment = {"PATH": os.defpath, "PYTHONPATH": str(root / "backend"), "PYTHON_DOTENV_DISABLED": "1"}
    result = subprocess.run([sys.executable, "-c", SENTRY_CAPTURE, mode], cwd=root,
                            env=environment, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, "isolated Sentry capture failed; no captured payload is printed"
    return json.loads(result.stdout)


def test_actual_sentry_provider_capture_has_positive_control_and_sanitized_failure_paths():
    assert sentry_capture("outbound") == {"unsafe_control": 1, "secret_free_transactions": 4, "wire_requests": 4}


def test_actual_sentry_captures_callback_queries_pending_ingress_gate():
    assert sentry_capture("inbound") == {
        "unsafe_inbound_transactions": 2, "unsafe_error_events": 1,
        "retained_fields": ["request.url", "request.query_string"], "pending_ingress_gate": True,
    }
