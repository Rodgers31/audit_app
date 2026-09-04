"""Every response cache must be cleared between tests.

``main.clear_all_caches()`` runs before every test (conftest ``_setup_tables``).
It used to enumerate the RedisCache singletons *by name* — ``main.redis_cache``
and ``cache.redis_cache.cache`` — and there is a third one it never knew about:
``routers/money_flow.py`` builds its own ``RedisCache()`` at import.  With no
Redis configured every instance falls back to a private ``_memory_cache``, so
money-flow responses stayed cached for their full 1800 s TTL — far longer than
a whole suite run.

The effect is order-dependence: a test's result depends on whether some
*earlier* test happened to warm that endpoint, so the same test can pass alone
and fail in a full run purely because of collection order.

``main._peers_cache`` (TTL 12 h) had the same problem.

These tests fail if either cache stops being cleared.
"""

import time

import main
from cache.redis_cache import RedisCache


def test_every_redis_cache_instance_is_reachable_from_clear_all_caches():
    """The registry must cover every instance, not a hand-maintained list."""
    from routers.money_flow import _redis_cache as money_flow_cache

    reachable = {id(rc) for rc in main._redis_cache_instances()}
    assert id(money_flow_cache) in reachable, (
        "routers/money_flow.py's RedisCache is not reachable from "
        "clear_all_caches() — its 1800 s entries will survive between tests"
    )
    # Not just money_flow: assert the registry is the source of truth.
    assert reachable >= {id(rc) for rc in RedisCache._instances}


def test_money_flow_cache_does_not_survive_clear_all_caches():
    from routers.money_flow import _redis_cache as money_flow_cache

    money_flow_cache.set("probe:money-flow", {"stale": True}, ttl=1800)
    assert money_flow_cache.get("probe:money-flow") is not None, (
        "probe did not cache — this test can no longer detect the leak"
    )

    main.clear_all_caches()

    assert money_flow_cache.get("probe:money-flow") is None, (
        "money-flow's cache survived clear_all_caches()"
    )


def test_peers_cache_does_not_survive_clear_all_caches():
    main._peers_cache["ts"] = time.time()
    main._peers_cache["data"] = [{"stale": True}]

    main.clear_all_caches()

    assert main._peers_cache["data"] is None, (
        "main._peers_cache survived clear_all_caches() — with a 12 h TTL one "
        "warm-up freezes peers for the entire run"
    )
