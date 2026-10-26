"""Tiny owned ASGI workloads prove request admission, without external services."""
import asyncio
import pytest
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from middleware import security


def run(value):
    return asyncio.run(value)


def request(ip='192.0.2.1', path='/x', method='GET'):
    return Request({'type': 'http', 'method': method, 'path': path, 'headers': [],
                    'query_string': b'', 'client': None if ip is None else (ip, 1)})


async def accepted(_):
    return JSONResponse({'ok': True})


@pytest.mark.parametrize('cls', [security.RateLimitMiddleware, security.RedisRateLimitMiddleware])
@pytest.mark.parametrize('ip', ['127.0.0.1', '::1', None])
def test_loopback_and_missing_peer_share_enforced_budgets(cls, ip):
    limiter = cls(FastAPI(), calls=2, period=60)
    if cls is security.RedisRateLimitMiddleware:
        limiter.redis_client = object()  # Explicit local-only mode, no Redis initialization.
    dispatch = getattr(cls, '_original_dispatch', cls.dispatch)
    async def exercise():
        return [(await dispatch(limiter, request(ip), accepted)).status_code for _ in range(3)]
    assert run(exercise()) == [200, 200, 429]


def test_rotating_ips_cannot_bypass_aggregate_process_budget():
    limiter = security.RateLimitMiddleware(FastAPI(), calls=10, period=60)
    limiter.aggregate_calls = 3
    dispatch = getattr(type(limiter), '_original_dispatch', type(limiter).dispatch)
    async def exercise():
        return [(await dispatch(limiter, request(f'192.0.2.{n}'), accepted)).status_code for n in range(4)]
    assert run(exercise()) == [200, 200, 200, 429]
    assert len(limiter.clients) <= 3, 'Globally refused peers still consume the per-peer storage budget'


def test_redis_slow_operation_releases_to_bounded_visible_local_mode():
    class Pipe:
        def incr(self, *args): return self
        def expire(self, *args): return self
        async def execute(self): await asyncio.Event().wait()
    class SlowRedis:
        def pipeline(self): return Pipe()
        async def eval(self, *args): await asyncio.Event().wait()
    limiter = security.RedisRateLimitMiddleware(FastAPI(), calls=2, period=60)
    limiter.redis_client = SlowRedis()
    limiter.use_redis = True
    limiter.redis_timeout = .01
    dispatch = getattr(type(limiter), '_original_dispatch', type(limiter).dispatch)
    async def exercise():
        first = await asyncio.wait_for(dispatch(limiter, request(), accepted), .2)
        assert first.status_code == 200
        assert limiter.use_redis is False
        assert limiter.status['rate_limit_mode'] == 'degraded_memory'
        assert (await dispatch(limiter, request(), accepted)).status_code == 200
        assert (await dispatch(limiter, request(), accepted)).status_code == 429
    run(exercise())


def test_optional_redis_initialization_is_bounded_and_does_not_reset_local_budget(monkeypatch):
    created = []
    class SlowRedis:
        closed=False
        def __await__(self):
            async def ready(): return self
            return ready().__await__()
        async def ping(self): await asyncio.Event().wait()
        async def aclose(self): self.closed=True
    client = SlowRedis()
    def construct(*args,**kwargs): created.append(True);return client
    monkeypatch.setattr(security.aioredis,'from_url',construct)
    monkeypatch.setattr(type(security.settings),'REDIS_URL',property(lambda self:'redis://fixture.invalid'))
    limiter=security.RedisRateLimitMiddleware(FastAPI(),calls=1,period=60)
    limiter.redis_timeout=.01
    dispatch=getattr(type(limiter),'_original_dispatch',type(limiter).dispatch)
    async def exercise():
        assert (await asyncio.wait_for(dispatch(limiter,request(),accepted),.2)).status_code == 200
        assert limiter.status['rate_limit_mode']=='degraded_memory'
        assert client.closed is True
        assert (await dispatch(limiter,request(),accepted)).status_code == 429
        assert created == [True]
    run(exercise())


async def asgi_call(app, *, body=b'', query=b'', headers=(), method='POST', path='/x', chunks=None):
    events = list(chunks if chunks is not None else [{'type': 'http.request', 'body': body, 'more_body': False}])
    out = []
    async def receive():
        if events:
            return events.pop(0)
        await asyncio.Event().wait()
    async def send(message): out.append(message)
    await app({'type':'http', 'method':method, 'path':path, 'raw_path':path.encode(),
               'query_string':query, 'headers':list(headers), 'client':('192.0.2.1',1),
               'server':('test',80), 'scheme':'http', 'http_version':'1.1'}, receive, send)
    return out


def bounded(app, **kwargs):
    # Frozen service had no resource guard. Exercise its unguarded behavior as
    # the red control; the installed middleware is the green entry point.
    cls = getattr(security, 'RequestResourceMiddleware', None)
    return cls(app, **kwargs) if cls else app


