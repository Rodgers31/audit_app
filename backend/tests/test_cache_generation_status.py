"""Worker acknowledgements must describe a completed local cache clear."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cache import invalidation
from routers.cache_invalidation import router

SECRET = "local-generation-status-test-key"
STATUS = "/api/v1/system/cache/status"


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("REVALIDATE_SECRET", SECRET)
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "generation"))
    monkeypatch.setattr(invalidation, "_local_caches", {})
    monkeypatch.setattr(invalidation, "_redis_instances", lambda: [])
    monkeypatch.setattr(invalidation, "_seen", None)
    monkeypatch.setattr(invalidation, "_seen_initialised", False)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def signed(client, path=STATUS, body=None, secret=SECRET):
    raw = json.dumps(body if body is not None else {"ts": time.time()}).encode()
    return client.post(
        path,
        content=raw,
        headers={"x-revalidate-signature": hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()},
    )


def test_failed_clear_must_retry_same_generation(isolated):
    cached = {"county": "old"}
    calls = []

    def clear():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("temporary clear failure")
        size = len(cached)
        cached.clear()
        return size

    invalidation.register_local_cache("county", clear)
    invalidation.sync_generation()
    previous = invalidation._seen
    invalidation.bump_generation()
    with pytest.raises(RuntimeError, match="temporary clear failure"):
        invalidation.sync_generation()
    assert invalidation._seen == previous
    assert invalidation.sync_generation() is True
    assert cached == {}
    assert len(calls) == 2


def test_status_identifies_loaded_path_and_adopted_generation(isolated, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    first = signed(isolated)
    assert first.status_code == 200
    assert first.json()["observed_identity"] is None
    ack = signed(isolated, "/api/v1/system/cache/invalidate")
    assert ack.status_code == 200
    response = signed(isolated)
    assert response.status_code == 200
    body = response.json()
    assert body["synchronised"] is True
    assert body["observed_identity"] == ack.json()["marker_identity"]
    assert body["adopted_identity"] == ack.json()["marker_identity"]
    assert body["marker_path"] == invalidation.marker_path()
    assert body["pid"] == ack.json()["pid"]
    assert body["commit"] == "a" * 40
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [STATUS, "/api/v1/system/cache/invalidate"])
@pytest.mark.parametrize("body", [[], None, {}, {"ts": True}, {"ts": float("nan")}, {"ts": 0}])
def test_invalid_signed_inputs_do_not_acknowledge(isolated, path, body):
    # Encode null explicitly; signed() otherwise supplies the valid default.
    raw = json.dumps(body).encode()
    response = isolated.post(path, content=raw, headers={
        "x-revalidate-signature": hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    })
    assert response.status_code in (400, 401)
    assert invalidation._seen_initialised is False
    assert invalidation.generation_identity() is None


def test_status_refuses_missing_wrong_and_unconfigured_signatures(isolated, monkeypatch):
    assert isolated.post(STATUS, json={"ts": time.time()}).status_code == 401
    assert signed(isolated, secret="wrong").status_code == 401
    monkeypatch.delenv("REVALIDATE_SECRET")
    assert signed(isolated).status_code == 503


def test_status_does_not_certify_unreadable_marker(isolated, monkeypatch):
    def unreadable():
        raise PermissionError("marker unreadable")
    monkeypatch.setattr(invalidation, "_stat_token", unreadable)
    response = signed(isolated)
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "generation_marker_unreadable"


def test_status_does_not_certify_failed_clear(isolated):
    invalidation.sync_generation()
    invalidation.bump_generation()
    def fail():
        raise RuntimeError("cache clear unavailable")
    invalidation.register_local_cache("county", fail)
    response = signed(isolated)
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "local_invalidation_failed"
    assert invalidation._seen is None


@pytest.mark.parametrize("competing", ["delete", "replace"])
def test_invalidation_does_not_acknowledge_missing_or_competing_marker(isolated, monkeypatch, competing):
    from pathlib import Path
    publish = invalidation._publish_generation
    def interrupted():
        result = publish()
        if competing == "delete":
            Path(invalidation.marker_path()).unlink()
        else:
            publish()
        return result
    monkeypatch.setattr(invalidation, "_publish_generation", interrupted)
    response = signed(isolated, "/api/v1/system/cache/invalidate")
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "generation_marker_changed"
    assert invalidation._seen_initialised is False
