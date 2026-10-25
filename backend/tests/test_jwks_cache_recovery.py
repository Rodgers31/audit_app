"""A malformed provider response must not outlive recovery as cached auth state."""

import json
import time
from contextlib import contextmanager

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

import supabase_auth as auth


@pytest.fixture
def provider(monkeypatch):
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    public.update(kid="recovery-fixture", alg="ES256")
    document = {"keys": [public]}
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        },
        private,
        algorithm="ES256",
        headers={"kid": "recovery-fixture"},
    )
    monkeypatch.setenv("SUPABASE_URL", "https://recovery-fixture.invalid")
    monkeypatch.setattr(auth, "_jwks_cache", None)
    monkeypatch.setattr(auth, "_jwks_cache_ts", 0)
    monkeypatch.setattr(auth, "_jwks_last_attempt_ts", None)
    monkeypatch.setattr(auth, "_jwks_refresh_in_flight", False)
    clock = [1000.0]
    monkeypatch.setattr(auth, "_jwks_clock", lambda: clock[0])
    return document, token, clock


@contextmanager
def key_response(method, url, document):
    response = httpx.Response(
        200,
        stream=httpx.ByteStream(json.dumps(document).encode()),
        request=httpx.Request(method, url),
    )
    try:
        yield response
    finally:
        response.close()


@pytest.mark.parametrize("malformed", [[], {}, {"keys": None}, {"keys": [None]}])
def test_provider_recovery_does_not_wait_for_poisoned_cache_ttl(
    provider, monkeypatch, malformed
):
    healthy, token, clock = provider
    replies = [malformed, healthy]
    calls = []

    def stream(method, url, **kwargs):
        calls.append(url)
        return key_response(method, url, replies.pop(0))

    monkeypatch.setattr(auth.httpx, "stream", stream)
    with pytest.raises(HTTPException):
        auth._decode_supabase_jwt(token)
    with pytest.raises(HTTPException) as cooling_down:
        auth._decode_supabase_jwt(token)
    assert cooling_down.value.status_code == 503
    assert len(calls) == 1
    # The fixed attempt cooldown applies; the poisoned one-hour TTL must not.
    clock[0] += 31
    assert auth._decode_supabase_jwt(token)["aud"] == "authenticated"
    assert len(calls) == 2
    assert auth._jwks_cache == healthy


def test_failed_forced_refresh_preserves_last_valid_document(provider, monkeypatch):
    healthy, _, clock = provider
    observed_at = clock[0]
    monkeypatch.setattr(auth, "_jwks_cache", healthy)
    monkeypatch.setattr(auth, "_jwks_cache_ts", observed_at)
    monkeypatch.setattr(
        auth.httpx,
        "stream",
        lambda method, url, **_: key_response(method, url, {"keys": None}),
    )
    with pytest.raises(HTTPException) as unavailable:
        auth._fetch_jwks(force_refresh=True)
    assert unavailable.value.status_code == 503
    assert auth._jwks_cache == healthy
    assert auth._jwks_cache_ts == observed_at


def test_healthy_cached_key_needs_no_provider_request(provider, monkeypatch):
    healthy, token, clock = provider
    monkeypatch.setattr(auth, "_jwks_cache", healthy)
    monkeypatch.setattr(auth, "_jwks_cache_ts", clock[0])
    monkeypatch.setattr(
        auth.httpx, "stream", lambda *_, **__: pytest.fail("fresh key must use cache")
    )
    assert auth._decode_supabase_jwt(token)["aud"] == "authenticated"
