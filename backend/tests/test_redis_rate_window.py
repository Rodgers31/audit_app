"""A deterministic Redis contract double, never a live limiter dependency."""
import asyncio

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from middleware import security


class CounterStore:
    def __init__(self, clock):
        self.clock = clock
        self.values = {}
        self.expires = {}

    def increment(self, key):
        if self.expires.get(key, float('inf')) <= self.clock[0]:
            self.values.pop(key, None)
            self.expires.pop(key, None)
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def pipeline(self):
        store = self

        class Pipeline:
            def __init__(self):
                self.commands = []

            def incr(self, key):
                self.commands.append(('incr', key))

            def expire(self, key, period):
                self.commands.append(('expire', key, period))

            def set(self, key, value, *, nx, ex):
                self.commands.append(('set', key, value, nx, ex))

            async def execute(self):
                results = []
                for operation, key, *args in self.commands:
                    if store.expires.get(key, float('inf')) <= store.clock[0]:
                        store.values.pop(key, None)
                        store.expires.pop(key, None)
                    if operation == 'incr':
                        results.append(store.increment(key))
                    elif operation == 'expire':
                        store.expires[key] = store.clock[0] + args[0]
                        results.append(True)
                    elif operation == 'set':
                        value, nx, ex = args
                        if nx and key in store.values:
                            results.append(None)
                        else:
                            store.values[key] = int(value)
                            store.expires[key] = store.clock[0] + ex
                            results.append(True)
                    else:
                        raise ValueError('Unknown Redis fixture command')
                return results

        return Pipeline()


def test_steady_requests_below_limit_recover_without_a_quiet_period(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(security.time, 'monotonic', lambda: clock[0])
    limiter = security.RedisRateLimitMiddleware(FastAPI(), calls=2, period=60)
    store = CounterStore(clock)
    limiter.redis_client, limiter.use_redis = store, True
    request = Request({'type': 'http', 'method': 'GET', 'path': '/fixture',
                       'headers': [], 'client': ('192.0.2.1', 1)})

    async def accepted(request):
        return JSONResponse({'ok': True})

    async def exercise():
        outcomes = []
        for instant in (0, 31, 62, 93):
            clock[0] = instant
            outcomes.append((await limiter.dispatch(request, accepted)).status_code)
        assert outcomes == [200, 200, 200, 200]

    asyncio.run(exercise())
