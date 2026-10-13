# Baseline production release preparation

Baseline schema target is **e602b11a0001**. The accepted source base is
`c8970e3953717fc0f0ca3a54e22f7e3e509eec0f`, tree
`1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8`. The separate audit successor
`a611b12a0001` is excluded from this release. A current checkout containing that
successor does not authorize `upgrade head` or deployment of an audit reader.

This is a concrete preparation procedure for coordinator review. It grants no
production authority. #583, #554 and #545 remain open. Accepted source and owned
rehearsals do not establish deployed writer quiescence or authenticated acceptance.

## Fresh read-only disposition

October 13 readback found repository Actions `enabled=false`; static workflows
186971728 CI, 236444317 Docker deploy, 378434636 R2 acceptance, 236444319 seed and
374266699 verification were `disabled_manually`. Dynamic Copilot workflow records
307672285, 265884629 and 265900628 remained `active` metadata under the disabled
repository. Preserve and inspect every discovered workflow; active metadata is
not an executed writer. Three historical verification records remain queued:
38348755971, 38346644137 and 37998042049. The coordinator owns their disposition
under #599; an OFF snapshot is not proof of their termination.

Render service `srv-d6hr3t5m5p6s73bomqu0` and Supabase project
`xznjxwrkbkahwtnbstbj` both redirected fresh browser navigation to sign-in.
Current provider state, installed source/image/runtime, database revision,
RUNNING rows, role privileges and Auto-Deploy setting are unverified. Earlier
`2d3cd595…`/Auto-Deploy-OFF and `ea1645a4c0b5`/three RUNNING observations remain
historical; do not reuse their timestamps or treat them as current empty state.
GitHub secret names are visible; values and targets remain independently unknown.

The new `backend/scripts/batch13_baseline_release.py` prepares and verifies a
packet from fresh typed inputs. Its 14 source control groups enumerate obligations,
not a complete deployed inventory. Every group remains `unverified`; the packet
always reports `blocked_production_prerequisites` and both authority/readiness
flags false. It performs file reads and exclusive external publication only.
It cannot execute SQL, migrate, deploy, stop a process or release a claim.

```text
<supported-python> backend/scripts/batch13_baseline_release.py prepare \
  --inputs <absolute-fresh-readbacks>/inputs.json \
  --out <absolute-fresh-external-path>/BASELINE_RELEASE_PACKET.json
<supported-python> backend/scripts/batch13_baseline_release.py verify \
  --inputs <same-readbacks>/inputs.json --packet <same-packet>
```

Inputs must retain the accepted base/tree, complete workflow census with unique
IDs/paths, nonterminal run identities, names-only secret metadata and exact
provider IDs/access disposition. UTC readbacks expire after five minutes with
maximum 30 seconds clock lead. `not_supplied` does not assert a new provider
observation. Authenticate and refresh actual provider readbacks separately; this
author tool intentionally cannot promote them to a maintenance certificate.
Archived expired packets remain evidence, but their current verifier must refuse.
Readers bind inputs, exact source/generator bytes and the immutable baseline
migration corpus. Missing/malformed/duplicate-key/nonfinite/stale/tampered inputs
and existing/symlink/source output destinations refuse in normal and Python -O.

## Exact identities required before a maintenance window

Assign a responsible operator and independent reviewer to each row. Retain who,
when, why, resource identities, raw readbacks, command exits and artifact hashes.
An unknown credential holder, session, process or restart path stops the release.

