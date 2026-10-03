# Scoped egress reduction: local receipts

This first implementation for issue #481 changes ingestion statistics and source-document resolution in the national-budget and revenue-by-source writers. The baseline is commit `9000c25`, measured on 2026-10-03 with isolated PostgreSQL fixtures. No production query, dashboard inspection, deployment, ingestion schedule change, or live publication was performed.

## Measured result

The fixture contains 100 ingestion jobs: 80 within the 30-day window, two domains, and all five statuses. Each job has approximately 64 KiB of diagnostic/metadata content. Each writer receives 20 records referencing two existing sources, each with approximately 64 KiB of metadata. These deliberately large synthetic fields exercise overfetch; they are not estimates of production averages.

| Measured selection | Before queries / returned rows | After queries / returned rows | Before selected-value bytes | After selected-value bytes |
|---|---:|---:|---:|---:|
| Ingestion statistics, 30 days | 1 / 80 | 1 / 10 | 5,253,971 | 356 |
| National-budget source documents | 20 / 20 | 2 / 2 | 1,314,200 | 2 |
| Revenue source documents | 20 / 20 | 2 / 2 | 1,314,274 | 46 |

These are **UTF-8 decoded selected-value estimates**, obtained from actual DBAPI results. The probe sums compact JSON representations of decoded dictionaries/lists and string representations of other values. It excludes PostgreSQL framing, column descriptors, protocol control messages, TLS, connection setup, compression, pooler accounting, and provider billing conventions. It is neither wire traffic nor a Supabase usage meter. Exact values can vary with generated IDs and timestamps. No production savings percentage or free-tier acceptance is inferred.

Statistics now select `domain`, `status`, `COUNT(id)`, and three `SUM` counters, grouped by domain and status. This transfers one row per present group rather than full ingestion jobs. The response remains the same, including the existing semantics for `days=None`, `days=0`, empty results, and negative-day filters. The local 30-day response still contains exactly 80 jobs and two domains.

Each writer lazily resolves a source once per distinct URL in that invocation. The national-budget writer selects only its identity; the revenue writer selects identity, publisher, and title. There is no process-global cache. Existing metadata remains untouched; status/last-seen updates and ordered publisher/title declarations still run for each record. New sources are cached only after their creation flush succeeds. Transaction commit and rollback remain the caller's responsibility.

Duplicate source URLs still cause `scalar_one_or_none()` to reject ambiguous provenance. This change neither adds a uniqueness constraint nor resolves the existing cross-process creation race. It must not be described as a general source deduplicator.

Logs contain static event names and bounded counts, duration, source ID, changed-field name, or exception class. Relabel logs no longer contain old/new labels, and persistence warnings no longer print exception/provider bodies. Returned `PersistenceStats.errors` retain their existing contract; that contract is not a new logging channel. Summary events say `persistence_prepared` because the caller may subsequently roll back.

## Regression evidence

New query-count regressions failed before implementation: full statistics returned 80/100 rows, and each writer issued 20 source selections rather than two. Independent byte guards also failed before implementation: 5,253,971 bytes for statistics and 131,402/131,404 bytes for two source reads. The original revenue relabel log exposed the private fixture labels. These failures were executed against the baseline, not inferred from source strings.

The local PostgreSQL lane verifies exact aggregate output; existing/new source reads; metadata preservation; ordered declared/undeclared labels; new-source rollback and subsequent re-resolution; rollback after an actual injected database flush failure; explicit withdrawal versus absent amounts; retained publication/provenance fields; national-budget measure replacement; refusal of duplicate URLs; and safe relabel/error logs. Four existing revenue publisher/provenance golden tests also run on this isolated PostgreSQL fixture. Financial/rollback cases were separately executed successfully on the baseline before asserting the optimization.

The final scoped run completed with **35 passed in 3.98 seconds**, using the existing backend Python 3.9 environment. Four existing pytest/SQLAlchemy configuration/deprecation warnings were emitted. The standalone benchmark also completed successfully, including its two concurrent fake operations.

