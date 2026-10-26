"""Owned low-volume interleavings for slow body and physical scan ownership."""
import asyncio
from threading import Event, Timer, get_ident
from time import monotonic

import pytest

from middleware.request_resources import RequestResourceMiddleware
from test_request_resource_bounds import asgi_call, consume


@pytest.mark.parametrize('method,headers', [
    ('POST',[(b'content-length',b'2')]),
    ('GET',[(b'content-length',b'2')]),
    ('GET',[(b'transfer-encoding',b'chunked')]),
])
def test_slow_body_connections_leave_ordinary_read_capacity(method,headers):
    async def exercise():
        release=asyncio.Event()
        guard=RequestResourceMiddleware(consume,body_timeout=1)
        async def slow():
            sent=False
            output=[]
            async def receive():
                nonlocal sent
                if not sent:
                    sent=True
                    return {'type':'http.request','body':b'x','more_body':True}
                await release.wait()
                return {'type':'http.request','body':b'x','more_body':False}
            async def send(value):output.append(value)
            await guard({'type':'http','method':method,'path':'/slow','headers':headers,
                'query_string':b'','client':('192.0.2.1',1)},receive,send)
            return output
        tasks=[asyncio.create_task(slow()) for _ in range(8)]
        try:
            await asyncio.sleep(0)
            assert (await asgi_call(guard,method='GET',path='/health/live'))[0]['status']==200
            assert (await asgi_call(guard,method='GET',path='/ordinary'))[0]['status']==200
            assert guard.body_inflight<=4
        finally:
            release.set()
            await asyncio.gather(*tasks)
        assert guard.inflight==guard.body_inflight==guard.buffered==0
    asyncio.run(exercise())


def test_trickled_body_still_has_an_absolute_deadline():
    async def exercise():
        called=[]
        async def endpoint(*args):called.append(True);await consume(*args)
        guard=RequestResourceMiddleware(endpoint,body_timeout=.03)
        async def receive():
            await asyncio.sleep(.005)
            return {'type':'http.request','body':b'x','more_body':True}
        output=[]
        async def send(value):output.append(value)
        started=monotonic()
        await guard({'type':'http','method':'POST','path':'/x','headers':[],
            'query_string':b'','client':('192.0.2.1',1)},receive,send)
        assert output[0]['status']==408
        assert monotonic()-started<.2
        assert called==[]
    asyncio.run(exercise())


async def wait_thread_event(event):
    async with asyncio.timeout(.3):
        while not event.is_set():
            await asyncio.sleep(.001)


def test_held_large_scan_does_not_block_get_or_health_event_loop():
    async def exercise():
        guard=RequestResourceMiddleware(consume)
        original=guard.check_json_budget
        entered,release,finished=Event(),Event(),Event()
        def held(raw,scope):
            if raw:
                entered.set()
                release.wait(1)
            try:return original(raw,scope)
            finally:
                if raw:finished.set()
        guard.check_json_budget=held
        # The watchdog forces the old synchronous interleaving to complete,
        # rather than hanging a test on the same loop it is demonstrating.
        watchdog=Timer(.5,release.set);watchdog.start()
        request=asyncio.create_task(asgi_call(guard,body=b' '*65536+b'{}'))
        started=monotonic()
        try:
            await asyncio.sleep(0)
            await wait_thread_event(entered)
            assert (await asgi_call(guard,method='GET',path='/ordinary'))[0]['status']==200
            assert (await asgi_call(guard,method='GET',path='/health/live'))[0]['status']==200
            assert not finished.is_set(), 'The loop could run reads only after the held scan ended'
            assert monotonic()-started<.3
        finally:
            release.set();watchdog.cancel();watchdog.join()
            await request
            if hasattr(guard,'aclose'):await guard.aclose()
    asyncio.run(exercise())