| Surface | Required exact inventory and fence readback |
| --- | --- |
| GitHub code/jobs | Repository ID1046703259; all workflow IDs/paths/revisions, dispatch/rerun/schedule permissions, all queued/running runs and runner child processes, environment/repository/org secret and variable holders. Preserve OFF; disabling a schedule alone is insufficient. |
| Render backend | Service ID above; workspace, sibling services/workers/cron, all deploy IDs/source commits, image digest/runtime/start/pre-deploy commands, replicas, PIDs/births, current build and deploy queues, hooks, API keys, manual deploy/rollback/restart/resume and health replacement rights. Disable/fence each launch channel through the reviewed provider action and verify actual stopped processes. |
| Render jobs | Enumerate each one-off job/cron ID, process and secret target. A base-service suspension/redeploy does not terminate an existing one-off job. Independently stop/fence each job and its launcher; inspect deployment/pre-deploy jobs and cron manual triggers. |
| Backend startup | `main.py` startup calls reference initialization before AutoSeeder. Stop every replica/thread and fence lifecycle restarts; account for all16 bootstrap effect domains plus the separate national-budget path. Read actual flags but do not use them as a lifecycle fence. |
| Application writers | AutoSeeder initial/hourly/weekly, APScheduler discovery, manual light/deep ETL, Parliament ingest/reconcile, digest/email, request sessions, dedicated supervisor, adapter orphans/native descendants and legacy compose restart/cron policies. Bind every host/PID/birth/group/generation and scheduler launch scope. |
| Supabase connections | Fresh project/region/database/OID/systemID/server-version/revision; direct host and IPv4/IPv6 route, shared session/transaction and dedicated pooler routes, connection username versus actual role, TLS mode and encryption. Inventory PostgREST/Auth/Storage/Realtime/Edge/cron/extensions/replication, dashboard SQL, replicas, prepared transactions and background maintenance. |
| Credentials | Independently fingerprint actual endpoint/project/database/role/TLS for GitHub DATABASE_URL/DATABASE_POOLER_URL, Render runtime/jobs, migration/operator, manual/native/legacy clients and Vercel server/browser API destinations. Include service-role/anon/API/PAT/hook/SSH/email/R2/storage/receipt/revalidation credentials and every holder. Never publish values or substitute a secret's name for its identity. |
| Vercel/UI | Exact project/deployment/source/domain and effective API/Supabase destinations; hooks and server functions, admin session roles and browser client routes. No direct database writer is inferred solely from Vercel's presence. Preserve separate authenticated UI acceptance. |

Keep external-effect transports fenced as well as database writes. Light ETL,
dry-run observations, source caching, receipts, revalidation, email and storage
must have explicit disposition. No production app requests belong in metadata
preflight: requests can wake startup, and dispatch/command GETs can commit
retirement in `admin_etl_dispatch.py`.

## Maintenance feasibility: unresolved hard prerequisite

The accepted `_maintenance` in `backend/seeding/reconciliation.py` requires
**actual** `rolsuper=true`, `datallowconn=false`, zero other target sessions
(including background writers) and zero prepared transactions. The retained
operator must connect before admission closes and keep its exact backend through
inspect/sign/plan/apply. Catalogs do not prove a direct path; a bounded historical
transaction-pooler continuity observation cannot certify it.

