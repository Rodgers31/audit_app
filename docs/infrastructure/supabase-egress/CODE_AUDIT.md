# Supabase egress: application code audit

Date: 2026-10-03. Scope: read-only application inspection; this documentation is the only file written by this workstream. No application imports, database scans, test runs, dependency installation, process changes, configuration changes, or production mutations were performed.

This document complements the dashboard investigation. It identifies code that can transfer unnecessary bytes from PostgreSQL, but **does not assign a percentage of the observed bill to a query without measurements**. File/line references describe the observed working tree, which includes unrelated concurrent development; re-check them before implementation.

## What is established

The user's screenshot shows 6.084 GB / 5 GB uncached egress, a 0.091 GB / 0.5 GB database, zero Storage usage, zero Realtime usage, and one authentication MAU. These are different meters: a small database can be read repeatedly, and anonymous website visitors, backend jobs, development sessions and SQL tools do not need to create authenticated monthly active users.

The coordinating investigation subsequently inspected the live Usage dashboard and reported that all eleven current-cycle daily tooltips round to **Shared Pooler 100.0%**, with only approximately 137 KB Auth plus 280 KB PostgREST across September 28–29. That locates the dominant transfer path at raw PostgreSQL clients using the shared pooler, rather than image/video Storage, Realtime, or browser authentication. It does **not** by itself distinguish Render, GitHub Actions, local development, SQL tooling or other clients. Refer to the companion dashboard evidence for exact date scope and totals.

The live Query Performance inspection also recorded these cumulative query statistics:

| Observed normalized SELECT shape | Calls | Rows returned | Code correspondence |
|---|---:|---:|---|
| Full `source_documents` row where `url = $1` | 109,449 | 109,438 | Several per-record seeding source resolvers, described below |
| Full `Audit` + `Entity`, entity types, severity/created ordering | 334 | 271,542 | Federal findings query, `backend/main.py:4278` |
| Full county `Audit`, 47 entity IDs, entity/created ordering | 336 | 503,328 | County list audit preload, `backend/main.py:2475` |
| Full `BudgetLine`, 47 entity IDs and period IDs | 1,918 | 1,052,350 | County/money-flow budget preloads; normalized shape can have multiple callers |

The coordinating investigation subsequently verified `extensions.pg_stat_statements_info.stats_reset = 2026-04-22 20:29:28.245625+00` through a bounded read-only metadata query. These cumulative counters therefore span a much longer period than the current September 23–October 23 billing cycle. They corroborate actual broad reads, but cannot be equated to the 6.084 GB billing-period total or assigned entirely to the current deployment. Newer narrowed queries also appeared in the dashboard; preserve existing improvements rather than treating historical full-row counters as proof they were never fixed. The observed `pgbouncer.get_auth` counter is internal pooler work and is not evidence of that many users or full data downloads. See [dashboard and database evidence](EVIDENCE.md) for the measurement record; this code-audit workstream itself made no database queries.

A 100% PostgreSQL buffer-cache hit rate means pages were served from database memory instead of disk. It is not the backend response-cache hit rate and does not make result transmission free.

The backend uses synchronous SQLAlchemy/psycopg2. `backend/database.py:12` reads `DATABASE_URL`, otherwise DB_* settings; the component-based default port is 6543. `backend/database.py:46` creates a pooled engine. Consequently a full ORM object query transfers its selected text/JSON columns from Supabase to the backend even if the API subsequently returns a small summary.

The two network legs are distinct:

```text
Supabase PostgreSQL -- query results --> Python backend   [Supabase egress]
Python backend      -- API response --> browser/Vercel    [host egress]
```

Compressing the second leg is useful but does not undo bytes already transferred on the first leg. The existing GZip middleware at `backend/main.py:1294` therefore does not fix raw SQL overfetching. SQL aggregates and narrow projections do.

## Ranked code-level investigation targets

Priority below combines definite overfetch behavior and a verified caller. It is not a measured production bandwidth ranking.

### 0. Repeated source-document lookups have a measured high call count

The observed unaliased `SELECT source_documents.id, ... metadata ... FROM source_documents WHERE source_documents.url = $1` matches SQLAlchemy `select(SourceDocument).where(...)` resolvers. Multiple current paths generate this same normalized shape:

