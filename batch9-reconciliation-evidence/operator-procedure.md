# Reconciliation operator procedure — local candidate, production use gated

Issue [#583](https://github.com/Rodgers31/audit_app/issues/583), dependent on
[#584](https://github.com/Rodgers31/audit_app/pull/584) at
`9e97ca3f1ca43f103a8655447a86d889456a218a`. No production mutation or author
production inspection occurred. The coordinator owns deployment facts and
authorization for any real outage, fencing, migration or reconciliation.

## What this procedure proves and requires

The tool is a conservative **whole-database maintenance operation** on a retained,
independently certified **direct** PostgreSQL connection. It requires superuser
visibility/privilege, database admission already disabled (`datallowconn=false`),
no other target-database backends of any type and no prepared transactions.
It does not change admission settings, disable roles, stop services, terminate
connections, activate dispatch or release anything on a timer.

These requirements are locally proved on direct PostgreSQL16. They are **not
certified feasible on the actual Supabase service**: its `postgres` account may
lack required superuser/catalog privileges and database admission control.
Do not supply a pooler URL merely because the environment variable says DIRECT.
A pre-existing pooler backend can serve new client jobs without opening a new
database backend. The provider/direct-path facts, pooler-client admission fence,
and ability to retain the maintenance connection must be independently certified.
If any requirement is unavailable, the tool remains unavailable; there is no
generic unlocked or reduced-visibility fallback. A provider-assisted, separately
reviewed mechanism would be required before an actual operation.

Database observations prove only their observed database state and transaction
fences. A signature authenticates an authorized host/scheduler operator's
statement; it does **not** make a false statement true, discover an omitted host,
prove an OS process dead or prove no external work can resume. The coordinator
must approve an exhaustive deployment inventory and separately provision trusted
policy keys. Unknown hosts, incomplete process groups, stale/reused PIDs, lost
backends, elapsed lease age, and unverifiable effects remain uncertainty.

## Writer and launcher inventory

The original `writer-census.json` is a historical subset scan, superseded for
current coverage by `writer-census-review.json`. The generator examines tracked
Python/YAML in `backend`, `etl`, `scripts` and `.github/workflows`, excluding
tests and `__pycache__`, plus root `docker-compose*.yml` files. It records exact
selected hashes and a complete list of tracked files omitted from that scan.
It is **not whole-repository writer coverage**. Before provisioning trusted
policy, independent operators must review every omitted scope for writers and
launch configuration, including `admin`, `infra`, `frontend`, Dockerfiles,
shell scripts and other configuration formats, and retain that separate source
inventory. Untracked deployment configuration must also be inspected on each
host. Source candidates are evidence for investigation, not a claim that
all deployed hosts are known. `batch8-exclusion-evidence/writer-inventory.md`
supplies the earlier reviewed semantics. The following categories must be
attested by **every configured host and scheduler scope**, including explicit
absent/not-deployed findings with their discovery source. Admission is fenced
for the entire database, so shared reference tables and application writes are
included even when only one seeding domain is reconciled.

| Signed category | Writers and what operators must inspect |
|---|---|
| `native_scheduled` | `.github/workflows/seed.yml` nightly/weekly `seeding.cli seed --all/--domain`, workflow runs/retries/manual dispatch, self-hosted or hosted job status and active runner work. Disable new launches and drain existing runs; a disabled workflow alone does not stop a running job. |
| `native_manual` | Every shell/manual call of `run_seed_command` or `python -m seeding.cli`; process groups and descendant processes on all hosts. |
| `dedicated_supervisor` | `admin_etl_dispatch_worker`: stop the actual supervisor and heartbeat, drain commands. A lease deadline is never stopped-process evidence. `ready=false` is an additional DB requirement, not host proof. |
| `dedicated_adapter_orphans` | Actual `admin_etl_dispatch_adapter` and native child/descendants, including groups whose supervisor died. Enumerate command line, PID **and process birth identity**, parent/group/container/job identity and target; prove complete groups stopped, not one PID absent. |
| `legacy_etl` | #581: `etl.worker` threads/subprocess `etl.backfill`, `etl.scheduler`, `KenyaDataPipeline` and `DatabaseLoader`; compose `etl` services, sample/manual `etl/seed_*.py` callers. Writes audits plus shared countries/entities/periods/documents/budgets/population/GDP/indicators. Include the #581 delivery when integrated; it remains a writer that must be stopped even when ownership coverage improves. |
| `bootstrap` | #582: web boot and weekly `initialize_reference_data`, direct national_budget handler and shared reference writes. Hold web restarts, deploy/restart hooks and bootstrap jobs. Include the #582 delivery when integrated; claim coverage never substitutes for quiescence. |
| `application_auto_seeder` | `backend/services/auto_seeder.py` reference-entity commits. Stop the owning application process, not only the seeding handler. |
| `application_sessions` | All backend services, ordinary authenticated/public application APIs, admin operations, social workers, SQL editors, service-role clients, subscriptions/background jobs and integrations against the target. `routers/user_features.py` writes bookmarks/newsletter rows; they also make a whole-DB outage relevant. Supabase/provider built-in, bypass-capable and owner roles need provider assessment. No exemption for using the operator's credentials. |
| `parliament` | Parliament scheduled orchestration, pipeline ingestion and manual backfill; writes shared source documents and Parliament tables. Default flags do not certify deployed absence. |
| `migrations_manual_scripts` | All migration/deploy Jobs and manual repair/verification scripts, including `normalize_fiscal_periods.py`, `cleanup_stale_bootstrap_loans.py`, `oag_boundary_correction.py`, one-time audit publication backfill, and arbitrary direct SQL. Freeze credentials/use, scheduled retries and independent operator activity. |

Registered native domains at the pinned tree: audits, counties_budget,
county_officials, national_debt, national_budget, imf_weo, debt_timeline,
learning_hub, economic_indicators, fiscal_summary, population, revenue_by_source,
pending_bills, stalled_projects and national_gdp. Each handler and its imported
writers is included by the native categories. Direct invocation of any handler
is a manual writer, including imports outside the CLI. The tool fingerprints and
locks every public table rather than assuming domains have disjoint effects.
Non-public/external effects must also be reconciled in host/operator artifacts;
the public-table fingerprint alone cannot certify them.

## Pre-operation decisions and evidence

1. Record the actual target/project/cluster identity, deployed code/configuration,
   direct connection/provider mode, migration revision and responsible operators.
   Run `read_only_census.sql` only under independent read-only authorization and
   verify `transaction_read_only=on` after explicit BEGIN. This also works before
   claim/dispatch tables exist. Sanitize outputs; retain source command/API,
   UTC observation time, target and generator/source hashes. Never infer pooler
   cutoffs from the server timeout alone or from ignored startup kwargs.
2. Enumerate all deployed hosts, containers, schedulers and credentials, including
   the Render backend's startup hooks and Actions runs. Freeze new launches and
   retries, ordinary application/provider clients and deployment/migration/manual
   entry. Inspect and stop complete process groups, child/orphan work and external
   operations. Include connection pools/reconnects and provider background writers.
   Independent operators record process birth identities, commands, target, job
   IDs, discovery coverage and stop/drain results. Any unknown scope refuses.
3. Approve a bounded **whole-database outage** and recovery plan. App readiness
   and health checks will fail when admission is disabled; hold auto-restarts and
   new deployments. The outage affects all writer roles, including provider and
   bypass-capable users. No author code assumes Vercel UI or a disabled workflow
   establishes backend quiescence. The tool does not perform this outage.
4. Provision a trusted policy **outside the submitted packet**: target fingerprint
   from `target_identity`, exact host/scheduler scope IDs with Ed25519 public keys,
   and authorized operator IDs/keys. At least one host and scheduler are required.
   Key provenance and complete scope discovery need coordinator approval. The
   policy file must be non-group/world-writable and its byte SHA256 independently
   pinned in deployment configuration. Do not generate a key/policy from incoming
   evidence. Local test keys are ephemeral fixtures and are never deployment keys.

## Operator session, inspect, sign, plan, apply

Open `python -m seeding.reconcile_operator` **before** closing database admission,
using deployment-provisioned `AUDIT_RECONCILIATION_DIRECT_DATABASE_URL`,
`AUDIT_RECONCILIATION_POLICY_PATH` and
`AUDIT_RECONCILIATION_POLICY_SHA256`. Do not put credentials in transcripts.
The session prints `connected` and waits for newline-delimited JSON requests.
It explicitly sets/verifies public schema and UTC; diagnostics explicitly BEGIN
READ ONLY and rollback. Retain this one physical connection. A restart or lost
backend invalidates its plan and cannot reconnect through closed admission.

Only an independently authorized operator/provider then closes target admission
from another database/control channel and drains all other target sessions.
Confirm no prepared transactions/background work, and explicit `ready=false`
for an existing dedicated-worker row after the real supervisor stopped. The
tool only verifies these observations; a write to `ready` is not stop proof.
Real fences remain held until explicit operator verification of durable outcomes;
they must **never automatically expire at an evidence timestamp**.

Select exactly one retained claim, or a sorted complete set of truly untagged
RUNNING legacy observation IDs for one domain:

```json
{"domain":"audits","claim_id":"<exact canonical UUID>","legacy_job_ids":[]}
{"domain":"national_budget","claim_id":null,"legacy_job_ids":[<exact integer IDs>]}
```

Submit `{"action":"inspect","selector":<selector>}`. The read-only inspection
returns the target and `context_sha256`, binding the exact owner/entry/return,
dispatch command/domain/worker generation, observations, schema revision, and
counts/SHA256 fingerprints of **all public tables**. No effect row contents are
exported by the effect census. Its limits are 1000 relevant observations/history,
100000 rows per table and 10s statement timeout; exceeding a limit refuses and
needs a separately reviewed procedure, never sampling or truncation as proof.

Now reconcile the exact committed effects against source/provenance records,
transaction outcomes, external/provider/storage work, ingestion counts and errors.
A DB fingerprint detects change; it does not decide whether a financial/source
effect is correct. Record meaningful who (1–64 chars), why (1–500), effects
summary (1–1500), and sanitized supporting artifacts. Fields containing only
Unicode whitespace (including tabs/newlines), NUL-containing text, and
oversize/wrong-shaped fields refuse. A maximum
65536 canonical JSON bytes bounds a packet/request/plan. Long Unicode durable
records are bounded at 4000 characters before release. Store the signed packet
and its artifacts in the operator's audited evidence archive.

Evidence schema (exact keys; no optional quiescence flag):

```text
version: 1
target: exact target_identity object including cluster system ID, DB OID/name,
        maintenance role and actual migration revision
selector: exact inspected selector
context_sha256: inspection's exact context SHA256
who / why / effects: bounded nonblank operator text
effects_artifact: SHA256 key of one supporting artifact
artifacts: { SHA256(canonical artifact):
             {source, observed_at (UTC), target, content (sanitized 1–12000 chars)} }
statements: [ {payload: {scope, target, observed_at, hold_until,
                 fence_release: "explicit_operator_after_durable_audit",
                 writers: {each category above: "stopped" or "absent"},
                 artifact: matching artifact SHA256}, signature: Ed25519 hex} ]
signature: authorized operator signature of entire evidence except signature
```

Canonical signing bytes are sorted JSON keys, compact separators, ASCII escapes,
no NaN/Infinity (`seeding.reconciliation.canonical`). Sign each scope with its
independently provisioned key, then sign the completed evidence with an authorized
operator key. Every configured scope and every writer category must be present;
`live`, `unknown`, omitted, stale, mismatched or unsigned evidence refuses. All
artifacts must be referenced and their hashes/time/target must match. Observations
must be at most five minutes old; hold_until lies within that freshness window.
That deadline invalidates **evidence**, never releases claims or host fences.

Submit `{"action":"plan","evidence":<signed packet>}`. Save and review its
returned plan; planning changes no ownership and rolls back its read-only
transaction. It verifies current effects equal the signed inspected context.
Independently review the plan's exact identity/correlation, effects decision,
original return evidence and RUNNING transitions. Do not resign older evidence
over a new plan without another exact effects investigation.

Only after independently authorized review submit the distinct request
`{"action":"apply","evidence":<same packet>,"plan":<reviewed plan>}` on the
same retained session. Apply row-locks the closed-admission `pg_database` row,
takes the existing transaction advisory domain key, freezes all public tables
NOWAIT, uses worker → domain → command → claim ordering, re-reads exact durable
state and all effects, and revalidates signatures/target/time inside that backend.
Admission re-opening, a new owner/generation, changed effects, live/uncertain
sessions, prepared work, an autocommit/lost backend or stale plan refuses.

One atomic commit appends `AdminAuditLog.action=seeding.reconcile`, releases only
the exact retained claim with truthful `released_at/reconciled_by/reconciliation`,
clears only its exact audits dispatch-domain correlation, interrupts its command
only if still running, and marks correlated RUNNING observations FAILED with
audited reconciliation metadata/error. Original acquired/entered/digest/returned
evidence, job IDs, original metadata/errors/counts and terminal observations are
preserved. No returned_at, job_id or normal runner return is invented. A genuine
FAILED boolean ownership_refused dispatch observation remains a refusal, never
a return; it can be included in exact operator reconciliation.

For pre-migration observations, no active claim/domain/command may conflict and
the exact complete truly untagged RUNNING set must match. Explicit null,
malformed/mismatched/released/other-owner tags require investigation and refuse
this legacy mode. Its audit and FAILED observations commit together, without
inventing claim history. This path runs before the new claim tables exist.

## Durable outcomes and restoration

`applied` is printed only after the committing lock-holding transaction succeeds.
Any connection/commit failure yields `uncertain`: do not retry apply, promise
retention, fabricate a return or restore writers. A killed operator/backend or
lost report requires reading the **durable audit, exact claim, dispatch rows and
observations** through an independently approved recovery connection/procedure.
An old plan cannot be applied on a new backend. Precommit interruptions roll back
all mutations; postcommit report loss may leave the complete audited release.
Those distinct outcomes have actual local controls, including source hashes.

Only the real operator, after inspecting durable atomic outcomes and external
effects, explicitly restores admission and host/scheduler/application services
in reviewed order. Keep dedicated dispatch default-off and OAG→audits-only.
Verify readiness and a valid subsequent domain run, then record its real receipt.
This author exercised only owned inert subsequent native and dedicated runs.

## Code merge versus actual operational acceptance

This packet can remove the missing-reviewed-operator-implementation code gate
holding #584 after coordinator review. It does **not** execute #583's production
census reconciliation, host quiescence, provider/pooler/direct-path certification,
real outage/restore or migration/activation. #583/#572/#554/#545 remain open.
The coordinator reports workflows individually disabled and Render pinned with
Auto-Deploy off; those facts are coordinator evidence, not author verification,
and code merge must be classified separately from rollout. Before any later
migration/activation, preserve the actual census and reconcile its exact legacy
IDs without using their age. Actual production facts and acceptance remain with
the coordinator; no production operation is authorized by this document.
