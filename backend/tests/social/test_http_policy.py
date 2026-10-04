"""Execute the namespace policy, including errors outside registered routes."""
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from social.http_policy import SocialNoStoreMiddleware


@pytest.mark.parametrize("status", [401, 403, 404, 405, 422, 429, 500, 503])
def test_social_namespace_overrides_cacheable_error_headers(status):
    app = FastAPI()

    @app.middleware("http")
    async def rejection(request, call_next):
        return JSONResponse(
            {"detail": "fixture rejection"},
            status_code=status,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    app.add_middleware(SocialNoStoreMiddleware)
    response = TestClient(app).get("/api/v1/admin/social/unmatched")
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"


def test_unmatched_paths_and_methods_private_public_endpoints_unchanged():
    app = FastAPI()

    @app.get("/api/v1/admin/social/fixture")
    def fixture():
        return {"fixture": True}

    @app.get("/api/v1/public")
    def public_fixture():
        return JSONResponse({}, headers={"Cache-Control": "public, max-age=60"})

    app.add_middleware(SocialNoStoreMiddleware)
    client = TestClient(app)
    for response in [
        client.get("/api/v1/admin/social"),
        client.get("/api/v1/admin/social/missing"),
        client.post("/api/v1/admin/social/fixture"),
    ]:
        assert response.status_code in {404, 405}
        assert response.headers["cache-control"] == "private, no-store"
    assert client.get("/api/v1/public").headers["cache-control"] == "public, max-age=60"
    assert "cache-control" not in client.get("/api/v1/admin/socialish").headers


@pytest.mark.parametrize("middleware_failure", [False, True])
def test_unhandled_exception_remains_private_and_safe(middleware_failure, caplog):
    app = FastAPI()

    @app.get("/api/v1/admin/social/throw")
    def throw():
        raise RuntimeError("fixture_secret_must_not_escape")

    if middleware_failure:
        @app.middleware("http")
        async def throw_outside_router(request, call_next):
            raise RuntimeError("fixture_secret_must_not_escape")

    app.add_middleware(SocialNoStoreMiddleware)
    with caplog.at_level(logging.INFO, logger="social"):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/admin/social/throw"
        )
    assert response.status_code == 500
    assert response.headers.get("cache-control") == "private, no-store"
    assert "fixture_secret_must_not_escape" not in response.text
    assert response.json()["detail"]["code"] == "SOCIAL_INTERNAL_ERROR"
    event = json.loads(next(record.message for record in caplog.records if record.name == "social"))
    assert event["request_id"] == response.headers["x-request-id"]
    assert event["error_code"] == "SOCIAL_INTERNAL_ERROR"
    assert "fixture_secret_must_not_escape" not in caplog.text