- `backend/seeding/domains/national_budget/writer.py:80`, called per input record by line 211.
- `backend/seeding/domains/economic_indicators/writer.py:68`, called per input record by line 140.
- `backend/seeding/domains/revenue_by_source/writer.py:42`, called per input record by line 106.
- `backend/seeding/fetch_documents.py:66`, called per candidate document.
- National GDP source resolvers at `backend/seeding/domains/national_gdp/__init__.py:54`, 92 and 123.

Important historical distinction: `backend/seeding/domains/counties_budget/writer.py` retains an old single-URL helper at line 48, but its current active batch writer uses `SourceDocument.url.in_(urls)` at line 287. Its implementation already addresses repeated per-record lookup. The legacy audits writer has the same SQL shape at `backend/seeding/domains/audits/writer.py:38`, but the current registered audits domain uses the extraction loader instead. Do not count unused helper definitions as active runtime evidence.

**Proposed fix:** extend the existing county-writer batch/cache pattern to other measured repetitive writers. Within one transaction, load each distinct source once, preserve required metadata updates and safe creation behavior, and pass source identity to per-record work. Where only an ID is needed, select the ID; where metadata must be updated, fetch the required row once. Avoid a process-global stale ORM-instance cache.

**Validation:** compare per-run query deltas and distinct source count. A batch with many records sharing two URLs should require a bounded number of source queries, not one query per record. Test new sources, repeated existing sources, updated provenance and rollback. Normalized query statistics alone cannot identify which resolver generated all 109,449 calls.

### 1. Full federal findings are fetched for the homepage's four-item card

- `backend/main.py:4261` exposes `/api/v1/audits/federal`, cached for one hour.
- `backend/main.py:4278` queries complete `Audit` and `Entity` models, joins them, and calls `.all()` at line 4283. It has no row limit or pagination.
- `backend/models.py:310` defines finding text, recommended action, provenance JSON, management response and other columns on `Audit`; `Entity` includes metadata JSON at line 116. ORM selection includes these columns even when a downstream UI does not use them.
- `backend/main.py:4360` serializes every finding.
- `frontend/app/page.tsx:73` prefetches this endpoint for the homepage, and `frontend/components/dashboard/AuditReportsSection.tsx:99` consumes it. The homepage sorts the full findings array and selects four at lines 127–131.
- `frontend/app/audits/page.tsx:27` also prefetches it.

**Frequency:** each backend cache miss for this endpoint, including process startup warmup; not every browser request while the same process cache remains warm. Different processes do not share the memory cache.

**Proposed fix:** add a bounded homepage summary contract with SQL aggregate totals plus only the displayed top findings. Preserve the full findings experience through a paginated detail route. Select only required fields; retain publication/provenance rules and nullable-amount semantics. The existing `backend/routers/audit_dashboard.py:151` aggregate queries and paginated findings at line 513 are useful examples, but verify their semantics before switching consumers.

**Validation:** unchanged displayed totals and finding ordering; no full findings array on homepage response; inspect SQL selected columns and returned row count; compare cache-miss and pooler-egress deltas over equivalent workloads.

### 2. County list and related summaries hydrate full rows to compute aggregates

- `/api/v1/counties`, `backend/main.py:2367`, has a one-hour cache.
- It loads all county entities at line 2395, relevant budget lines at 2460, all county loans at 2466, and all publishable county audit records at 2475–2482.
- Audits are intentionally not restricted to the selected budget fiscal period. The fix must preserve the latest appropriate audit opinion across reporting periods.
- `frontend/app/page.tsx:85` and `frontend/app/counties/page.tsx:29` prefetch this list; the map and county explorer consume it.
- Similar full-audit reads appear in county peer/accountability calculations (`backend/main.py:5514`) and county summaries (`backend/main.py:5727`).
- `backend/routers/money_flow.py:454` loads full budget lines to compute national totals in Python. In contrast, its all-counties route already uses SQL aggregates at lines 595–606 and 618–628.

**Proposed fix:** move scalar totals/counts into SQL, use narrow projections for necessary provenance fields, and obtain latest-per-entity audit records through an explicit ordered/window query. Do not replace financial aggregation logic casually: aggregate versus component budget rows, unknown versus zero amounts, publishability, fiscal periods and opinion precedence are correctness constraints.

**Validation:** golden response comparison including nulls, actual/modelled/projected basis, chosen fiscal period and latest audit opinion; count returned database rows/bytes in controlled tests.

### 3. Restart amplification makes expensive cached reads recur

