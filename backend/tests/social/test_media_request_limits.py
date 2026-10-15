"""Real media routes must bound metadata before JSON/dependency work."""
import asyncio
import json
from uuid import uuid4

from fastapi import FastAPI
import pytest

from social.http_boundary import AdminUser, require_admin
from social.media.api import router, service
from social.service import SocialError
from test_media_support import ACTOR, intent


LIMIT = 64 * 1024
BASE = '/api/v1/admin/social/media'


def request(chunks, *, length=None, extra_headers=(), path='/uploads', method='POST'):
    app = FastAPI()
    app.include_router(router)
    calls = []

    class Disabled:
        def initiate(self, *args):
            calls.append('initiate')
            raise SocialError('MEDIA_UNAVAILABLE', 'Disabled fixture.', 503)

        def complete(self, *args):
            calls.append('complete')
            raise SocialError('MEDIA_UNAVAILABLE', 'Disabled fixture.', 503)

    def disabled_service():
        calls.append('dependency')
        return Disabled()

    app.dependency_overrides[service] = disabled_service
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(ACTOR), email=None, roles=['admin'])
    headers = [(b'content-type', b'application/json'), (b'idempotency-key', str(uuid4()).encode())]
    if length is not None:
        headers.append((b'content-length', length))
    headers.extend(extra_headers)
    received, sent = [], []

    async def receive():
        index = len(received)
        if index >= len(chunks):
            return {'type': 'http.disconnect'}
        received.append(index)
        return {'type': 'http.request', 'body': chunks[index], 'more_body': index + 1 < len(chunks)}

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': method, 'scheme': 'https', 'path': BASE + path,
             'raw_path': (BASE + path).encode(), 'root_path': '', 'query_string': b'',
             'headers': headers, 'server': ('fixture.test', 443), 'client': ('127.0.0.1', 1)}
    asyncio.run(app(scope, receive, send))
    start = next(item for item in sent if item['type'] == 'http.response.start')
    body = b''.join(item.get('body', b'') for item in sent if item['type'] == 'http.response.body')
    return start['status'], dict(start['headers']), json.loads(body), received, calls


def upload(size):
    body = json.dumps(intent()).encode()
    return body + b' ' * (size - len(body))


@pytest.mark.parametrize('path,body', [('/uploads', upload(LIMIT + 1)),
                                    (f'/uploads/{uuid4()}/complete', b'{"expected_version":1}' + b' ' * LIMIT)], ids=['initiate', 'complete'])
@pytest.mark.parametrize('length', [None, b'1', str(LIMIT + 1).encode()], ids=['absent', 'understated', 'oversize'])
def test_both_metadata_commands_reject_oversized_bodies_before_dependencies(path, body, length):
    status, headers, data, _, calls = request([body], length=length, path=path)
    assert status == 413
    assert data['detail']['code'] == 'MEDIA_REQUEST_TOO_LARGE'
    assert headers[b'cache-control'] == b'private, no-store'
    assert headers[b'x-request-id']
    assert calls == []


def test_declared_oversize_does_not_consume_any_body():
    status, _, _, reads, calls = request([b'never read'], length=str(LIMIT + 1).encode())
    assert status == 413
    assert reads == [] and calls == []


def test_chunked_oversize_stops_at_the_crossing_chunk():
    status, _, _, reads, calls = request([upload(LIMIT), b'x', b'never read'])
    assert status == 413
    assert reads == [0, 1] and calls == []


@pytest.mark.parametrize('length', [None, str(LIMIT).encode()])
def test_exact_limit_reaches_existing_route_and_service(length):
    status, headers, data, reads, calls = request([upload(LIMIT // 2), b' ' * (LIMIT // 2)], length=length)
    assert status == 503 and data['detail']['code'] == 'MEDIA_UNAVAILABLE'
    assert calls == ['dependency', 'initiate'] and reads == [0, 1]
    assert headers[b'cache-control'] == b'private, no-store'


@pytest.mark.parametrize('length', [b'-1', b'1.5', b'+1', b' 1', b'x', b'', b'9' * 5000], ids=['negative', 'fraction', 'plus', 'space', 'text', 'empty', 'overlong'])
def test_invalid_length_refuses_before_reading(length):
    status, headers, data, reads, calls = request([upload(512)], length=length)
    assert status == 400 and data['detail']['code'] == 'INVALID_REQUEST'
    assert headers[b'cache-control'] == b'private, no-store'
    assert reads == [] and calls == []


def test_duplicate_lengths_refuse_before_reading():
    status, _, data, reads, calls = request([upload(512)], length=b'512', extra_headers=[(b'content-length', b'512')])
    assert status == 400 and data['detail']['code'] == 'INVALID_REQUEST'
    assert reads == [] and calls == []
