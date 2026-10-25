"""Rejected bearer tokens must not create one upstream request per key ID."""

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
import jwt

import supabase_auth as auth


def unsigned(header):
    def part(value):
        return (
            base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
        )

    return f"{part(header)}.{part({'aud': 'authenticated'})}.AA"


@pytest.fixture
def provider(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key())) | {
        "kid": "current"
    }
    calls = []
    clock = [1000.0]
    monkeypatch.setenv("SUPABASE_URL", "https://auth.example.invalid")
    monkeypatch.setattr(auth, "_jwks_cache", None)
    monkeypatch.setattr(auth, "_jwks_cache_ts", 0)
    monkeypatch.setattr(auth, "_jwks_last_attempt_ts", None, raising=False)
    monkeypatch.setattr(auth, "_jwks_refresh_in_flight", False)
    monkeypatch.setattr(auth, "_jwks_clock", lambda: clock[0], raising=False)

    @contextmanager
    def stream(method, url, **kwargs):
        args = (method, url)
        calls.append((args, kwargs))
        response = httpx.Response(
            200,
            stream=httpx.ByteStream(json.dumps({"keys": [public]}).encode()),
            request=httpx.Request(method, url),
        )
        try:
            yield response
        finally:
            response.close()

    monkeypatch.setattr(auth.httpx, "stream", stream)

    def token(kid="current"):
        return jwt.encode(
            {
                "sub": "fixture-user",
                "aud": "authenticated",
                "exp": int(time.time()) + 300,
            },
            private,
            algorithm="ES256",
            headers={"kid": kid},
        )

    return calls, clock, public, token, stream


def test_random_key_ids_share_one_refresh_budget(provider):
    calls, _, _, _, _ = provider
    for n in range(4):
        with pytest.raises(HTTPException) as denied:
            auth._decode_supabase_jwt(unsigned({"alg": "ES256", "kid": f"unknown-{n}"}))
        assert denied.value.status_code == 401
    assert len(calls) == 1, "unverified key IDs amplified outbound JWKS requests"


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "none", "kid": "current"},
        {"alg": "HS512", "kid": "current"},
        {"alg": "ES256"},
        {"alg": "ES256", "kid": []},
        {"alg": "ES256", "kid": ""},
        {"alg": "ES256", "kid": "x" * 257},
    ],
)
def test_invalid_header_never_fetches_keys(provider, header):
    calls, _, _, _, _ = provider
    with pytest.raises(HTTPException) as denied:
        auth._decode_supabase_jwt(unsigned(header))
    assert denied.value.status_code == 401
    assert calls == []


def test_valid_signature_and_rotation_still_work(provider):
    calls, clock, public, token, _ = provider
    assert auth._decode_supabase_jwt(token())["sub"] == "fixture-user"
    public["kid"] = "rotated"
    with pytest.raises(HTTPException):
        auth._decode_supabase_jwt(token("rotated"))
    assert len(calls) == 1
    clock[0] += 31
    assert auth._decode_supabase_jwt(token("rotated"))["sub"] == "fixture-user"
    assert len(calls) == 2


def test_provider_failure_has_a_retry_budget(provider, monkeypatch):
    calls, _, _, _, _ = provider

    def failed(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError("inert outage")

    monkeypatch.setattr(auth.httpx, "stream", failed)
    for _ in range(4):
        with pytest.raises(HTTPException) as denied:
            auth._decode_supabase_jwt(unsigned({"alg": "ES256", "kid": "current"}))
        assert denied.value.status_code == 503
    assert len(calls) == 1


def test_concurrent_cold_requests_share_a_fetch(provider, monkeypatch):
    calls, _, _, token, stream = provider
    entered, release = Event(), Event()

    @contextmanager
    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(2), "fixture did not release provider"
        with stream(*args, **kwargs) as response:
            yield response

    monkeypatch.setattr(auth.httpx, "stream", paused)
    signed = token()

    def follow():
        with pytest.raises(HTTPException) as denied:
            auth._decode_supabase_jwt(signed)
        return denied.value.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(auth._decode_supabase_jwt, signed)
        assert entered.wait(2)
        others = [pool.submit(follow) for _ in range(3)]
        try:
            assert all(f.result(timeout=0.5) == 503 for f in others)
        finally:
            release.set()
        assert first.result(timeout=3)["sub"] == "fixture-user"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "document", [None, [], {}, {"keys": None}, {"keys": [None]}, {"keys": [{}] * 21}]
)
def test_malformed_provider_response_refuses_and_backs_off(
    provider, monkeypatch, document
):
    calls, _, _, _, _ = provider

    @contextmanager
    def malformed(method, url, **kwargs):
        calls.append(1)
        response = httpx.Response(
            200,
            stream=httpx.ByteStream(json.dumps(document).encode()),
            request=httpx.Request(method, url),
        )
        try:
            yield response
        finally:
            response.close()

    monkeypatch.setattr(auth.httpx, "stream", malformed)
    for _ in range(2):
        with pytest.raises(HTTPException) as denied:
            auth._fetch_jwks()
        assert denied.value.status_code == 503
    assert len(calls) == 1


def test_expired_keys_do_not_authorize_during_provider_failure(provider, monkeypatch):
    _, clock, _, token, _ = provider
    signed = token()
    assert auth._decode_supabase_jwt(signed)["sub"] == "fixture-user"
    clock[0] += 3601

    def failed(*args, **kwargs):
        raise httpx.ConnectError("inert outage")

    monkeypatch.setattr(auth.httpx, "stream", failed)
    for _ in range(2):
        with pytest.raises(HTTPException) as denied:
            auth._decode_supabase_jwt(signed)
        assert denied.value.status_code == 503


def test_oversized_token_does_not_fetch_keys(provider):
    calls, _, _, _, _ = provider
    with pytest.raises(HTTPException) as denied:
        auth._decode_supabase_jwt("x" * 16_385)
    assert denied.value.status_code == 401
    assert calls == []