def test_repeated_cancelled_scans_keep_physical_slot_and_bytes_until_completion():
    async def exercise():
        guard=RequestResourceMiddleware(consume)
        original=guard.check_json_budget
        phase={}
        threads=[]
        def held(raw,scope):
            if raw:
                threads.append(get_ident())
                phase['entered'].set()
                phase['release'].wait(1)
            try:return original(raw,scope)
            finally:
                if raw:phase['finished'].set()
        guard.check_json_budget=held
        raw=b' '*65536+b'{}'
        try:
            for turn in range(3):
                phase.update(entered=Event(),release=Event(),finished=Event())
                watchdog=Timer(.5,phase['release'].set);watchdog.start()
                task=asyncio.create_task(asgi_call(guard,body=raw))
                try:
                    await asyncio.sleep(0)
                    await wait_thread_event(phase['entered'])
                    assert not phase['finished'].is_set(), 'The scan blocked cancellation on the loop'
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):await task
                    assert guard.inflight==guard.body_inflight==guard.scanning==1
                    assert guard.buffered==len(raw)
                    for _ in range(3):
                        refused=await asgi_call(guard,body=raw)
                        assert refused[0]['status']==503
                        assert guard.inflight==guard.body_inflight==guard.scanning==1
                        assert guard.buffered==len(raw)
                    assert len(threads)==turn+1, 'A refused request queued another physical scan'
                    assert (await asgi_call(guard,method='GET',path='/ordinary'))[0]['status']==200
                finally:
                    phase['release'].set();watchdog.cancel();watchdog.join()
                    await asyncio.gather(task,return_exceptions=True)
                async with asyncio.timeout(.3):
                    while guard.inflight or guard.scanning:
                        await asyncio.sleep(.001)
                assert phase['finished'].is_set()
                assert guard.buffered==guard.body_inflight==0
            assert len(set(threads))==1, 'Scanner cancellation created additional workers'
        finally:
            phase.get('release',Event()).set()
            if hasattr(guard,'aclose'):await guard.aclose()
    asyncio.run(exercise())


def test_scan_timeout_retains_ownership_until_the_worker_finishes():
    async def exercise():
        guard=RequestResourceMiddleware(consume,request_timeout=.01)
        original=guard.check_json_budget
        entered,release=Event(),Event()
        def held(raw,scope):
            if raw:
                entered.set()
                release.wait(1)
            return original(raw,scope)
        guard.check_json_budget=held
        watchdog=Timer(.5,release.set);watchdog.start()
        raw=b' '*65536+b'{}'
        try:
            response=await asgi_call(guard,body=raw)
            assert entered.is_set()
            assert response[0]['status']==504
            assert guard.inflight==guard.body_inflight==guard.scanning==1
            assert guard.buffered==len(raw)
            assert (await asgi_call(guard,method='GET',path='/ordinary'))[0]['status']==200
        finally:
            release.set();watchdog.cancel();watchdog.join()
            await guard.aclose()
        assert guard.inflight==guard.body_inflight==guard.scanning==guard.buffered==0
    asyncio.run(exercise())


def test_shutdown_waits_for_physical_scan_without_blocking_the_loop():
    async def exercise():
        guard=RequestResourceMiddleware(consume)
        original=guard.check_json_budget
        entered,release=Event(),Event()
        def held(raw,scope):
            if raw:
                entered.set()
                release.wait(1)
            return original(raw,scope)
        guard.check_json_budget=held
        watchdog=Timer(.5,release.set);watchdog.start()
        request=asyncio.create_task(asgi_call(guard,body=b' '*65536+b'{}'))
        closing=None
        try:
            await wait_thread_event(entered)
            closing=asyncio.create_task(guard.aclose())
            await asyncio.sleep(0)
            assert not closing.done()
            assert guard.scanning==guard.inflight==1
            assert (await asgi_call(guard,method='GET',path='/health/live'))[0]['status']==200
        finally:
            release.set();watchdog.cancel();watchdog.join()
            await request
            if closing is not None:await closing
            else:await guard.aclose()
        assert guard.scanning==guard.inflight==guard.buffered==0
        assert guard._scan_executor is None
    asyncio.run(exercise())


def test_failed_large_scan_refuses_instead_of_reaching_the_handler():
    async def exercise():
        called=[]
        async def endpoint(*args):called.append(True);await consume(*args)
        guard=RequestResourceMiddleware(endpoint)
        def broken(raw,scope):raise ValueError('inert scanner failure')
        guard.check_json_budget=broken
        try:
            response=await asgi_call(guard,body=b' '*65536+b'{}')
            assert response[0]['status']==500
            assert b'JSON_SCAN_FAILED' in response[1]['body']
            assert called==[]
        finally:
            await guard.aclose()
        assert guard.scanning==guard.inflight==guard.buffered==0
    asyncio.run(exercise())
