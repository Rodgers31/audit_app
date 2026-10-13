# Batch 12 production rollout and worker acceptance

This PR supplies a read-only database observer, an immutable migration planner,
owned migration/worker controls, and the ordered operator procedure below.
Production execution and acceptance remain pending. #583, #554 and #545 remain
open; #611 owns the separate durable audit-storage release.

## Coordinator review correction — October 12, 2026

The observer now defaults to `sslmode=require`, rejects insecure, unknown,
empty and repeated modes, and fingerprints the effective mode. The opened
connection explicitly uses that mode and verifies `pg_stat_ssl` before reading
operational state. Receipts record both the mode and actual encryption. Only the
existing passwordless `postgres` test profile at literal 127.0.0.1 ports
55496/55560 with its exact generated reconciliation database name uses plaintext;
that profile has a different fingerprint and cannot authorize a TLS endpoint.
Explicit `sslmode=disable` URLs remain refused. `require` proves encryption,
while certificate/name verification requires the reviewed `verify-ca` or
`verify-full` mode. These are distinct endpoint identities.

Published plans now validate their exact generator provenance, malformed migration
metadata gives a fixed refusal, and output-guard controls use valid receipts with
named diagnostics. The original helper/observation packets are historical inputs;
their generator hashes are unchanged. Old observations lack the newly required
transport fields and cannot be used as current accepted plans. A new production
observation requires a freshly reviewed TLS-bound endpoint and actual connection.

Review regressions reproduced 13 failures on the unfixed helper. The fixed
non-database cohort passed 54 cases on each current/minimum normal/optimized run
in external `BATCH_12_REVIEW/640_UNIT_V2`; full owned PostgreSQL and immutable
combined hosted verification are recorded separately by the coordinator. #642
tracks these consumer/validation repairs. No production readiness is implied.

## Scope and evidence identity

Reviewed baseline main: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree
`3a680eef19822ef0ac83aa6890c3b41deee97058`. Branch:
`codex/batch12-production-rollout`. Changes are confined to
`backend/scripts/batch12_rollout*`, `backend/tests/test_batch12_rollout*` and this
handoff. Migrations, models, existing writers, dependency manifests, shared
workflows, primary checkout and peer worktrees are outside this delivery.

Append-only execution evidence is in the coordinator's external Batch 12
`ROLLOUT/` lane. `START.json` identifies the initial checkout, ports and clean
environment. `github-v1/` contains complete paginated issue checkpoints,
comments, PR bodies, reviews and replies for #583/#554/#545 and
#584/#590/#592/#596/#604/#606/#609/#619/#626. `REVIEW_CONTEXT.md` and
`SOURCE_REQUIREMENTS_RECEIPT.json` record the independent source review.
`REVIEW_CURRENT.md` records the final helper review, including 20 direct controls
in normal and optimized Python. Its acceptance is restricted to that helper.
Delivery commit and draft PR identities belong in the final external receipt;
a commit cannot contain its own SHA.

Historical failed, red, setup and cancelled executions remain preserved. Their
source hashes and results are not changed to describe later source. The final
execution manifest identifies the exact source, generator, runtime, command,
JUnit identities, output and cleanup consumed for each acceptance claim.

## Actual production observation

Read-only observation and provider UI were refreshed on October 12, 2026.
These snapshots cannot certify later quiescence or authorize an outage.

