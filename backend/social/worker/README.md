# Durable publishing worker (batch one)

The worker is a separate explicit process. No web/ETL lifespan imports it, no `.env` is read, no operational rows are seeded, and no provider adapters are registered by the CLI. Accounts, controls and provider implementations remain unavailable until their separately authorized setup. A missing adapter produces `ADAPTER_NOT_AVAILABLE`; it cannot produce a successful publication.

```sh
PYTHONPATH="$PWD/backend" python -m social.worker --database-url "$EXPLICIT_SOCIAL_DATABASE_URL"
```

Supply the database configuration explicitly. Publishing controls default off in the domain schema. `--once` performs one bounded scan and drains that scan's operations. SIGTERM/SIGINT stop new claims and drain bounded active calls. A killed or cancelled public call leaves durable intent for later reconciliation.

The runtime uses two external slots, one persisted mutating admission per account, two database connections without overflow, and two database executor threads. Each database operation owns its short connection/transaction; none spans an external await. Defaults are 5-second active scans, 30-second idle scans, 15/60-second active/idle heartbeat, 120-second leases renewed every 20 seconds. Known future due times shorten the scan wait. Empty claims return no payloads. Due claims select minimal identifiers through the partial due index and `SKIP LOCKED` before payload loading.

Every operation has an intent. Public intents use `outcome=intent`, `cost_reservation_state=not_required`, a dispatch timestamp and token/epoch fencing. Controls/account/publication/target locks always follow that order. Claim-only audit rows retain target FK and account/publication IDs in details, with nullable account/post FKs, avoiding backwards FK locks while remaining atomic with the claim. A claim cannot start a second unresolved operation. Each mutation rehashes the authorized revision and re-resolves its exact selected account, content, media/accessibility and evidence in that transaction; a self-consistent target hash alone cannot authorize different content. Only that destination is revalidated, preserving independent platform outcomes. Adapter execution explicitly receives the immutable payload: `execute(payload, operation, credential, media_access)`. An adapter must expose each upload/container/finalize/publication/status boundary; `OperationPlan.checkpoint` is its exact durable checkpoint input. Successful non-public operations save their checkpoint and continue without incrementing public submissions or declaring publication.

A public result requires a positive confirmed-success outcome, public visibility, primary remote identity and confirmation kind. Raw provider receipts are discarded; attempts retain compact typed IDs/checkpoints/visibility/confirmation and `retry_safe`, required by the API's audited retry command. Public submissions are capped at five and 24 hours, shortened by approved deadlines/freshness. Provider delays are never shortened. Read-only checks have an independent 100-operation/24-hour bound and do not consume public submissions.

Global/platform pause keeps the same authorized checkpoint queued with a 30-second due time. Resume checks current controls and deadlines again; work that has become stale is blocked. Status/reconciliation reads continue while paused. Cancellation or pause before the permit prevents mutation; a committed permit may already be in flight and later confirmation remains authoritative.

Expired possible mutations enter reconciliation and persist an account hold. Expired admission is not proof an HTTP request stopped, so another target cannot reuse it before recovery. An expired worker can append its late receipt to its own attempt, but cannot overwrite current target state. Reconciliation receives the latest mutation's evidence, including late evidence, rather than losing it behind a newer read attempt. An unknown result remains `outcome_unknown`, never automatically resent. Only confirmed publication or definitive evidence of no publication clears that target's account hold.

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
