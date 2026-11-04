# Current allocation and population worksheet

This worksheet grants no activation. Private role/endpoint hashes and raw
observations live with the lane handoff, outside Git. A missing population,
history or accepted reserve remains unknown, not zero.

## Render memory, CPU and stop

The final packet observed the existing 512 MiB memory and 0.5 CPU quotas. Current
memory was 298,708,992 / 305,528,832 / 327,933,952 bytes before/between/after;
the kernel lifetime peak at completion was 342,409,216 bytes (326.547 MiB).
Remaining space against that peak was 185.453 MiB. All recorded OOM counters
were zero. These samples include live web and shell/observer overhead; do not add
constructor RSS or an independently sampled peak to them. They do not isolate
codec peak, establish sustained reserve or erase older peaks on other instances.

CPU usage increased 1,018,789 microseconds over the 2.210037-second observation,
about 0.461 core during this tiny interval. This is not the future workload's
steady mean or proof of the proposed 0.1-core reserve. No CPU plan was changed.

The existing proposed worker envelope is peak <=460 MiB, reserve >=52 MiB,
current abort at480 MiB; steady mean <=0.4 core and reserve0.1 core. These remain
proposals pending owner acceptance and representative measurement. The codec's
96 MiB execution guard is a different limit.

Current Render Settings does not expose shutdown delay. Existing local/host
environment checks found no Render API credential and no local CLI/configuration.
An ordinary verified-TLS Retrieve service GET returned HTTP401. No credential
was created or extracted from browser state. Required minimal observation is the
current service's `serviceDetails.maxShutdownDelaySeconds` field, with service and
observation identity, from an existing authorized control-plane read. Historical
90 seconds and the documented default30 seconds cannot fill it.