| Surface | Observed state | Consequence |
| --- | --- | --- |
| GitHub main | Accepted baseline above | Source acceptance is separate from deployment. |
| Repository Actions | `enabled=false`; five static workflows manually disabled | Preserve this fence. Queued/manual/provider launch paths still need a deployed census. |
| Render `audit_app` | Live deployment `dep-db3oskc9v7es73dtuvc0`, commit `2d3cd5959df1914bf068cb0381057d1bcbbabf81`; Auto-Deploy off; one instance | The backend is older than accepted main. Actual image and installed runtime are unverified. |
| Render flags | `AUTO_SEEDER_ENABLED=false`, `PARLIAMENT_PIPELINE_ENABLED=0`, `WEB_CONCURRENCY=1` | These values do not fence bootstrap, scheduler threads, manual deploys or Gunicorn worker replacement. |
| Vercel deployment metadata | Production deployment `6989105785` reports success at baseline main | This is deployment metadata; authenticated deployed UI acceptance remains pending. |
| Supabase `audit_gava` | Project `xznjxwrkbkahwtnbstbj`, `eu-central-1`, PostgreSQL 17.6 | Independently bind every writer's actual credential target to this project and database. |
| Database | `postgres`, OID 5, system identifier `7626352619084395911`, revision `ea1645a4c0b5` | Eleven exact baseline migrations remain. Claim/dispatch tables are absent. |
| Actual database role | `postgres`, `rolsuper=false`, `rolbypassrls=true` | **Accepted reconciliation requires actual superuser status. It cannot run with this role.** |
| Admission/census | Admission open; 12 other target sessions in refreshed snapshot; zero prepared transactions | No durable client admission fence or sole-session operator proof exists. |
| RUNNING observations | IDs 1167 (`national_budget`), 1655/2651 (`fiscal_summary`); claim/command tags absent | Retain the entire exact set. Age and absence of a claim are insufficient to dispose of uncertainty. |
| Backups UI | Seven visible physical backups; latest `2026-10-11T23:36:04Z`; storage objects excluded | Backup availability is observed. Production restore, coverage and recovery acceptance are unverified. |
| Direct connection UI | `db.xznjxwrkbkahwtnbstbj.supabase.co:5432`, role/database `postgres`; IPv6 default | UI availability is not certified direct connection continuity or maintenance capability. |

`DATABASE_OBSERVATION_V2.json`, `BASELINE_PLAN_V2.json`,
`PROVIDER_METADATA_V1.json` and `SUPABASE_PROVIDER_METADATA_V2.json` retain these
observations without passwords. The SQL observer used an explicit READ ONLY
repeatable-read transaction and rolled back. It queried catalogs and bounded
operational metadata. No app HTTP probes or financial-table census were used.
The independently observed Render endpoint was compared with the read-only
locally configured database endpoint before connection. GitHub's database secret
target remains independently unverified.

The concrete provider blocker needs a separately reviewed provider-assisted
maintenance mechanism, or a reviewed change to the accepted operator followed
by new acceptance. Renaming a role, switching from pooler to direct transport,
or removing a guard cannot establish the missing privilege. Provider background
sessions and admission control must also be resolved. This PR implements no such
exception and performs no production change.

## Observer and planner

From a frozen checkout, with an isolated supported runtime, a clean allowlisted
environment and a provisioned `BATCH12_ROLLOUT_DATABASE_URL`:

```text
<python> -B backend/scripts/batch12_rollout.py observe \
  --expected-endpoint-sha256 <independently-verified-endpoint-hash> \
  --out <absolute-fresh-external-path>/observation.json
<python> -B backend/scripts/batch12_rollout.py plan \
  --observation <absolute-external-path>/observation.json \
  --out <absolute-fresh-external-path>/plan.json
```

The endpoint hash binds host, port, database and connection role, excluding the
password. No ambient libpq redirects or query overrides except `sslmode` are
accepted. The catalog role can differ from a pooler's connection username; both
identities are retained separately. `connection_mode=unverified_from_catalogs`
expressly avoids certifying a direct path from catalogs alone.

Planning requires a strict current UTC observation (maximum age five minutes,
maximum clock lead 30 seconds), bounded typed rows, unique identities and one
known revision. Generated observations must match the actual generator bytes.
The output parent is traversed without following links and retained by directory
FD before observation. Publication is exclusive, mode 0600, fsynced and read
back, with file and parent identity checks. A parent replacement causes refusal,
even if an anchored private evidence file was already created. Preserve that
file for investigation. Never overwrite or relabel a receipt.

Every output states `production_ready=false`; plans also state
`production_execution_authorized=false`. Successful `observed` or `planned`
status is only helper completion. The helper has no migration, fencing,
reconciliation, deploy or activation operation. A structurally valid submitted
observation is not an independently signed production certificate.

The full accepted migration ancestry/file corpus has SHA256
`6dd02de2b7357f6f28708e4b46276eb774ec871a21048beff2eb84212617625f`.
The exact suffix from observed `ea1645a4c0b5` is:

```text
c415a10d2026 → f38c61a9d203 → c96d13e2f411 → a42b86e1d310
→ b73e19a4f602 → d8f4a619b203 → e554d7c9a001 → e572b8c9a001
→ e583b9c9a001 → e554b10a0001 → e602b11a0001
```

Use the plan's exact per-file hashes and `alembic upgrade e602b11a0001`.
Missing/modified/duplicate ancestry, unknown/multiple revision, or an observed
future audit revision refuses. Future additive descendant files are excluded
from this baseline plan. `upgrade head` cannot substitute for the explicit
reviewed target; existing workflow head upgrades must remain fenced.

