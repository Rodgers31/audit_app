"""Refresh followers and provider bodies cannot consume unbounded auth resources."""

import gzip
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import httpx
import pytest
from fastapi import HTTPException

import supabase_auth as auth

MAX_BODY_BYTES = 64 * 1024


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setenv("SUPABASE_URL", "https://transport-fixture.invalid")
    monkeypatch.setattr(auth, "_jwks_cache", None)
    monkeypatch.setattr(auth, "_jwks_cache_ts", 0)
    monkeypatch.setattr(auth, "_jwks_last_attempt_ts", None)
    monkeypatch.setattr(auth, "_jwks_refresh_in_flight", False, raising=False)
    monkeypatch.setattr(auth, "_jwks_clock", lambda: now[0])
    return now


@pytest.mark.parametrize("warm", [False, True])
def test_refresh_followers_finish_before_the_provider_is_released(
    clock, monkeypatch, warm
):
    entered, release = Event(), Event()
    document = {"keys": []}
    calls = []
    if warm:
        auth._jwks_cache, auth._jwks_cache_ts = document, clock[0]

    def response(url):
        calls.append(url)
        entered.set()
        assert release.wait(2), "fixture did not release the refresh leader"
        return httpx.Response(
            200,
            stream=httpx.ByteStream(json.dumps(document).encode()),
            request=httpx.Request("GET", url),
        )

    def get(url, **kwargs):
        result = response(url)
        result.read()
        return result

    monkeypatch.setattr(auth.httpx, "get", get)

    def stream(method, url, **kwargs):
        class PausedResponse:
            def __enter__(self):
                return response(url)

            def __exit__(self, *args):
                return False

        return PausedResponse()

    monkeypatch.setattr(auth.httpx, "stream", stream)

    def follower():
        try:
            return auth._fetch_jwks()
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(auth._fetch_jwks, force_refresh=warm)
        assert entered.wait(1)
        pending = pool.submit(follower)
        try:
            try:
                result = pending.result(timeout=0.5)
            except TimeoutError:
                pytest.fail("auth follower waited for provider I/O")
            assert result == (document if warm else 503)
            assert not release.is_set()
        finally:
            release.set()
            assert leader.result(timeout=2) == document
    assert len(calls) == 1


class ObservedBody(httpx.SyncByteStream):
    def __init__(self, chunks, on_read=None):
        self.chunks = chunks
        self.on_read = on_read
        self.read_bytes = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            if self.on_read:
                self.on_read()
            self.read_bytes += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    clients = []

    def install(body, headers=None):
        stream = ObservedBody([body[i : i + 1024] for i in range(0, len(body), 1024)])
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, headers=headers, stream=stream)

        client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        clients.append(client)
        monkeypatch.setattr(auth.httpx, "get", client.get)
        monkeypatch.setattr(auth.httpx, "stream", client.stream)
        return stream, requests

    yield install
    for client in clients:
        client.close()


def padded_document(size):
    envelope = b'{"keys":[],"padding":""}'
    return b'{"keys":[],"padding":"' + b"x" * (size - len(envelope)) + b'"}'


def unavailable():
    with pytest.raises(HTTPException) as result:
        auth._fetch_jwks()
    assert result.value.status_code == 503
    assert auth._jwks_cache is None
    assert not auth._jwks_refresh_in_flight


def test_chunked_oversized_document_stops_before_it_is_buffered(clock, transport):
    body, _ = transport(padded_document(MAX_BODY_BYTES * 2))
    unavailable()
    assert body.closed
    assert body.read_bytes <= MAX_BODY_BYTES + 1024


def test_small_healthy_document_is_accepted(clock, transport):
    body, _ = transport(b'{"keys":[]}')
    assert auth._fetch_jwks() == {"keys": []}
    assert body.closed


@pytest.mark.parametrize("length", [str(MAX_BODY_BYTES + 1), "-1", "1,1", "NaN"])
def test_invalid_declared_length_is_refused_before_body_read(clock, transport, length):
    body, _ = transport(b'{"keys":[]}', {"Content-Length": length})
    unavailable()
    assert body.closed and body.read_bytes == 0


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Encoding", "gzip")],
        [("Content-Encoding", "identity"), ("Content-Encoding", "gzip")],
    ],
)
def test_encoded_response_is_refused_before_decompression(clock, transport, headers):
    body, _ = transport(gzip.compress(b'{"keys":[]}'), headers)
    unavailable()
    assert body.closed and body.read_bytes == 0


def test_exact_limit_document_is_accepted_and_closed(clock, transport):
    raw = padded_document(MAX_BODY_BYTES)
    body, requests = transport(raw)
    assert auth._fetch_jwks() == json.loads(raw)
    assert body.read_bytes == MAX_BODY_BYTES and body.closed
    assert requests[0].headers["accept-encoding"] == "identity"
    assert not auth._jwks_refresh_in_flight


def test_late_body_cannot_publish_and_refresh_can_recover(clock, transport):
    body, _ = transport(b'{"keys":[]}')
    body.on_read = lambda: clock.__setitem__(0, clock[0] + 6)
    unavailable()
    assert body.closed
    clock[0] += 31
    healed, _ = transport(b'{"keys":[]}')
    assert auth._fetch_jwks() == {"keys": []}
    assert healed.closed and not auth._jwks_refresh_in_flight