async def consume(scope, receive, send):
    value = bytearray()
    while True:
        event = await receive()
        value.extend(event.get('body', b''))
        if not event.get('more_body'):
            break
    await JSONResponse({'bytes':len(value)})(scope, receive, send)


@pytest.mark.parametrize('kwargs,expected', [
    ({'body':b'x'*17},413),
    ({'query':b'x'*17,'method':'GET'},414),
    ({'headers':[(b'content-length',b'1'),(b'content-length',b'1')]},400),
    ({'headers':[(b'content-length',b'3')],'body':b'x'},400),
    ({'headers':[(b'content-length',b'1'),(b'transfer-encoding',b'chunked')]},400),
    ({'headers':[(b'content-encoding',b'gzip')],'body':b'compressed'},415),
])
def test_rejects_large_or_ambiguous_input_before_handler(kwargs, expected):
    called = []
    async def endpoint(*args):
        called.append(True)
        await consume(*args)
    guard = bounded(endpoint, max_body=16, max_query=16)
    events = run(asgi_call(guard, **kwargs))
    assert events[0]['status'] == expected
    assert called == []


def test_chunked_bound_and_exact_signed_bytes_are_preserved():
    guard = bounded(consume, max_body=16)
    chunks = [{'type':'http.request','body':b'raw\x00','more_body':True},
              {'type':'http.request','body':b'signed','more_body':False}]
    headers=[(b'content-type',b'application/octet-stream')]
    events = run(asgi_call(guard, chunks=chunks,headers=headers))
    assert events[0]['status'] == 200
    assert b'10' in events[1]['body']
    chunks[1]['body'] = b'x'*17
    assert run(asgi_call(guard, chunks=chunks,headers=headers))[0]['status'] == 413


def test_slow_body_deadline_and_cancellation_release_admission():
    async def exercise():
        guard = bounded(consume, max_body=16, body_timeout=.01, max_inflight=1)
        events = await asyncio.wait_for(asgi_call(guard, chunks=[]), .2)
        assert events[0]['status'] == 408
        assert (await asgi_call(guard, body=b'ok'))[0]['status'] == 200
    run(exercise())


def test_cancelled_downstream_request_releases_all_admission_state():
    async def exercise():
        entered = asyncio.Event()
        async def endpoint(*args):
            entered.set()
            await asyncio.Event().wait()
        guard = bounded(endpoint, max_inflight=1)
        task = asyncio.create_task(asgi_call(guard,body=b'owned'))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert guard.inflight == 0
        assert guard.buffered == 0
    run(exercise())


def test_parallel_bodies_share_one_process_byte_budget():
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.set()
            await release.wait()
            await consume(scope, receive, send)
        guard = bounded(endpoint,max_body=16,max_buffered=8,max_inflight=3)
        first = asyncio.create_task(asgi_call(guard,body=b'123456'))
        await entered.wait()
        try:
            second = await asyncio.wait_for(asgi_call(guard,body=b'789'),.2)
            assert second[0]['status'] == 503
            assert b'BODY_CAPACITY_EXCEEDED' in second[1]['body']
            assert guard.buffered == 6
        finally:
            release.set()
            await first
        assert guard.inflight == guard.buffered == 0
    run(exercise())


def test_inflight_saturation_refuses_without_queue_and_health_stays_available():
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            if scope['path'] == '/x':
                entered.set()
                await release.wait()
            await consume(scope, receive, send)
        guard = bounded(endpoint, max_inflight=1)
        first = asyncio.create_task(asgi_call(guard))
        await entered.wait()
        try:
            assert (await asyncio.wait_for(asgi_call(guard), .2))[0]['status'] == 503
            assert (await asgi_call(guard, path='/health/live', method='GET'))[0]['status'] == 200
        finally:
            release.set()
            await first
        assert (await asgi_call(guard))[0]['status'] == 200
    run(exercise())


def test_largest_declared_social_document_fits_wire_body_budget():
    import json
    from uuid import UUID
    from social.contracts import CreatePost
    text = '\U0001f600'
    link = 'https://example.invalid/' + text * 2000
    media = [{'asset_id':str(UUID(int=n+1)), 'alt_text':text*2000} for n in range(35)]
    master = dict(text=text*20000, link=link, hashtags=[text*100]*50, media=media)
    overrides = {name:{'mode':'replace','value':value} for name,value in master.items()}
    document = CreatePost.model_validate(dict(title=text*300, document=dict(master=master,
        targets=[dict(account_id=str(UUID(int=n+100)), format='carousel', overrides=overrides) for n in range(25)]),
        references=[dict(url=link,label=text*300) for _ in range(30)]))
    wire = json.dumps(document.model_dump(mode='json'), ensure_ascii=True).encode()
    assert len(wire) > 30_000_000, 'The positive control no longer covers the largest declared fields'
    assert run(asgi_call(bounded(consume), body=wire))[0]['status'] == 200