## Ordered production procedure for a later authorized release

Each numbered phase needs an owner, exact source/image/runtime identity,
timestamped source-bound evidence and explicit disposition. An unknown item is
a stop condition. Coordinator review of this PR is separate from production
execution authorization.

1. **Freeze the candidate and targets.** Verify the final reviewed commit, tree,
   Docker build context, image digest, Python/SQLAlchemy/driver packages and
   actual module/route inventory. Bind Render, Vercel, Supabase, GitHub-secret,
   scheduler, operator and manual-client credentials independently, without
   publishing values. Determine actual DDL and maintenance privileges. Resolve
   the non-superuser/provider blocker before scheduling maintenance.
2. **Verify recovery before touching production.** Obtain a current authorized
   backup with immutable identity and checksums. Account for database data,
   revision, sequences, roles, grants, RLS, policies, indexes, constraints,
   functions/triggers, storage objects and external effects. Restore to a
   separately owned isolated target with transports fenced; compare actual
   state and recovery application compatibility. Record source and restored
   cluster/database identities. A provider backup badge or an empty local
   skeleton restore is insufficient. Protect credentials and custody outside
   repository evidence. Agree the exact recovery decision and owners.
3. **Inventory every deployed writer and resume path.** Complete the census
   below for all hosts, replicas, background processes, sessions, tasks,
   schedules, queued/running jobs, manual clients, provider services and
   credential holders. Record actual PID/birth or provider job/deploy identity,
   target fingerprint, command/source/image, effects and durable restart fence.
   Discover adapter orphans independently of their supervisors.
4. **Establish and verify durable fences.** Stop or prove absent each writer and
   prevent reconnect/restart/replacement/manual admission. Include service
   wake, Auto-Deploy/manual deploy, autoscaling, health replacement, Gunicorn
   recycle, Compose restart policy, workflow dispatch/queues/timers and provider
   connection routes. Keep API startup and source-fetch transports fenced.
   Existing Actions OFF is preserved. Do not certify from an idle database
   snapshot, a disabled flag, a killed connection or an expired worker lease.
5. **Perform the separate fenced migration phase.** Under the independently
   authorized provider fence, admit only the reviewed migration client and any
   explicitly required retained operator connection. Recheck current revision,
   schema and exact migration hashes; refuse unexpected partial tables or
   histories. Run `alembic upgrade e602b11a0001` with bounded lock/statement
   limits and exact output/exit receipts. Independently read back the revision,
   column types/nullability, constraints, indexes, mappings, RLS/grants and the
   complete preexisting RUNNING/claim/command set. Repeat-target no-op is a
   separate readback. A failed migration must not be stamped or manually
   repaired. Close the migration and readback connections when this phase ends.
6. **Retain the reviewed direct operator session, then close admission.** Start
   `python -m seeding.reconcile_operator` with independently provisioned private
   policy path/hash, trusted signing scopes and an exact direct database URL
   before the final admission closure. Ensure a clean retained backend, public
   search path, UTC, exact actual cluster/database/role and required privileges.
   Establish provider admission closure and read back `datallowconn=false`,
   zero other target backends (including background/provider writers) and zero
   prepared transactions. Alembic opens a fresh connection: it cannot be run
   after this closure by bypassing the fence. Stop if sole-session/provider
   maintenance cannot be established; do not weaken the accepted operator.
7. **Investigate every retained owner and untagged RUNNING row.** Use the same
   retained operator backend's bounded `inspect` context. Preserve the complete
   original set and correlate any claim/command/job/entry identity exactly.
   Reconcile all affected public-table and external effects independently,
   including partial effects, source/storage/email calls, live or stopped host
   processes and adapters whose DB connection disappeared. An unresolved
   process or effect is uncertainty. Prepare independently signed, current
   host/scheduler statements covering every required category and the exact
   effects/context digest. Never manufacture zero effects or replacement tags.