- `backend/main.py:1129` startup initializes reference data, starts the production-default auto-seeder and APScheduler, then warms response caches.
- Warmup is enabled by default at line 1216. The list at line 1225 contains 24 endpoints, including federal findings, counties, budget, debt and money flow.
- `_warm_cache` at line 1255 makes self-HTTP requests, concurrency-capped to three. That protects memory but does not eliminate repeated database reads.
- `backend/Dockerfile.prod:98` recycles a web worker every 1,000 requests plus up to 100 jitter requests. Deployments and crashes also reset process-local caches. Actual deployed command, worker count and restart frequency must be verified from hosting logs.
- `backend/bootstrap.py:1248` skips its expensive county loop when 47 counties exist, but national reference seeders still run on startup. It is inaccurate to claim that every restart re-seeds all counties.
- `backend/services/auto_seeder.py:168` boot-seeds five domains and keeps refresh times in memory. The hourly loop at line 235 checks whether each domain is due; it does **not** run every domain hourly. Registry domains are backfilled with a boot timestamp and generally run weekly.

**Proposed fix:** first measure restarts and cold cache misses. Then consider narrower/lazy warmup, a longer safe worker lifetime after memory profiling, and one explicit owner for periodic ingestion. Keep startup work lightweight. Do not remove recycling, seeding or freshness guarantees blindly and do not stop existing processes as part of this audit.

### 4. Existing caching is real, but process-local and not stampede-protected

- `backend/cache/redis_cache.py:30–92` implements memory fallback with TTL when Redis is absent. **No Redis does not mean no cache.** A paid Redis service is not the first remedy.
- `backend/main.py:1585` uses this cache for many public endpoints; DI objects are omitted from its keys.
- `backend/cache/redis_cache.py:211` and the main-module decorator both call the expensive function after a miss without per-key in-flight request coalescing. Concurrent cold requests can duplicate work before the first result is saved.
- If a Redis client was successfully initialized but subsequently errors, its `get`/`set` methods log the exception and do not switch that request to memory caching. This matters only if that deployed failure mode exists.
- Normal TTLs are often 30–60 minutes; error results may intentionally get only a 30-second TTL. Empty-but-readable results retain ordinary TTLs.
- `frontend/lib/react-query/getQueryClient.ts:43` deliberately creates a fresh server client per render and retains a browser singleton. Browser `staleTime` is not a server-wide shared cache. Most public hooks already use multi-minute stale times with window-focus/reconnect refetch disabled.
- SSR uses Axios. Do not assume it participates in Next.js fetch caching merely because the component is server-rendered. The homepage declares ISR; actual rendered route/cache behavior should be checked in a build/deployment inspection.

**Proposed fix:** retain working memory caching, add per-key single-flight around expensive public cache fills, instrument hits/misses, and ensure keys distinguish meaningful filters. Cache only public responses across users. Explicitly use private/no-store for admin and account data; do not cache authenticated responses globally to save bandwidth.

**Validation:** two simultaneous cold requests produce one database workload; correct separation by year/filter; errors recover promptly; private data cannot leak across users.

### 5. Audit ingestion rereads unchanged extraction payloads and existing findings

- `.github/workflows/seed.yml:7` schedules nightly refresh and a weekly additional deep run using a remote `DATABASE_URL` secret at line 40.
- `backend/seeding/domains/audits/__init__.py:116–137` processes `known + fresh` document candidates, not only new ones.
- `backend/seeding/extractors/oag_blue_book.py:453–475` correctly skips extraction when the document hash is unchanged.
- Even after that skip, `backend/seeding/domains/audits/__init__.py:164` invokes the loader.
- `backend/seeding/domains/audits/loader.py:124–134` loads every `Extraction` for the document, including `extracted_json` containing full finding text, then line 188 loads a complete existing `Audit` per extraction.
- The loader compares values at lines 224–241, so unchanged data can incur reads without producing useful changes.
- `backfill_publishable_audits` performs server-side updates/counts. Those writes have operational cost but should not be mislabelled as downloading all rows; its statements use `synchronize_session=False` and do not return full records.

**Proposed fix:** record separate extraction and loader version/hash completion markers. Skip a completed unchanged load only when document hash, parser version, loader version and completeness checks match. Otherwise fetch only IDs, comparison hashes and required fields in batches. Preserve recovery from partial loads and deliberate reparsing after algorithm changes.