Supabase documents that its `postgres` role is not a true superuser. Network
restrictions cover direct/pooled PostgreSQL traffic but exclude HTTPS APIs.
These facts rule out treating an IP allowlist, idle census, role grant or
Auto-Deploy-OFF as the accepted sole-session fence. Provider background services
and admission while retaining the operator still need provider proof. No
supported provider equivalent is asserted. See [Supabase role
limits](https://supabase.com/docs/guides/database/postgres/roles-superuser) and
[network restrictions](https://supabase.com/docs/guides/platform/network-restrictions).

Before scheduling an outage, obtain a provider-assisted procedure that satisfies
the existing operator unchanged, or a separately reviewed operator design with
equivalent complete visibility, connection admission, background/session fencing,
same-transaction effect proof and lost-continuity retention. Do not remove the
superuser check in this lane or retry the known-incompatible apply command.
Direct connectivity uses a reviewed IPv6-capable route or actual IPv4 add-on;
session pooling is an available connection alternative, not certified equivalent
maintenance semantics. [Connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

Render's independent-job constraint is documented in [one-off
jobs](https://render.com/docs/one-off-jobs). Hook possession is a separate
deployment path; account for holders without exposing the URL. [Deploy
hooks](https://render.com/docs/deploy-hooks).

## Ordered release steps for separate coordinator authorization

1. Freeze the reviewed baseline release source/tree, per-file corpus and installed
   image/runtime/configuration. Read the exact Lane E contract/hash/head into the
   coordinator packet, retaining separate targets. Resolve every unknown above
   and maintenance feasibility before proposing an outage. GitHub head-upgrade
   workflows stay fenced throughout this baseline phase.
2. Approve backup/recovery scope and custody. Capture an authorized current backup
   with source cluster/OID/revision/time and immutable hashes; independently
   restore to an owned isolated target with transports fenced. Compare actual
   rows/sequences, complete schema/triggers/functions/constraints/indexes,
   roles/effective grants/RLS/policies and application compatibility. Include
   Storage object bytes, queues, email/publisher receipts and external effects;
   database backups do not include Storage object bytes. Agree RPO/RTO and exact
   restore/rollback decision owners using the actual provider plan. [Backup
   limits](https://supabase.com/docs/guides/platform/backups).
3. Under the reviewed concrete maintenance action, stop/fence every host, runner,
   API, scheduler, native/manual/legacy worker, orphan and provider/external
   channel. Verify no launch/restart/reconnect can bypass the fence. Read back
   complete actual process/job/credential/session identities. Keep independent
   operators' signed scope evidence separate from developer assertions.
4. Obtain a fresh explicit `BEGIN READ ONLY` observation using the accepted TLS
   observer and independently verified endpoint. Require one current baseline
   revision and actual schema. Generate its exact pending suffix to e602b11a0001
   with `batch12_rollout.py`; never stamp or infer equivalence. Historical
   ea1645a4c0b5 requires eleven steps through c415a10d2026, f38c61a9d203,
   c96d13e2f411, a42b86e1d310, b73e19a4f602, d8f4a619b203, e554d7c9a001,
   e572b8c9a001, e583b9c9a001, e554b10a0001, e602b11a0001; this list is conditional
   on a new observation of that revision. Bind each file's accepted hash.
5. While all untrusted writers are fenced, admit only the reviewed migration
   client, apply the explicit target transactionally and verify revision/schema
   and preserved claims/observations. Alembic opens a fresh NullPool connection;
   perform this before closing final operator admission. Close the migration
   client. No a611b12a0001 change belongs here.
6. Open the retained direct operator and establish the independently authorized
   final database-admission/background-maintenance fence. Verify its actual
   privilege, PID/database/cluster/revision, zero other target sessions/prepared
   work and provider admission certificate. Keep all restart/transport fences.
7. Inspect exact claims, dispatch command/domain/worker state and legacy RUNNING
   observation IDs. Investigate exact financial/source-document/artifact/external
   effects using the real provenance chain; unknown effects remain retained.
   Independently provision policy/hash/keys outside the request. Sign distinct
   who/when/why/context/effects artifacts; make and apply one exact plan on the
   same backend. Record durable changes and preserved original metadata/errors;
   reconciliation is not fabricated runner completion. Loss/ambiguous commit
   requires durable investigation before any new plan, never automatic retry.
8. End reconciliation and review its complete durable readback. Deploy only the
   reviewed baseline-compatible backend image under explicit authorization;
   startup itself is a writer, so fence release and service start are one
   ordered reviewed action after retained effects are accounted for. Keep
   dedicated dispatch/CRA/social/provider/publisher activation separately held.
9. Execute authenticated deployed acceptance with the real identity provider and
   intended Vercel/API/operator hosts. Separately authorize bounded real or inert
   deployed effect controls. Record admin/nonadmin/expired auth, default-off
   unavailable behavior, one-use intent/idempotent replay/stale generation, exact
   command/job/claim/audit actor/action/target correlation, actual child custody
   and normal/dry-run/failure/interruption receipts. Verify UI disabled/loading/
   error/empty/malformed/history/mobile/keyboard flows and every intended route.
   A deploy badge, 202 or worker heartbeat cannot prove completed work. Deployed
   lifespan/JWKS/profiles/installed runtime/real ingestion differ from local seams.
10. Review final acceptance and explicitly authorize bounded activation/fence
    release per channel. Enable only reviewed supported mappings and schedules;
    CRA remains default-off and OpenData #621/#602 remains unsupported until its
    own disposition. Only after separate coordinator acceptance may Lane E's
    exact audit migration/custody/incarnation/roles/readers run as another step.

## Operator abort and recovery

Abort before the next write on identity/source/target drift; missing/expired
scope evidence; unaccounted credentials/jobs/processes/sessions/prepared work;
admission reopen/restart; lost retained backend; unknown effects; stale context;
schema/row/constraint mismatch; invalid signature; ambiguous commit; incomplete
backup/restore; or failed deployed auth/correlation. Hold every fence, preserve
raw failures and original durable ownership, and checkpoint the last completed
step. Do not rerun an uncertain apply or release based on age or idle state.

Generic downgrade is not recovery: reconciliation/history downgrades deliberately
refuse weakening. Prefer a separately reviewed schema-compatible application
rollback while preserving evidence. Restore/PITR/clone/promotion changes custody;
withhold audit certification and invalidate/rotate external incarnation according
to Lane E's accepted contract before any audit-reader admission. Production
restore, data-loss decisions, credentials and fence release need their own exact
reviewed step. Preserve the original database and account for external effects
that a database restore cannot reverse.
