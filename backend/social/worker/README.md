# Durable publishing worker (batch one)

The worker is a separate explicit process. No web/ETL lifespan imports it, no `.env` is read, no operational rows are seeded, and native provider adapters require explicit opt-in plus restricted-role verification. Accounts, controls and provider implementations remain unavailable until their separately authorized setup. A missing adapter produces `ADAPTER_NOT_AVAILABLE`; it cannot produce a successful publication.

```sh
PYTHONPATH="$PWD/backend" python -m social.worker --database-url "$EXPLICIT_SOCIAL_DATABASE_URL"
```

Supply the database configuration explicitly with `postgresql://` or `postgresql+psycopg2://`; both use the synchronous psycopg2 driver. Other drivers, including async drivers, are rejected during configuration. Publishing controls default off in the domain schema. `--once` performs one bounded scan and drains that scan's operations. SIGTERM/SIGINT stop new claims and drain bounded active calls. A killed or cancelled public call leaves durable intent for later reconciliation.

The runtime uses two external slots, one persisted mutating admission per account, two database connections without overflow, and two database executor threads. Each database operation owns its short connection/transaction; none spans an external await. Defaults are 5-second active scans, 30-second idle scans, 15/60-second active/idle heartbeat, 120-second leases renewed every 20 seconds. Known future due times shorten the scan wait. Empty claims return no payloads. Due claims select minimal identifiers through the partial due index and `SKIP LOCKED` before payload loading.

Every operation has an intent. Public intents use `outcome=intent`, `cost_reservation_state=not_required`, a dispatch timestamp and token/epoch fencing. Controls/account/publication/target locks always follow that order. Claim-only audit rows retain target FK and account/publication IDs in details, with nullable account/post FKs, avoiding backwards FK locks while remaining atomic with the claim. A claim cannot start a second unresolved operation. Each mutation rehashes the authorized revision and re-resolves its exact selected account, content, media/accessibility and evidence in that transaction; a self-consistent target hash alone cannot authorize different content. Only that destination is revalidated, preserving independent platform outcomes. Adapter execution explicitly receives the immutable payload: `execute(payload, operation, credential, media_access)`. An adapter must expose each upload/container/finalize/publication/status boundary; `OperationPlan.checkpoint` is its exact durable checkpoint input. Successful non-public operations save their checkpoint and continue without incrementing public submissions or declaring publication.

A public result requires a positive confirmed-success outcome, public visibility, primary remote identity and confirmation kind. Raw provider receipts are discarded; attempts retain compact typed IDs/checkpoints/visibility/confirmation and `retry_safe`, required by the API's audited retry command. Public submissions are capped at five and 24 hours, shortened by approved deadlines/freshness. Provider delays are never shortened. Read-only checks have an independent rolling 100-read/24-hour budget and do not consume public submissions. The locked permit counts poll/reconcile intents within that window, including lost results; mutation and older history do not consume it. Exhaustion preserves processing/reconciliation, the checkpoint and account hold, schedules the next check when a budget slot expires, and makes no provider call. Reconciliation can recover after the public retry deadline; that recovery never extends permission to resubmit.

Global/platform pause keeps the same authorized checkpoint queued with a 30-second due time. Resume checks current controls and deadlines again; work that has become stale is blocked. Status/reconciliation reads continue while paused. Cancellation or pause before the permit prevents mutation; a committed permit may already be in flight and later confirmation remains authoritative.

Expired possible mutations enter reconciliation and persist an account hold. Expired admission is not proof an HTTP request stopped, so another target cannot reuse it before recovery. An expired worker can append its late receipt to its own attempt, but cannot overwrite current target state. Reconciliation receives the latest mutation's evidence, including late evidence, rather than losing it behind a newer read attempt. An unknown result remains `outcome_unknown`, never automatically resent. Only confirmed publication or a typed `DefinitiveAbsenceProof` clears that target's account hold. Absence proof must name the original mutating operation and selected account, use `provider_definitive_status` or `confirmed_not_sent`, and affirm verified complete coverage. Generic evidence, empty lookups, false/incomplete proof and mismatched identities remain `outcome_unknown` and retain the hold. Malformed proofs complete the read attempt as unknown rather than leaving an unfinished read intent.

Paid budget reservation and credential refresh are intentionally unavailable in this batch; paid/unverified capabilities and any charged operation are blocked. Later real adapters need reviewed credential/media ports and accounting, rather than a fallback from these controls.

## Local verification

Use the dedicated disposable local database named **social_worker_test**, on localhost only. The test harness rejects other database names and remote hosts. It creates only the domain's social tables and truncates those fixture tables between tests. It never imports `backend.main` or `backend.database`, migrates production or contacts a platform. Constructed fake adapters exist only in test code.

```sh
SOCIAL_WORKER_TEST_DATABASE_URL="$EXPLICIT_LOCAL_TEST_DSN" \
PYTHONPATH="$PWD/backend" python -m pytest \
  --confcutdir=backend/tests/social \
  backend/tests/social/test_worker_config.py \
  backend/tests/social/test_worker_policy.py \
  backend/tests/social/test_queue_postgres.py -q
```

