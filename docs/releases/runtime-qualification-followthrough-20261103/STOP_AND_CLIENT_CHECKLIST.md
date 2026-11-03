# Stop timing and client inventory — current observations still required

This checklist is read-only preparation for the parent. No production command,
setting change, new credential, broader scope, worker or database query was
executed by this work session. Raw provider/account/role data stays external.

## Discoverable stop metadata

The retained `render-settings-current.txt` observation inspected the actual
service settings and did not expose a shutdown-delay field. It is an observation
gap, not an owner-selected reserve. Historical 90 seconds remains historical.
Render's documented default 30 seconds is not this service's current metadata.

The official [Retrieve service API](https://api-docs.render.com/reference/retrieve-service)
provides a read-only `GET /v1/services/{serviceId}`. The parent can inspect the
existing service response using already available authorized access, if any.
Check the typed service-details object for `maxShutdownDelaySeconds`, alongside
service identity/type, current allocation, start command, active deployment and
auto-deploy state. Retain the exact response privately and a safe field-only
projection with timestamp and source hash. Do not print authorization headers,
environment-variable lists or registry credentials. This packet supplies no API
token and authorizes no new credential or scope. If existing access cannot read
it, retain the exact HTTP status/refusal or missing-field response and mark
**current stop timing unavailable**. Do not call Update service or trigger a
restart/deploy to discover it.

The public [Render shutdown documentation](https://render.com/docs/deploys#graceful-shutdown)
and [Blueprint field reference](https://render.com/docs/blueprint-spec#maxshutdowndelayseconds)
describe `maxShutdownDelaySeconds`, SIGTERM followed by SIGKILL and a default
30-second delay, configurable up to 300 seconds subject to service restrictions.
They explain the setting; they do not attest this service. Public documentation
was checked on 3 November. A direct local request for its OpenAPI JSON returned
HTTP 403; the same public schema was readable through the web research tool.
Neither operation queried the production control plane.

Before any later worker canary, compare the **current confirmed** host window
with the existing proposed 60-second worker drain, 75-second whole stop and
web/reap margin in the historical worker plan. Missing or too-short metadata
keeps that canary held. `SOCIAL_WORKER_SHUTDOWN_SECONDS` is a launcher drain
setting (`backend/social_worker_supervisor.py:39`), not evidence of the provider
window. The OFF-state tiny-codec packet neither needs nor accepts a worker stop
window. No stop limit is changed here.

## Source-derived population worksheet

These are maximum configured **client connections per process**, before other
clients and reserve. They are not observed open sockets, backend reservations
or summed usage of one shared limit.

| Population | Source and configured bound | Remaining read-only evidence |
| --- | --- | --- |
| Web legacy/bootstrap | `backend/database.py:56`, 5 pooled + 10 overflow | Actual process count and destination/login/routing |
| Web request pool | `backend/request_database.py:16,129`, 5 + 0 | Same mapping and current usage |
| Web audit writer | `backend/request_database.py:20,142`, 1 + 0 | Actual audit-writer destination/role |
| Restricted audit reader | `backend/services/admin_audit_storage.py:51,55`, `backend/request_database.py:26,135`, 1 + 0 | Separate configured reference, role/visibility and client population |
| Web subtotal | 15 + 5 + 1 + 1 = **22** for one process | Confirm actual launcher/replicas, lazy engine use and other processes |
| Future social worker | `backend/social/worker/config.py:76`, 2 + 0 | Still OFF; worker role historical `rolconnlimit=2`, fresh catalog identity required |
| Web plus one future worker | **24**, before all rows below and accepted reserves | Planning ceiling only |
| Admin ETL dispatcher | `backend/admin_etl_dispatch_worker.py:338,351`, uses `database.SessionLocal` | Consumer OFF; separate process imports also construct web module engines, so do not assume one shared web pool |
| Admin qualification worker | `backend/admin_etl_qualification_worker.py:23`, separate 3 + 0 engine | OFF; identify any actual process before counting |
| Nightly seed/cache | `.github/workflows/seed.yml:104,971`; `backend/seeding/source_cache.py:415` creates a separate engine | Exact job overlap, subprocesses, endpoint/role and driver-resolved defaults; no dispatch |
| Legacy ETL scheduler/backfill | `etl/worker.py:94` opens a direct psycopg2 advisory-lock connection and starts `etl.backfill`; `etl/database_loader.py:139` uses PostgreSQL `NullPool` | No worker start; inventory existing lock holder, backfill processes and transaction concurrency separately |
| Startup seeder/warmup | `backend/services/auto_seeder.py:279,412`, `backend/main.py:1759,1818,1885` | Explicit false resolved in running app; warmup HTTP activity can consume request pools, not a new fixed connection allowance |
| In-process scheduled jobs | `backend/main.py:1772,8013,8080,8087,8212` calls APScheduler setup, conditional discovery/Parliament scheduling and weekly digest scheduling | Coarse background-process count cannot attest task absence; parent must inspect existing startup/job metadata read-only, without starting or triggering a job |
| Migration/reconciliation | `backend/alembic/env.py:166`, `backend/seeding/reconcile_operator.py:56`, `NullPool` | No persistent pool ceiling means concurrent invocations still count; none run here |
| Recovery/maintenance operators | `backend/social/recovery_operator.py:77`, 2 + 0; `backend/social/media/maintenance.py:109` uses worker engine | No operator/maintenance invocation; inventory any existing process separately |
| Enhanced database module | `backend/database_enhanced.py:47`, configurable defaults 20 + 40 | No import found in searched `backend/`, `etl/`, `scripts/` Python sources; do not count it as a serving process without runtime evidence |
| Platform/other operators | Supabase platform/dashboard/SQL clients, monitoring, external tasks and copies of credentials | Provider aggregate/history, all authorized runtime surfaces and named operator census; not inferable from repository code |

For **each actual** process population, parent inventory must record the exact
service/process count, purpose, concurrency ceiling, destination project route,
endpoint family/port, hashed role/login, pool mode, configured client ceiling,
observed connections and timestamp, effective limit/reserve and evidence hash.
Use a fresh private topology table; do not commit raw DSNs/account metadata or
issue SQL just because this worksheet names it. All runtime surfaces include
Render replicas/services, ordinary scheduled GitHub jobs, existing local/operator
tools and platform clients. An absent process on one host is not an account-wide
complete inventory. Known application state remains OFF, while the ordinary
nightly lane is owned by the parent and must be included in overlap planning.

## Distinct limit units and protected database scope

The historical provider observations were **200 pooler client connections**,
**15 backend connections per user/database** and **60 database connections**.
Apply each only to its own routed population. The instantaneous catalog held
13 `pg_stat_activity` process rows but only **five client backends including the
observer**; 13/60 is not utilization. Masked/restricted and sequential role views
do not establish pooler clients, all projects, sustained peaks or exclusive users.
Matching database-name hashes do not prove physical backend identity. The separate
configured project-route comparison is historical evidence with that limited scope.

Keep privileged catalog reads in the existing separately reviewed guard scope:
`db_capacity_v5.py` SHA
`6075a49e830002207b78643b672e39d691fe90564f6729d8c6fad36b41d98811`
and its retained `db-command-v5.txt` belong to the prior private packet. Its queries
are catalog-only, no query text/app rows, `NullPool`, verify-full TLS with the
existing CA, bounded 30-second observation, 3-second statements/1-second locks,
read-only transactions, rollback/dispose and no exception-body projection.
Its old held-flag inventory predates the corrected warmup guard. Do **not** run
it unwrapped or treat this note as a new review/authority: parent must bind the
corrected probe's explicit seeder/warmup check before and after, review the exact
existing command and preserve existing privilege/TLS/query bounds. No query or
guard modification is included here.

Prior concrete catalog refusals remain retained: v3 emitted generic refusal
with cause unknown; v4 rejected the backend-type validator. v5 later observed the
catalog. Do not characterize those parser refusals as provider denial or missing
provider metadata. Missing connection-history charts and memory commitment
semantics remain unavailable in the retained provider UI observations. The
1.29 GB commitment warning, 796.22 MB usage and 0.62% CPU are historical UI
headlines, not validated peaks/limits or proof of a leak. Preserve the exact
unavailable-chart observation; do not invent a reconstruction or buy monitoring.

Complete client/role topology and stop timing are discoverable engineering facts
to pursue read-only using existing access. Positive memory/CPU/client/byte reserves,
named custody and separately authorized pilot scopes remain genuine owner inputs.
No positive reserve, exclusive-writer claim, sustained workload or guaranteed
no-cost profile has been supplied or accepted by this packet.