8. **Plan, inspect and explicitly apply on that same backend.** Submit distinct
   newline JSON inspect/plan/apply requests using the deployment-provisioned
   policy. Review the plan's exact selected set, effects/context, operator and
   signer evidence, expiry, target and continuity. Apply only after the
   separately authorized decision. Verify atomic durable reconciliation audit,
   retained original identity/history, exact claim release, correlated RUNNING
   failure and dispatch interrupted/domain disposition. Another connection or
   changed effects/evidence requires a new investigation and plan. Refusal,
   session loss, expired evidence or ambiguous commit keeps all fences held;
   inspect durable audit/ownership before any new session. No blind apply retry,
   automatic expiry, lease reclaim or fabricated completion is acceptable.
   **After successful durable readback, keep admission closed until the next
   separately authorized phase.** Retire the consumed evidence/plan and dispose
   of the old operator session. The provider owner may then perform an explicit,
   recorded admission transition for only the reviewed migration or bounded
   worker clients, while every other writer/restart/reconnect fence remains
   held. Independently verify the allowed roles/routes/targets and all excluded
   clients. An unrestricted admission reopening is insufficient. If bounded
   admission cannot be established, keep closure and stop. Any later
   reconciliation requires a new retained backend and the full phase 6–8
   sequence; the old plan cannot be reused.
9. **Handle #611 as a separate exact release.** Re-read its migration contract,
   frozen reviewed head and source hashes. Rehearse the combined source on an
   owned replica before a new production decision. Apply only its reviewed
   explicit revision in a distinct stopped-worker/fenced migration phase.
   Independently provision reader/writer roles, certification/incarnation and
   bookmark authority. Existing rows missing provenance must remain unavailable;
   no synthetic backfill or uncertified restored history. Verify old writer
   INSERT compatibility and reader ACL/RLS/append-only behavior. Do not extend
   this baseline plan to an unfrozen audit head.
   The phase 8 admission transition is a prerequisite for its fresh Alembic
   connection. `frozen_head=null` stops this combined release; a different
   baseline-only scope requires its own explicit reviewed decision.
10. **Stage and authorize bounded worker activation.** Recheck the exact runtime,
    route registration, native CLI/core/domain imports, schema and independent
    auth/profile roles in the real deployed configuration. Keep dispatch
    default-off until the activation decision. Start one separately identified
    dedicated supervisor with an explicit supported source selection; OAG is
    the initial bounded acceptance source. Native, legacy, bootstrap and
    scheduler restart fences remain held as required. A ready lease alone
    cannot release a retained domain. CRA requires its separate strict opt-in,
    reviewed publication contract and source acceptance; OpenData remains
    unsupported.
   Admit the worker connection only through the separately verified phase 8
   transition. A successful reconciliation does not itself reopen admission.
11. **Accept actual deployed behavior, then release fences explicitly.** Verify
    real admin and non-admin/unauthenticated requests, private no-store headers,
    capability freshness/source scope, unavailable-before-worker refusal and
    exact correlated command lifecycle. A single accepted intent and its
    idempotent replay must share one command and one actor audit. Match the
    consumed command to actual supervisor/adapter/native CLI execution, one
    claim/job, terminal outcome and investigated effects. Include normal,
    operationally mutating dry-run, bounded failure, interrupted/death/restart,
    lost lease/backend and ambiguous acknowledgment controls in staged custody.
    Verify real deployed startup, route/error/redaction, authenticated UI, data
    freshness and audit-storage acceptance separately. Record durable acceptance
    and explicit fence release with owners. A 202, wrapper print, image deploy,
    calendar plan or worker heartbeat cannot establish completion.

## Writer and restart census

All rows below require actual deployed disposition; source presence is not proof
of deployment or absence. The accepted operator categories are
`native_scheduled`, `native_manual`, `dedicated_supervisor`,
`dedicated_adapter_orphans`, `legacy_etl`, `bootstrap`,
`application_auto_seeder`, `application_sessions`, `parliament`,
`migrations_manual_scripts`. Every independently trusted host/scheduler scope
must cover every category, including discovered channels not listed in source.