`--confcutdir` avoids the existing root backend conftest's web/auth/database startup. Without an explicit test DSN, PostgreSQL tests skip truthfully. Tests execute independent worker claims, skip-locked rows, token/epoch fencing, lock ordering, account admission and expired-admission races, control-lock expiry, database failure before/after permit, upload checkpoints, processing while paused, bounded retries, independent results, malformed JSON, direct guard bypass attempts, and an actual SIGKILL after a fake remote receipt is fsynced. A fresh worker reconciles that receipt without executing a second public operation.


## Restricted native worker login

Native CLI startup now requires `--worker-role` and verifies the actual database
login **before** constructing a queue repository or provider runtime. Plain
non-native scans retain their existing behavior. This does not start a scheduled
process or enable any publishing/upload setting, and does not change the API's
separate database identity.

The reviewed contract in `role_contract.py` allows SELECT on nine named worker
tables, exact column INSERT/UPDATE grants for queue progress, attempts,
heartbeats and worker audit events, and lock-only UPDATE(id) on controls,
publications and credentials. Restrictive RLS policies prevent a permissive
PUBLIC policy from enabling writes to lock-only rows or completed attempts.
The worker cannot alter account publishing permissions, approved payloads,
credential ciphertext, media objects, OAuth flows or privacy records, and cannot
DELETE, TRUNCATE or grant privileges. Reading encrypted credentials is necessary
for native dispatch; key custody and operating-system isolation are separate.

An operator must separately approve and create a dedicated LOGIN role with
NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOINHERIT and
CONNECTION LIMIT 2, without other memberships, ownership of any object (in any
database, as recorded in `pg_shdepend`) or login defaults (`ALTER ROLE ... SET`). Credential creation/storage is outside these tools.
Installation refuses existing excess access instead of silently revoking it;
unexpected PUBLIC grants, policies or accessible SECURITY DEFINER routines may
need a separate reviewed remediation. No role, grant or policy is created at
import, API startup or migration.

Both installation and verification inventory authority outside the worker
tables as well: every relation and column in every non-temporary schema
(PostgreSQL 17 MAINTAIN included), with catalog access limited to initdb's
PUBLIC grants recorded in `pg_init_privs` plus information_schema's public views;
catalog routines initdb withholds from PUBLIC; any accessible SECURITY DEFINER
routine; parameter ACL rows (pg_settings hides superuser-only parameters from
the worker); large-object, foreign-data-wrapper, foreign-server and user-mapping
access; and login defaults, since `SET LOCAL ROLE` never applies them. A
database-wide default may set only built-in user-context parameters or custom
placeholders outside every installed extension's prefix; extension settings
(such as `plpgsql.*`, which changes how the guard functions resolve names) are
refused. The checks resolve functions in `pg_catalog` first, so a user-schema
object cannot stand in for a builtin. The five guard triggers must fire on every UPDATE (no column
list), and the worker tables must carry no rewrite rules, whose actions run as
the table owner.

After that separately authorized setup, use named environment references so
connection secrets do not enter process arguments or shell history:

```sh
PYTHONPATH="$PWD/backend" python -m social.worker.role_admin \
  --database-url-env SOCIAL_ROLE_OPERATOR_DSN --role audit_social_worker --install
PYTHONPATH="$PWD/backend" python -m social.worker.role_admin \
  --database-url-env SOCIAL_WORKER_DATABASE_URL --role audit_social_worker --verify
PYTHONPATH="$PWD/backend" python -m social.worker \
  --database-url-env SOCIAL_WORKER_DATABASE_URL --worker-role audit_social_worker \
  --native-meta --once
```

These are operator examples, not activation approval. The installer only grants
the exact contract to an existing login in one atomic transaction; it creates no
credential, table, database, default ACL, PUBLIC privilege or operational row.
Verification requires the existing controls singleton, matching RLS policies and
exact effective privileges, including column grants and inherited PUBLIC access.
A privileged operator session cannot pass runtime login verification. Both
commands emit fixed diagnostics without SQL, DSNs or row data, including on
Ctrl-C (exit 130). The native worker also requires its existing separate
native/media operational gates. Configure `--schema` for the operator or
`--database-schema` for a worker only for a trusted schema. With `--worker-role`
(default schema `public`) or an explicit `--database-schema`, every physical
worker connection pins `pg_catalog,<schema>,pg_temp`: builtins keep precedence and
an untrusted temporary table cannot replace a worker relation. Without either,
and for media maintenance, the DSN/login search path is unchanged.

This is a startup snapshot of SQL authority, not ongoing delivery ownership,
credential backup/restore proof or a defense against a compromised host that can
read the API's environment. A database owner can still change grants/policies;
reverify after any such change and before activation. No production restricted
login is provisioned by this code release.

The additional local lane uses `SOCIAL_ROLE_TEST_DATABASE_URL` pointing only to
`social_domain_test` on loopback port 62124. Its fixtures create/drop uniquely
named schemas and inert roles in that disposable database. Tests exercise the
actual migrated schema and complete native text/image pipelines with inert
HTTP/storage, forbidden SQL mutations, RLS drift and atomic refusal. Where an
outside-table widening grants usable authority, its test first proves it through
the actual worker login (absent before, present after); every widening then
requires the verifier, the installer and the native CLI to refuse. Temporary
catalog, parameter, large-object and foreign-server widenings are restored in
`finally`.
