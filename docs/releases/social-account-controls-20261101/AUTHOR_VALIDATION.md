# Local account publishing controls

This feature supplies explicit per-account manual publishing consent. The account command does not enable global publishing, automation, uploads or a worker and performs no provider request. All receipts below use synthetic accounts, grants, storage and adapters. They do not authorize production activation or establish provider delivery.

The implementation adds metadata-only readiness and a receipt-backed PATCH at `/api/v1/admin/social/accounts/{account_id}/publishing`. Global controls serialize the mutation; their existing monotonic version and an account/credential state digest reject stale intent and ABA toggles. Connected native admission and current credentials are required to enable. Pausing preserves unresolved leases and holds and remains possible with unhealthy credentials. Both existing account-card families use the same explicit control, pending/error states and session-epoch fences. An ambiguous command retains its exact body and idempotency key for explicit retry.

The Page-material fix follows the existing Page/User lifetime decision: Page access expiry remains authoritative for the Page token. Parent User access expiry requires discovery reconnection; both data-access expiries, revocation, refresh ownership and account/grant identity checks remain enforced. Production access expiries were not inspected by these tests.

## Author-stage receipts

`AUTHOR_SOURCE.json` binds this **uncommitted author-stage** source and the raw logs. Independent review or subsequent fixes may supersede these source hashes; the file does not claim to bind a future commit or final review. Its baseline is `9bbdde51d6ebe9e38bf0aa86f4d0f086c5cdffeb`.

| Receipt | Observed result |
| --- | --- |
| `red-account-api-baseline.txt` | New mounted regression with only `api.py` overlaid from baseline Git blob: HTTP 404 instead of 200. |
| `red-parent-access-baseline.txt` | New material regression with only `worker/materials.py` overlaid from baseline Git blob: `CREDENTIAL_EXPIRED` despite valid Page access and expired parent User access. |
| `author-backend.txt` | 58 passed, zero skips: account command/API, mounted media/review/queue, full credential-material boundary. |
| `author-ui.txt` | 12 passed: explicit enable/pause, blocked enable with available safety pause, retained retry key/body, late prior-session response, malformed readiness. |
| `author-runtime.txt` | Actual production package subset plus existing vetted test overlay; no installations. |
| `author-typescript.txt` | Historical author-stage exit 2 on five unchanged existing Testing Library `exact` options in three prior workflow tests; no new source errors. Parent owns the separate cleanup and final typecheck receipt. |

The broader author Jest run also completed 835 tests / 58 suites across `__tests__/social-connections` and `__tests__/admin/social` (observed tool output, not a retained raw log). The development-stage after-update trigger regression was observed failing (`DID NOT RAISE SocialError`), then passed after durable account/control readback before receipt. There is no immutable pre-fix source capture for that intermediate stage; no commit identity is claimed for it.

## Exact execution setup

The backend receipts use Docker image `pr863-python-patch-parity:local`, `--network none --read-only --tmpfs /tmp:rw`, the feature checkout read-only at `/app`, and the existing `security-final-866-867-20261101/python-author` directory read-only at `/evidence`. The interpreter is `/evidence/docker-prod-test-env/bin/python`; `PYTHONPATH=/app/backend:/app/backend/tests/social`; working directory `/app`.

```sh
/evidence/docker-prod-test-env/bin/python -m pytest \
  --confcutdir=backend/tests/social \
  backend/tests/social/test_account_publishing.py \
  backend/tests/social/test_manual_media_workflow.py \
  backend/tests/social/test_worker_materials.py -q -p no:cacheprovider --tb=short
```

For each baseline red receipt, `git show 9bbdde51d6ebe9e38bf0aa86f4d0f086c5cdffeb:<path>` was written to a temporary file and mounted over just that source file. The current regression test was selected individually. The original worktree files were not changed. The baseline blob SHA-256 values are retained in `AUTHOR_SOURCE.json`.

Frontend commands use the cached Node 24.22.1 binary and existing dependency-worktree `node_modules`, with no dependency install or lock changes:

```sh
node node_modules/jest/bin/jest.js --runInBand --no-cache \
  __tests__/social-connections/account-publishing.test.tsx
node node_modules/jest/bin/jest.js --runInBand --no-cache \
  __tests__/social-connections __tests__/admin/social
node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
```

These author checks use SQLite for the mounted APIs. They do not prove PostgreSQL lock contention, production DB permissions, a live worker, provider acceptance, storage custody, restore/retention/capacity acceptance or ingress privacy resolution. Independent review and any PostgreSQL receipts are recorded separately. The activation sequence and remaining operator evidence belong to `docs/social-publishing/manual-publication-activation.md`.


## Review fixes and superseding receipts

The author-stage source above was superseded by independently reproduced fixes. Final command verification now runs after deferred constraint effects **and** exact durable receipt verification, before commit. The setter registers a mandatory trusted postcondition in the normal `SocialService.command` lifecycle, covering ordinary internal callers and HTTP. It compares the complete returned account-state witness and the exact durable audit event, so a deferred account/receipt trigger cannot change consent, controls or credentials while leaving a positive response. The lifecycle clears registered checks after success, replay or failure. Existing command behavior otherwise remains unchanged.

The shared TikTok capability context now treats non-object persisted JSON as unapproved. Five observed-red null/list/bool/integer/string cases now return blocked native eligibility while permitting the explicit safety pause. Numeric native eligibility was **not** a product defect: the initial reviewer/author fixture used Python JSON equality (`True == 1`) and SQLAlchemy skipped the dirty write. The preserved `red-numeric-native-proof.txt` is an invalid-finding historical receipt; the corrected fixture forces persistence, verifies the stored integer type and observes the existing strict native proof reject it. `native_admission.py` was not changed.

The UI now rejects non-incrementing/unrelated command versions, unchanged state witnesses, and a global-off response lacking its corresponding hold. A synchronous in-flight ref prevents batched overlapping reads from overwriting a newer readiness verdict. `red-ui-receipt-witness.txt` records four failures and `red-ui-overlap.txt` one failure before those fixes; `author-ui-after-review.txt` records 17 passes after them. `red-audit-suppression.txt` records the missing audit witness before its fix. `red-malformed-safety-pause.txt` records all five malformed TikTok failures before the shared context guard.

`author-backend-after-review.txt` is an intermediate 191-pass receipt before the final audit/TikTok fixes. `author-backend-final.txt` supersedes it: 203 passed, zero skips, covering the three initial modules plus native capability admission, native Meta adapters and existing admin API tests. `author-backend-final-optimized.txt` records the same selection under `python -O` separately. Independent PostgreSQL/concurrency and actual API-wrapper UI reviews are separate receipts; these local tests do not replace them. Final scoped source bindings and independent results are indexed separately from `AUTHOR_SOURCE.json`.