| Channel | Concrete source and fence obligation |
| --- | --- |
| API lifespan bootstrap | `backend/main.py` invokes `initialize_reference_data` before checking AutoSeeder; the observed older Render source does too. Fence every process start/recycle and its thread. |
| Bootstrap manual/weekly/force | `backend/bootstrap.py`, weekly `seed.yml`; reference group overlaps sixteen domains plus national budget. Force and county fast path do not remove ownership requirements. |
| API AutoSeeder | `backend/services/auto_seeder.py`; initial/hourly/weekly effects and reference commits. Confirm existing tasks stopped and future starts fenced. |
| Legacy manual/light discovery | `main.py` `/etl/run`; light mode still performs HTTP/storage/email effects. Deep refusal does not establish light-mode absence. |
| API legacy discovery scheduler | `main.py` APScheduler OAG/CoB/Treasury jobs; replica-local `max_instances` does not provide a maintenance fence. |
| Parliament and digest | `main.py` Parliament native children and weekly email digest; inventory processes and external transports, including separately flagged reconcile. |
| Native scheduled/manual CLI | `seed.yml` schedules/dispatch and `seeding.cli`; all supported domains and direct callers. Dry run still writes observations and claims. |
| Dedicated supervisor/adapter | `admin_etl_dispatch_worker` and actual adapter child/orphans; generation freshness is separate from effect certainty and domain ownership. |
| Legacy ETL services | `docker-compose.prod.yml` legacy workers/scripts and restart policies; include DatabaseLoader, manual wrappers and cron. |
| API replicas/sessions | Startup, scheduled/background tasks, request-owned writes, Gunicorn max-requests recycling and health replacement. Stop/reconnect fencing is required. |
| Migrations/deploy/CI | `seed.yml`, `ci.yml`, `docker-build-deploy.yml`, manual Alembic/SQL, image deploy and migrations. Existing head upgrades must stay fenced. |
| Provider/manual/unknown clients | Supabase API/PostgREST, realtime, background jobs, poolers, dashboard SQL, remote scripts, service roles and credential holders. Independently discover and account for them. |

Do not use production `/dispatch`, `/commands` or `/commands/{id}` GETs as a
read-only census: they can commit receipt retirement, including history while
dispatch is disabled. App requests may also wake startup bootstrap. Move those
checks into the explicitly authorized lifecycle phase. Weekly bootstrap's
current workflow ignores a False return before printing success; stdout must
not substitute for actual initialized/deferred/refused state.

## Recovery and abort

The baseline includes a reconciliation migration whose downgrade deliberately
refuses weakening. History-preserving migrations also refuse unsafe removal.
Generic `alembic downgrade` is not a recovery plan. Keep a reviewed application
rollback compatible with retained schema and a separately verified isolated
backup restore procedure. Preserve the original database, evidence, logs,
uncertain claims and external-effect accounting before recovery decisions.
Restore/PITR/clone changes target custody; rotate external audit incarnation and
withhold certification according to #611. Provider recovery, data loss decisions,
credential changes and production fence release require separate authorization.

## Local verification and compatibility boundary

The owned server was built from official PostgreSQL 17.6 source SHA256
`e0630a3600aea27511715563259ec2111cd5f4353a4b040e0be827f94cd7a8b0` and listens only
on reserved `127.0.0.1:55560`. Its binary/config/PID/birth/cluster identity are
recorded in `native-postgres/FIXTURE_V1.json`. Runtime variants are actual
Python 3.13.9 / SQLAlchemy 2.0.54 and Python 3.12.14 / SQLAlchemy 2.0.23, in owned
isolated runtime paths; archived interpreter/dependency origins are recorded.
No shared Docker restart or borrowed peer port was used. Autovacuum is disabled
only in this owned fixture; provider background maintenance remains unresolved.

The new controls exercise exact legacy/fresh migration and preserved RUNNING
rows, partial-schema transactional refusal, repeat-target no-op, RLS observation,
actual server read-only rejection, strict observation/publication guards and
parent replacement. Regression evidence starts with four genuine pre-fix
failures, then independently found missing/extra schema-field cases. Existing
accepted reconciliation/process/mapped controls exercise signed sole-session
release, atomic rollback, retained ownership, live disconnected/orphan writers,
exact effect readback and a subsequent real native/dedicated run.

The new worker fixture uses the real ETL HTTP router and JWT decoder, one actual
supervisor process, its actual adapter and unchanged native CLI. Only the profile
lookup and native domain handler are controlled seams. The handler uses owned
inert tables; Python socket transports are restricted, and complete DB name,
role, port, system ID and nonce are checked before product imports in normal and
optimized Python. This fixture omits `backend.main` lifespan. It does not prove
deployed startup, asymmetric JWKS/provider auth, production profiles, real source
ingestion, installed production image or production acceptance. Actual local
HTTP controls cover unavailable/non-admin refusal, one-use intent/replay,
normal/dry-run/failure effects and command/claim/job/audit correlation, including
the authenticated actor, command audit FK, action, target and exact dry-run
payload. An owned Popen measurement subclass records the adapter's real kernel
poll result; it does not replace its argv or completion decision. The handler
records its birth, argv, UID, PPID and process group. These additional observation
writes are fixture instrumentation. Top-level PID/birth/exit/group-cleanup
receipts are retained. Actual worker/adapter runs use normal Python; optimized
guard controls are separately scoped and do not certify an optimized adapter.