@pytest.mark.parametrize('authorization', [None, b'Bearer invalid-local-token'])
def test_large_admin_json_has_same_predecode_ceiling_without_verified_auth(authorization):
    from fastapi import Depends
    from supabase_auth import require_admin
    app = FastAPI()
    @app.post('/api/v1/admin/local-guard-control')
    def endpoint(body: dict, admin=Depends(require_admin)):
        pytest.fail('Absent or invalid bearer reached a protected handler')
    headers = [(b'content-type',b'application/json')]
    if authorization:
        headers.append((b'authorization',authorization))
    events = run(asgi_call(bounded(app,max_body=64), path='/api/v1/admin/local-guard-control',
        body=b'{"value":"'+b'x'*64+b'"}',headers=headers))
    assert events[0]['status'] == 413


@pytest.mark.parametrize('header', [None,b'application/problem+json',b'text/plain'])
@pytest.mark.parametrize('kind,body', [
    ('containers',b'[{},{},{},{}]'),('depth',b'[[[[0]]]]'),
    ('separators',b'{"a":1,"b":2,"c":3}'),
])
def test_json_geometry_is_refused_before_framework_decode(header,kind,body):
    called=[]
    async def endpoint(*args): called.append(True);await consume(*args)
    guard=bounded(endpoint,max_body=4096)
    guard.max_json_containers=3 if kind=='containers' else 100
    guard.max_json_depth=3 if kind=='depth' else 64
    guard.max_json_separators=3 if kind=='separators' else 100
    events=run(asgi_call(guard,body=body,headers=[] if header is None else [(b'content-type',header)]))
    assert events[0]['status']==413
    assert called==[]


def test_json_string_delimiters_and_chunk_split_escapes_preserve_exact_bytes():
    import json
    from starlette.responses import Response
    raw=json.dumps({'value':'braces{}[],: escaped quote" and backslash\\'}).encode()
    seen=[]
    async def endpoint(scope,receive,send):
        seen.append((await receive())['body'])
        await Response(status_code=200)(scope,receive,send)
    guard=bounded(endpoint,max_body=4096)
    guard.max_json_containers=guard.max_json_depth=guard.max_json_separators=1
    split=raw.index(b'\\"')+1
    chunks=[{'type':'http.request','body':raw[:split],'more_body':True},
            {'type':'http.request','body':raw[split:],'more_body':False}]
    events=run(asgi_call(guard,chunks=chunks,headers=[(b'content-type',b'application/json')]))
    assert events[0]['status']==200
    assert seen==[raw]


@pytest.mark.parametrize('encoding',['utf-16','utf-16-le','utf-16-be','utf-32','utf-32-le','utf-32-be'])
def test_json_alternate_encodings_cannot_bypass_byte_geometry(encoding):
    called=[]
    async def endpoint(*args): called.append(True);await consume(*args)
    raw='{"value":"escaped\\\" quote","rows":[{},{},{}]}'.encode(encoding)
    events=run(asgi_call(bounded(endpoint,max_body=4096),body=raw))
    assert events[0]['status']==415
    assert called==[]


@pytest.mark.parametrize('encoding',['utf-16-le','utf-16-be','utf-32-le','utf-32-be'])
@pytest.mark.parametrize('mime',[b'text/plain',b'application/octet-stream'])
@pytest.mark.parametrize('prefix',['  ',' \t\r\n'*17000],ids=['two-whitespace','multiple-decoder-chunks'])
def test_whitespace_prefixed_alternate_json_cannot_bypass_manual_mime_geometry(encoding,mime,prefix):
    called=[]
    async def endpoint(*args): called.append(True);await consume(*args)
    guard=bounded(endpoint,max_body=2*1024*1024)
    guard.max_json_containers=2
    raw=(prefix+'[{},{},{}]').encode(encoding)
    events=run(asgi_call(guard,body=raw,headers=[(b'content-type',mime)]))
    assert events[0]['status']==415
    assert called==[]


def test_utf8_bom_and_escaped_nul_are_preserved():
    raw=b'\xef\xbb\xbf{"value":"\\u0000"}'
    assert run(asgi_call(bounded(consume,max_body=4096),body=raw))[0]['status']==200


@pytest.mark.parametrize('authorization',[None,b'Bearer invalid-local-token'])
def test_complex_admin_json_is_refused_before_auth_dependency_or_decode(authorization):
    from fastapi import Depends
    from supabase_auth import require_admin
    app=FastAPI()
    @app.post('/api/v1/admin/local-geometry')
    def endpoint(body:dict,admin=Depends(require_admin)):
        pytest.fail('Complex untrusted input reached persistence')
    guard=bounded(app,max_body=4096)
    guard.max_json_containers=3
    headers=[(b'content-type',b'application/json')]
    if authorization:headers.append((b'authorization',authorization))
    events=run(asgi_call(guard,path='/api/v1/admin/local-geometry',body=b'{"rows":[{},{},{}]}',headers=headers))
    assert events[0]['status']==413