The benchmark and test harness reject absent, asynchronous, non-PostgreSQL, non-loopback, wrong-port, and unassigned-database URLs before connecting. Tests create random schemas in the dedicated local fixture database and remove only those schemas. They do not import `backend.main`, start application lifespan/ETL, load configured environment files, or install packages.

## Repeat the measurement

Use an existing Python environment containing the repository's backend dependencies. Supply the **dedicated disposable local** database URL explicitly; this harness currently permits only loopback port `62124`, database `social_worker_test`, and synchronous `psycopg2`. It is deliberately unsuitable for production targets.

```sh
export EGRESS_TEST_DATABASE_URL='postgresql+psycopg2://LOCAL_USER:LOCAL_PASSWORD@127.0.0.1:62124/social_worker_test'
PYTHONPATH=backend "$PYTHON" -m pytest --confcutdir=backend/tests/egress backend/tests/egress -q

"$PYTHON" docs/infrastructure/supabase-egress/batch2-egress/benchmark.py \
  --database-url "$EGRESS_TEST_DATABASE_URL"
```

Set `$PYTHON` and `EGRESS_TEST_DATABASE_URL` in the local shell for both commands. Do not use a deployed DSN. The benchmark assigns its verified URL only inside its own process for router dependency import; it does not edit `.env` or affect a running application. JSON output contains aggregate counts and estimates, with no SQL parameters, document bodies, credentials, or provider URLs. A benchmark failure prints only an error class.

The worker portion explicitly constructs fake adapters from test fixtures. It never enables a fake deployment adapter or contacts a provider. For a baseline comparison, run the same fixture lane against the baseline's three owned production files in an isolated checkout; the harness itself is measurement code, not a production feature.

## Existing worker headroom receipt

| Isolated operation | DBAPI statements | Returned rows | Selected-value byte estimate | Peak checked-out DB connections |
|---|---:|---:|---:|---:|
| Empty scan: recovery, claim, next-due check | 6 | 3 | 3 | 1 |
| Idle heartbeat | 2 | 1 | 1 | 1 |
| One fake public publication | 33 | 21 | 6,555 | 1 |
| Two concurrent fake public publications | 63 | 40 | 13,272 | 2 |

All captured DBAPI statements are counted, including pre-ping `SELECT 1`; these are not only business queries. The concurrent fixture required both fake external requests to overlap, measured a peak of two, and used a pool of two with zero overflow. Safety gates, intent/checkpoint writes, account serialization, retries, and heartbeat behavior remain unchanged. Worker implementation files were not edited.

At the existing 30-second idle-scan and 60-second idle-heartbeat cadences, 30 completely idle days imply 86,400 scans plus 43,200 heartbeats, or approximately 604,800 statements with this pre-ping configuration. Empty-result protocol overhead can dominate the tiny decoded values. This measurement therefore does **not** establish the social 200 MB/month budget. Real work, recovery, reconnects, logs, and metadata growth add traffic.

The existing web pool and its overflow configuration are unchanged. Replica counts, ETL processes, connection limits, and hosting-plan support for an always-on worker were not observed. The isolated two-connection worker result cannot establish shared application or hosting capacity.

## Outstanding operational acceptance gates

Issue #481 remains open until representative operational evidence is available:

1. Attribute real uncached database/pooler usage across deployments, ingestion, public/API activity, and social work, using provider counter/reset boundaries and matching timestamps.
2. Measure at least seven representative days, including deployment/ingestion spikes, against the approximately 120 MB/day overall planning target and current organization allowance.
3. Measure actual protocol/provider accounting during a bounded social pilot against the 200 MB/month planning budget, including realistic payload/checkpoint sizes and metadata growth.
4. Verify the actual hosting plan, always-on process ownership, replica/ETL connection demand, and shared pool headroom before enabling the worker.

Provider access, the seven-day observation window, and hosting evidence were unavailable in this scoped implementation. Local decoded-value reductions satisfy neither those live gates nor acceptance of media/API costs. Other public-page/cache/source-registry work, economic-indicator writer changes, migrations, credentials, and deployment configuration are outside this change.