Both supported runtime cohorts passed 235 cases, with zero failures, errors or
skips. Their immutable V5 receipts predate the final audit/custody assertions.
The final V7 worker subset passed all three cases on each runtime at its updated
source hashes; those cases overlap the full cohorts and are not additional unique
coverage. The final fixture entry guard passed 28 actual invocations across both
runtimes, normal and optimized Python. Each runtime's separate optimized helper
subset passed 39 cases, with five database cases deliberately deselected; all
five are exercised in the normal full cohorts. These are local acceptance only.

The owned logical backup restored 53 public tables and preserved the legacy
RUNNING observation, actual rows, sequences, RLS, effective expanded ACLs,
indexes, triggers and constraints. Comparison preserves the raw before/after
receipts and explicitly normalizes exactly two PostgreSQL deparser rewrites
(array text casts and AND nesting). This is semantic equivalence of this owned
fixture, not byte equivalence or a production recovery rehearsal. Production
roles, provider/external storage and recovery coverage remain unverified.

Source/runtime bindings, raw logs, JUnit identities, backup and owned cleanup
dispositions are published in the external FINAL_MANIFEST.json and draft PR.
Required skipped,
setup-failed, storage-failed or source-drift runs are not acceptance. Host ENOSPC
and unavailable Docker attempts remain preserved; no tests or target guards are
weakened to turn those attempts green.

The #611 contract readback is `AUDIT_DEPENDENCY_READBACK.json`: planned additive
`a611b12a0001` after `e602b11a0001`, sidecar provenance and independent roles/
incarnation. At this handoff its published `frozen_head` is null. Combined exact
head rehearsal, provider certification and authenticated audit-reader acceptance
remain pending. No audit candidate was applied or copied into this lane.

Workflow result handling has a separately verified follow-up, #639. The exact
weekly/manual bootstrap Python wrapper exits zero and prints success even when
the actual bootstrap returns false for retained ownership. An owned PostgreSQL
reproduction preserved all public rows and sequences. This lane does not change
the coordinator-owned workflow; activation remains fenced pending an accurate
deferred/refused outcome and its own acceptance.

Suggested narrow shared-skill lesson for the coordinator: check route bodies
for writes before classifying authenticated GETs as observations, and place
fresh-connection Alembic migrations before the final admission-closed retained
operator phase. Actual examples are command-history receipt retirement and
`alembic/env.py`'s new NullPool connection. No shared skill file was edited.

Coordinator follow-up: plan receipts now require an exact JSON integer version;
boolean/float aliases reproduce the original dictionary-comparison gap and
are refused by the new guard. Production authority remains false. This is
part of #642, with final combined current/minimum native proof recorded before
merge. The earlier 54-case-per-mode packets remain historical, unchanged.

## Coordinator review: hosted worker fixture parity (#647)

The first complete combined hosted candidate (`7c803a1`, run38341871807)
failed all three new worker correlations. The startup guard accepted only
local55560; the canonical hosted reconciliation fixture uses55496. Its early
exit was then masked by cleanup treating a known exited root's zombie command
as a foreign process. The complete failed run is retained.

The rehearsal now permits only those two established owned ports and binds
the socket restriction to the validated selected port. Exact native database,
principal, cluster and nonce checks remain required. Cleanup first polls its
exact owned Popen handle, then retains independent process-group membership
and foreign-member refusals. An early HTTP child exit now reports its actual
exit and inert startup log. No production connection or provider path changed.

An exact native55496 reproduction fails the original unchanged worker case;
a separate native exited-root control fails original cleanup. With the repair,
all three actual HTTP/supervisor/adapter/native-CLI correlations and the exited
root control pass on current/minimum SQLAlchemy, normal and optimized runtimes
(four cases per execution). This scoped run's source is this PR and its template
uses e602b11a0001; fresh complete combined full-head/native hosted acceptance
remains required. These results do not certify production rollout or activation.

Independent review found a remaining exit-between-poll-and-census ordering.
A parent-controlled native child now reproduces that exact race on c5f66d4.
When a census fails command identity, cleanup re-polls only the known Popen
root and repeats the census only after confirmed exit; independent foreign
members still refuse. All five native controls pass on current/minimum,
normal/optimized execution. Independent literal-function controls verify
foreign UID/module refusal in both live-root and exited-root branches before
any signal or wait. These doubles supplement, and do not replace, native
process or fresh complete hosted acceptance.