**Validation:** unchanged second run returns minimal metadata and no full extraction payloads; changed document, changed parser/loader, interrupted run and missing audit rows all correctly trigger processing. Compare real scheduled-job query-stat deltas before/after.

### 6. Uncached admin statistics load verbose job records

- `backend/routers/admin.py:233–238` loads all matching `IngestionJob` records and computes counts/sums in Python.
- The model includes errors and metadata, neither required for simple totals.
- The admin overview requests a seven-day summary at `frontend/app/admin/page.tsx:118`; its `staleTime` is 30 seconds. **Stale time is not a 30-second polling interval.** It fetches on normal query activation/refetch behavior.
- The overview's failed-job list really polls every 60 seconds at line 161, but is limited to five jobs. The list still includes each job's full errors and metadata (`backend/routers/admin.py:154–155`).

**Proposed fix:** compute summary counts/sums/grouping in PostgreSQL. Give list responses bounded summaries and fetch large errors/metadata only in the detail view. Use a short private cache only if safe and useful; reducing selected data is the primary fix.

**Validation:** aggregate results equal current output; job list page size remains enforced; detail information remains available; no cross-admin data caching mistake.

### 7. Freshness badges can retrieve all source-document metadata

- `backend/routers/data_freshness.py:282` has no backend cache decorator.
- `_source_publication_date` at line 258 queries all matching document IDs and calls `resolve_data_vintage`.
- `backend/provenance.py:86` loads full `SourceDocument` models even though vintage needs only publication-date metadata and fetch date.
- `frontend/components/DataFreshnessBadge.tsx:50` requests the endpoint with a 30-minute browser stale time. This reduces calls per browser, but does not share a cache among browsers.

**Proposed fix:** select only the needed timestamp/JSON key fields and share a short public response cache. Preserve the distinction between source publication date, retrieval date and latest ingestion date.

**Validation:** same source dates, coverage and null behavior; no full source-document rows returned just to compute freshness.

### 8. An apparent paginated endpoint paginates only after downloading all findings

- `backend/main.py:4961` defines `/counties/{county_id}/audits/list` without a cache decorator.
- It loads all matching complete `Audit` rows at line 5004, filters status in Python and slices at 5022–5025.
- If county-name resolution succeeds but no database entity matches, the current code omits the entity filter and can query all publishable audits instead of returning empty/not-found.
- `frontend/lib/api/audits.ts:84`, its React Query hook and `frontend/components/AuditListWithSources.tsx:21` form a caller chain. However, this audit did not find the component mounted by a current page; actual production traffic to this endpoint remains unverified.

**Proposed fix:** fail closed when no entity matches; push equivalent status/year/severity filters, count and pagination into SQL. Preserve provenance-derived status semantics until an explicit migration/normalization decision is made. Join only required source/period fields for the selected page.

**Validation:** requesting ten rows transfers no more than the intended page and small aggregates; unknown/missing entities cannot expose a full-table result; filters and total count match expected behavior.

## Development, tests, scripts and other clients

Shared Pooler data can be downloaded by more than the deployed backend:

- Local application startup loads `.env` through `backend/database.py:9`. Whether any current local environment points to production was not disclosed or changed by this workstream.
- `backend/verify_seeded_data.py:19–43` loads whole ingestion-job, source-document, fiscal-period and budget-line tables. It has no proven scheduled invocation in this audit.
- `scripts/supabase_migrate/01_dump.sh:51` performs a full data dump. A manually invoked dump transfers database contents; no recurring dump workflow was found in the inspected workflow set.
- Standard CI backend tests use a local PostgreSQL service (`.github/workflows/ci.yml:79`), and common unit-test fixtures use SQLite with DB dependency overrides (`backend/conftest.py:159–235`). Do not attribute their normal reads to Supabase without evidence.
- The HTTP network guard at `backend/conftest.py:96` blocks HTTP transports, not arbitrary psycopg2 connections. New diagnostic scripts and tests that bypass fixtures should have explicit local-database guards.
- Playwright can reuse an existing local frontend server (`frontend/playwright.config.ts:26`) and tests all three browser engines. Its API destination depends on the server configuration. This is a possible source of repeated real API reads, not proof of current production use.
- CI migrations use a remote pooler secret on qualifying main/develop pushes (`.github/workflows/ci.yml:256–303`); the migration path is distinct from ordinary test traffic.

Recommendation: make future work use local fixtures/snapshots for repeated exploration, bounded projections for diagnostics and explicit `application_name` values for API, seeder, worker, migration and local sessions. Never print connection credentials. Do not change any existing agent's environment or stop its process without task-specific authorization.

