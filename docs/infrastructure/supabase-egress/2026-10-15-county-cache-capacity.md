# County response cache capacity

The 15 October production response contained all 47 counties and serialized to
2,362,271 bytes in `RedisCache.set`. The prior 2 MiB entry ceiling refused it,
incremented `oversized`, and left subsequent reads uncached. Current Render
startup logs and runtime configuration confirm the in-memory fallback is used.
Bounded public reads took 4.83 and 6.68 seconds; the gzip read transferred
165,704 bytes. These samples establish slow reads, not a latency distribution.

Raise the default individual entry ceiling to 3 MiB through one shared constant
used by normal construction and fallback defaults. Retain the existing 16 MiB
**serialized payload budget per cache instance**, entry count, eviction, TTL,
generation fencing, filters and Redis behavior. This budget is not a process
RSS measurement; multiple existing cache instances retain separate budgets.
No Redis service, hosting change, paid resource or new dependency is added.
The full financial/evidence payload is retained rather than trimming provenance
to make it fit. Responses above 3 MiB still remain uncached.

Six regressions failed on the original cache source: normal and bare instances
under all three actual decorators (`main.cached`, `money_flow._cached`, and
`cache.redis_cache.cached`) each executed the expensive handler twice. This
fix permits a second read to use the exact cached response. Existing TTL,
transient-failure, filter, invalidation, serialization and budget controls remain
in the affected cohort. Parallel helper coverage does not establish coalescing
in the legacy main/money-flow decorators, which do not supply that behavior.

The shared `RedisCache.set` guard covers all three existing singleton instances
and their normal writes. Decorators' independent no-cache-object dictionaries
are unaffected; this repair does not claim to bound those separate paths.

Before production acceptance, compare all 47 response records before/after,
measure bounded cold/repeat reads, observe cache counters where available and
verify health/readiness. Roll back to accepted `01d99524e64c430f26d84af66b1229123b33fe20`
through the existing Render manual deployment if equivalence, health or memory
headroom fails. Build-scoped cache keys isolate the rollback. Browser LCP and
layout shift need separate measurements: the seven-day county LCP10.92s(5
samples), county CLS0.38(6), budget CLS0.46(3) and detail CLS0.46(1) are not
certified fixed by a local cache test or this entry-limit adjustment.
