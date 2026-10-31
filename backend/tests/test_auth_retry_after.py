"""Cold key-cache followers retain refusal and tell safe readers when to retry."""
from concurrent.futures import ThreadPoolExecutor
import threading

from fastapi import HTTPException
import pytest
import httpx

import supabase_auth as auth


@pytest.fixture
def cold(monkeypatch):
    for name, value in (("_jwks_cache", None), ("_jwks_cache_ts", 0),
                        ("_jwks_last_attempt_ts", None), ("_jwks_refresh_in_flight", False)):
        monkeypatch.setattr(auth, name, value)
    monkeypatch.setattr(auth, "_jwks_clock", lambda: 100.0)


def test_cold_followers_get_retry_advice_without_duplicate_key_fetch(cold, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def read():
        calls.append(True)
        entered.set()
        if not release.wait(2):
            raise RuntimeError("Owned leader was not released")
        return {"keys": []}

    monkeypatch.setattr(auth, "_read_jwks", read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        leader = pool.submit(auth._fetch_jwks)
        try:
            assert entered.wait(1)
            for _ in range(7):
                with pytest.raises(HTTPException) as caught:
                    auth._fetch_jwks()
                assert caught.value.status_code == 503
                assert (caught.value.headers or {}).get("Retry-After") == "1"
            assert len(calls) == 1
        finally:
            release.set()
        assert leader.result(timeout=1) == {"keys": []}
    assert auth._fetch_jwks() == {"keys": []}
    assert len(calls) == 1


def test_provider_failure_cooldown_does_not_invite_an_immediate_retry(cold, monkeypatch):
    def fail():
        raise ValueError("Inert private issuer detail")

    monkeypatch.setattr(auth, "_read_jwks", fail)
    with pytest.raises(HTTPException) as caught:
        auth._fetch_jwks()
    assert caught.value.status_code == 503
    assert (caught.value.headers or {}).get("Retry-After") == "30"
    monkeypatch.setattr(auth, "_jwks_clock", lambda: 110.5)
    with pytest.raises(HTTPException) as caught:
        auth._fetch_jwks()
    assert (caught.value.headers or {}).get("Retry-After") == "20"
    assert "private" not in str(caught.value.detail)


def test_slow_provider_failure_advertises_the_remaining_attempt_cooldown(cold, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(auth, '_jwks_clock', lambda: clock[0])

    def fail():
        clock[0] += 4.25
        raise ValueError('Inert delayed issuer refusal')

    monkeypatch.setattr(auth, '_read_jwks', fail)
    with pytest.raises(HTTPException) as leader:
        auth._fetch_jwks()
    with pytest.raises(HTTPException) as follower:
        auth._fetch_jwks()
    assert leader.value.headers['Retry-After'] == follower.value.headers['Retry-After'] == '26'


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed', [True, False])
async def test_admin_refusal_exposes_only_retry_advice_to_the_configured_browser(monkeypatch, allowed):
    import main

    def unavailable():
        raise HTTPException(503, "Authentication keys temporarily unavailable", headers={"Retry-After": "1"})

    monkeypatch.setattr(main.app, "dependency_overrides", {**main.app.dependency_overrides, auth.get_current_user: unavailable})
    cors = next(m for m in main.app.user_middleware if m.cls.__name__ == 'CORSMiddleware')
    origin = cors.kwargs['allow_origins'][0] if allowed else 'https://unconfigured.example.invalid'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://owned.test") as client:
        response = await client.get("/api/v1/admin/users/stats", headers={"Origin": origin, "Authorization": "Bearer inert"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert 'access-control-allow-origin' not in response.headers
    exposed = {x.strip().lower() for x in response.headers.get("access-control-expose-headers", "").split(",")}
    assert "retry-after" in exposed
    assert "authorization" not in exposed and "set-cookie" not in exposed
    assert "no-store" in response.headers["cache-control"]