The future profile requires explicit drain60s, whole stop<=75s and measured
web/reap<10s **inside the confirmed provider window**, including margin. Until
that comparison passes, stop/canary admission is held. The official
[Retrieve service](https://api-docs.render.com/reference/retrieve-service) and
[shutdown documentation](https://render.com/docs/deploys#graceful-shutdown)
describe the API and default behavior; they do not attest this service.

## Process and route populations

| Population | Source ceiling per process | Current evidence and overlap |
| --- | --- | --- |
| Web legacy/bootstrap | `backend/database.py:56`, 5+10=15 | One serving Gunicorn master/one application worker. Legacy engine, request and audit writer use `DATABASE_URL`; separate engine objects do not imply all slots are open. |
| Web request | `backend/request_database.py:129`, 5+0 | Same configured primary route/login; concurrent HTTP reads share this process, not separate 5-slot pools per request. |
| HTTP audit writer | `backend/database.py:76`, 1+0 | Primary URL; separate one-slot engine. Outside request context the helper falls back to legacy SessionLocal (`database.py:89`). Do not double-count that fallback as a new pool. |
| Restricted audit reader | `backend/services/admin_audit_storage.py:51`, 1+0 | `ADMIN_AUDIT_DATABASE_URL`, distinct reader reference; used lazily for PostgreSQL visibility reads. |
| Web total | 22 configured client slots | A source ceiling for one app process, not measured use or backend reservation. |
| Future native worker | `backend/social/worker/config.py:78`, 2+0 | Zero current processes; protected worker reference separate from primary/reader. One future worker makes subtotal24 before all populations below. |
| Admin dispatcher | `backend/admin_etl_dispatch_worker.py:338` | Zero coarse processes; imports separate-process `database.SessionLocal`; engine capacity cannot be shared with the web process by arithmetic. Consumer stays OFF. |
| Admin qualification | `backend/admin_etl_qualification_worker.py:23`, 3+0 | OFF; distinct bounded factory if invoked. No invocation here. |
| GitHub seed domains | `.github/workflows/seed.yml:104` | Ordinary run41759203897 completed failure before this lane's observations. Job uses repository secret `DATABASE_URL`; equality with Render secret values is not observable through variable names. Do not presume matching login/route. No hosted secret export/dispatch here. |
| Source/cache helper | `backend/seeding/source_cache.py:415` | Own SQLAlchemy engine with resolved driver defaults (QueuePool5+10 on the installed PostgreSQL driver); bounded one connection in this helper's current body. Map process/driver/secret through the nightly lane. Ceiling is not simultaneous usage. |
| Startup seeder/warmup | `backend/services/auto_seeder.py`, `backend/main.py:1759,1818` | Explicit inherited false in fresh host observations. No startup was initiated. |
| In-process scheduler | `backend/main.py:8013` | Current instance logs at23:47:26UTC show scheduler started and weekly digest job added; inherited APScheduler distribution3.11.3 observed. Zero background processes cannot mean zero scheduled jobs. Exact next fire/running-instance state remains unavailable. |
| Legacy discovery/Parliament | `backend/main.py:8039,8087` | Current-instance startup logs show legacy discovery unavailable/skipped and Parliament disabled; inherited Parliament flag is0. No task was stopped or triggered. |
| Legacy ETL/backfill | `etl/worker.py:94`, direct advisory-lock connection plus child; `etl/database_loader.py:139`, NullPool | No matching current coarse process observed on Render. Other deployments/operators remain separate unknown populations. Lock holder and each concurrent backfill count independently. |
| Migrations/reconciliation | `backend/alembic/env.py:166`, `backend/seeding/reconcile_operator.py:56`, NullPool | None invoked here. NullPool prevents retention, not concurrent connections. Nightly migration activity belongs in overlap. |
| Recovery/maintenance | `backend/social/recovery_operator.py:77`, 2+0; `backend/social/media/maintenance.py:109` | No live invocation. Operator role may differ from worker; retained ownership is never cleared to manufacture an eligible census. |
| Platform/dashboard/operator | Supabase platform clients, Studio, other engineering lanes and existing tools | Dashboard and catalog observers themselves consume capacity. Current sequential role views are neither account-wide exclusive-user proof nor a pooler client census. Owner must reconcile authorized operators and credential copies. |

`database_enhanced.py` has a separate configurable20+40 factory but no import in
the searched backend/etl/scripts Python source; it is not counted as a serving
process. Future deployments must repeat that wiring check. The worksheet's
24+other-clients+accepted-reserve inequality applies only after partitioning by
actual route/login and limit unit. No unnamed reserve is silently assigned zero.

## Supabase units and current observations

Current dashboard shows Healthy, Micro/1GB selected, spend cap enabled and
0.37GB disk used of2GB provisioned. The overview displayed13/60 connections;
that literal aggregate is not a per-app peak or a worker reservation. No selection
or plan change was made. Pooler clients, per-user/database server backends and
physical PostgreSQL connections remain distinct populations. Current database
settings display200 maximum pooler clients and15 backend connections per
user/database; the bounded catalog shows60 database connections;
never treat22/24 source slots as utilization of one common limit.

At03:07:53UTC on4November, the reviewed bounded observer completed in0.882s,
exit0. Primary web/legacy/audit-writer reference routes through the transaction
pooler on6543. Restricted audit reader and configured future-worker references
use session pooling on5432, with distinct logins. Configured project-suffix hashes
match, and each configured role hash matches its own connected catalog identity.
This is configured route/login reconciliation, not physical-backend attestation.

The primary view had full-statistics visibility:16 catalog process rows, of which
**eight were client backends including this observer**, and eight were other
backend types. Only the observer was active; no idle-in-transaction or waiting-lock
count was observed in that snapshot. One client principal remains unclassified
by the finite standard-role dictionary; role matching cannot identify the actual
process or credential holder. Reader/worker views were masked for other principals
and were observed sequentially. Do not sum those views or call16/60 utilization.
This still does not count idle transaction-pooler clients, all external callers,
historical peaks, operator credential copies or application pool checkouts.

All three connected login views showed non-superuser login roles; primary and
reader connection limits were-1, worker limit2. This is not a new grant/authority
verification. Effective observer-session settings were max_connections60,
superuser_reserved_connections3, reserved_connections0, shared_buffers256MiB,
work_mem3500KiB, hash_mem_multiplier2, maintenance_work_mem64MiB and
autovacuum_max_workers3. They do not establish other roles' overrides, global
memory commitment semantics or an accepted reserve.

The bounded catalog observer uses unchanged reviewed catalog queries, verify-full
TLS and existing CA, NullPool, read-only transactions, 3s statements/1s locks and
a finite observation alarm. It projects hashes/counts only, never SQL text,
credential values or application rows. Current observations or refusals and their
visibility limits belong in the private handoff. A database-name hash does not
establish physical backend identity; masked stats do not establish a complete
client census or history.

The current Last60minutes dashboard window labels3November8:06–9:06p.m. and
shows memory794.5MB, commitment1.32GB and CPU10.63%. Database, dedicated-pooler
and shared-pooler connection history charts all say unable to load data. These
are provider-rendered headlines/availability observations, not validated peaks,
physical used-RAM attribution, isolated workload cost or a diagnosed leak.
Mixed-release egress remains a separate operating measurement. No zero-cost
forecast, free-tier admission, upgrade,
PostgreSQL tuning, monitoring purchase or future egress guarantee follows here.