## Lower-priority and excluded explanations

- Authentication: `_fetch_roles` performs a narrow profile REST request per authenticated backend request (`backend/supabase_auth.py:191`, `backend/supabase_admin.py:151`). Middleware validates logged-in sessions and role reads; it already skips Supabase entirely for anonymous public-route requests (`frontend/lib/supabase/middleware.ts:23–38`). The observed Auth/PostgREST totals are tiny relative to pooler egress, so authentication caching is not the first savings target.
- Health probes: the mounted main-module `/health/live` and `/health/ready` paths inspect in-memory readiness, not a full dataset. Do not assume every health check downloads records because another unmounted health module contains SQL.
- Government PDF downloads: remote government-to-ETL downloads and GitHub PDF-cache churn are not themselves Supabase database egress. Database reads of stored extraction JSON are.
- Storage images/video, Realtime and Edge Functions are not supported as causes by the observed zero usage and the dominant Shared Pooler breakdown.
- Adding indexes improves database work, but an index alone does not reduce the number of selected bytes in a full-row result.
- Moving from pooled to direct PostgreSQL access would not remove outbound-data cost. It would only change the connection path.

## Measurements needed before assigning blame

1. Correlate the daily Shared Pooler series with deployments/restarts, scheduled ingestion and periods of intensive development.
2. Inspect existing `pg_stat_statements`/Query Performance counters without resetting them. Capture snapshot time and stats-reset boundary. Calls and rows are useful but are not byte meters; cumulative rows can include writes.
3. Group SELECT patterns by model/projection and estimate output width from small representative samples or existing metadata. Do not export the whole database to diagnose bandwidth.
4. Capture counter deltas across a bounded normal interval and associate normalized query patterns with the code paths above. A shared query can still have multiple clients.
5. Add future per-client `application_name`, endpoint cache-hit/miss metrics, and bounded result-size telemetry without recording private row contents.
6. After each isolated fix, compare daily pooler egress at similar workload, cache hit rate, restart frequency and correctness tests. Do not claim savings from reduced API JSON alone.

## Low-egress requirements for the future social worker

The existing PostgreSQL remains suitable for the small social publishing domain. The design must avoid turning a sparse queue into constant large reads:

- Claim a bounded number of due **IDs and lease fields**, with `SKIP LOCKED` and a partial due-work index. Load the immutable payload only after a successful claim. Never scan/select every draft body or media manifest every five seconds.
- An empty poll returns no payload rows. Do not perform full account, credential, control, draft and history queries each tick.
- Cache non-sensitive capabilities and account metadata between operations. Read encrypted credentials only when needed; rotate/refresh under a versioned lease.
- Recheck the authoritative global/account pause and approval state in the short dispatch-permit transaction. Caching must not weaken the kill switch.
- Heartbeat updates should return only minimal acknowledgement; do not `RETURNING *` a large JSON record.
- Combine small maintenance scans and back off while idle. A 60-second idle poll changes the Publish Now latency promise; document that tradeoff rather than simultaneously promising sub-ten-second dispatch. Retain short polling only where needed and measure its actual wire cost.
- Five-second polling creates 535,680 scans in a 31-day month; 60-second polling creates 44,640. These are scan counts, **not** a measured byte estimate. Actual protocol/result bytes must be profiled.
- Keep polling queries bounded, avoid repeatedly reconnecting, and use a small worker connection pool.
- Admin queue pages return summaries only, are paginated, and poll actively publishing records at a bounded cadence. Stop active polling when the view is hidden; static history does not need continuous refresh.
- Generate source events from changed IDs/fingerprints with a persisted cursor. Do not reread every audit/extraction on each social-worker tick.
- Media bytes belong in object storage, not PostgreSQL/base64 columns. If Supabase Storage is chosen later, each preview and provider download can add storage egress; treat that as a separate budget from today's database-result problem.
- Load approved media once per operation as needed; reuse immutable assets and derivatives instead of creating five originals. Metadata may be repeated in immutable approval snapshots, but image/video bytes must not be.

## Implementation boundary

All proposed fixes are pending separate implementation. This audit has not changed cache behavior, queries, ETL cadence, hosting, credentials, billing or existing workstreams. Prioritize measured raw-SQL overfetch and restart amplification before considering a database migration or a paid cache.
