# Cache and runtime verification — issue #355

Base: `37c6c37c565b3190ae0f72fb5fa895daf68abe24`. Worktree: `codex/cache-runtime`. Tests used the local SQLite test database explicitly; no production database, environment file, or service was read.

## Changes

- Cache public audit findings for 300 seconds and data freshness for 120 seconds. Both routes retain their response models and use FastAPI's sync thread pool for their synchronous SQLAlchemy work. Pipeline health (#290) uses a 30 second shared response cache.
- The existing `cache.redis_cache` decorator now hashes complete bound arguments, including defaults, filters, pages and page limits, while excluding request scoped dependencies. It uses fixed 64 stripe locks per event loop or sync wrapper so matching cold requests share one load. The generation marker participates in the key, making a pre-invalidation in-flight fill unreachable afterward. Cancelled or raised loads do not write a successful cache entry.
- Each `RedisCache` instance caps its memory fallback at 1,024 entries, 16 MiB of serialized JSON payloads, and 2 MiB per entry. The process has multiple instances, so 16 MiB is not a total process-memory limit. Oversized entries are served without storage. Existing build namespaces, TTLs, and signed invalidation remain in force.
- `/health/detailed` reports process-local cache hits, misses, expirations, evictions, lock contention, rejected oversized entries, memory entry count and JSON payload bytes for the shared cache instance. Request completion logs use JSON with method, route template, status and duration. Fast 2xx requests log at DEBUG; slow responses and errors log at WARNING/ERROR. Raw URLs, query values, credentials and evidence text are omitted. `httpx` URL logging at INFO is disabled.
- The Render service's `backend/Dockerfile` no longer starts Uvicorn with `--reload`. This file is also used by the repository's default Docker Compose service, which therefore no longer reloads automatically. The separate image-publishing workflow builds `backend/Dockerfile.prod`, whose Gunicorn command already omits reload; that alternate image is unchanged.

### Deployment-path evidence

The coordinator re-read the live Render **Settings** page on 2026-09-28 during
Copilot review. The service builds branch `main`, with root directory `backend`,
Dockerfile path `./Dockerfile`, Docker build context `.`, and an empty Docker
Command override. These settings select `backend/Dockerfile`, not the alternate
image from `.github/workflows/docker-build-deploy.yml:271`. That workflow does
build `backend/Dockerfile.prod`, and `docker-compose.yml:36` uses `Dockerfile`.
Both repository references are correct; they do not establish which image the
Render service uses. No Render setting or deployment was changed during this
read-only verification.

## Behavioral receipts

- Before the cache change: `pytest backend/tests/test_public_response_cache.py -q` → **2 failed, 2 passed**. The old decorator exposed filter values in keys and 12 identical cold calls ran 12 loads.
- After the change, from `backend/`, with `DATABASE_URL=sqlite:////tmp/cache-runtime-test.sqlite`: the focused cache, audit, freshness, serialization, invalidation, namespace and recovery test files → **101 passed, 4 warnings**. An audit subset with absent, malformed and extraction metadata plus zero/withheld model cases → **35 passed**.
- The route cache sweep exercises seeded and empty database responses; its freshness fixture now supplies an accepted Treasury fact with a publication date, so the populated branch is actually tested. Cached findings preserve source URLs and byte-identical response bodies for absent/malformed/normal document metadata; invalidation exposes changed data. Freshness retains `unknown` until invalidated. Pipeline-health makes five external checks for two identical calls using a local fake, versus ten without caching; its JSON body matches `JSONResponse` serialization.
- Tests force expiry, a returned `unavailable` body, a raised load, cancellation, concurrent sync and async calls, oversize rejection, byte-budget eviction and an invalidation during a paused load. No network service is contacted in these tests.

Run from `backend/`:

```sh
env DATABASE_URL=sqlite:////tmp/cache-runtime-test.sqlite /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest tests/test_public_response_cache.py tests/test_audit_dashboard.py tests/test_data_freshness.py tests/test_model_responses_are_cacheable.py tests/test_cache_invalidation_endpoint.py tests/test_cache_key_is_build_scoped.py tests/test_health_detailed_reports_cache.py tests/test_cache_namespace_pinning_warning.py tests/test_failures_are_not_cached_long.py -q
```

## Limits and follow-up

- Cache payload bytes are serialized JSON size in one process, not database wire bytes or Supabase billable egress. The counters reset on process restart, are not per route, and the detailed health response does not include other `RedisCache` instances. Request INFO logs intentionally do not provide a complete request count. Compare Supabase's own egress metrics after deployment for the actual effect.
- Production has no Redis. The marker is per container; multiple containers would need a shared invalidation mechanism. Redis storage is TTL bounded but does not have the in-process byte budget. Oversized responses are uncached, so simultaneous callers arriving after the first oversized load may each query; this is visible in the `oversized` counter.
- The preexisting pipeline-health handler still does synchronous DB work within an async function on a cache miss. Its query/runtime migration is outside this scoped change; the 30 second cache reduces frequency but does not remove that miss-path blocking. Follow-up: [#363](https://github.com/Rodgers31/audit_app/issues/363).
- The local venv's FastAPI lacks `fastapi.routing.iter_route_contexts`, so the unrelated `test_system_routes_are_read_only.py` failed at import when included in an exploratory run. The focused cache suite above passes. The coordinator should verify this test in CI's separately installed environment.
- Router query bodies in `audit_dashboard.py` and `data_freshness.py`, and county/federal sections of `main.py`, are being changed in other sessions. This commit only changes decorators/route signatures and pipeline/cache/observability sections in those shared files. Integration should preserve both sets of edits.
