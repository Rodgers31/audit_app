"""A failed cache initialization cannot open a second unbounded retention path."""
import asyncio


def test_hard_cache_failure_keeps_public_reads_without_retaining_query_keys(monkeypatch):
    import main
    monkeypatch.setattr(main,'redis_cache',None)
    calls = []
    @main.cached('owned-hard-cache-failure')
    async def endpoint(value):
        calls.append(value)
        return {'value':value}
    async def exercise():
        for value in ('one','two','three','one'):
            assert await endpoint(value=value) == {'value':value}
    asyncio.run(exercise())
    assert calls == ['one','two','three','one']
    assert main._all_mem_caches[-1] == {}
