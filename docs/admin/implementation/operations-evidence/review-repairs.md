# PR #560 review regression receipts

Baseline delivery: `ac493422f1aa5138e5469f1ed7f67bdf3837cdb2`.
Complete review: two inline findings, plus authentication diagnostics and source
membership hypotheses in the review body. Both body-only concerns are valid.
The additional date defect was independently reproduced by the coordinator's
Spec reviewer. Raw logs are retained in the coordinator's `BATCH_6_REVIEW/560`
artifact; the committed tests below are portable reproductions.

## Executed commands

Run backend from the repository root, using this worktree and read-only runtime:

```sh
operations_tree=/Users/roger/.codex/worktrees/admin-operations-batch6/audit_app
operations_python=/Users/roger/Documents/projects/audit_app/venv/bin/python
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH="$operations_tree/backend" \
  DATABASE_URL=sqlite:////tmp/batch6-operations-review-bootstrap.sqlite \
  "$operations_python" -m pytest \
  backend/tests/test_admin_operations_review_regressions.py -q
```

Before repair, observed **25 failed, 2 warnings in 0.86s**. The packaging case
executed real mounted endpoints in a fresh backend-only directory and failed
because calendar reads returned unavailable. Eight cases executed actual JWT
unknown-key handling with an inert key identifier and synthetic JWKS. Sixteen
cases supplied hostile dependency diagnostics for 401/403 across all routes.
The final suite adds a repository import/direct-script compatibility control.

Final backend replay adds the following existing files to that command:

```text
backend/tests/test_admin_operations_lane.py
backend/tests/test_admin_operations_adversarial.py
backend/tests/test_etl_admin_endpoints.py
backend/tests/test_web_ingestion_ownership.py
backend/tests/test_ingestion_query_transfer.py
```

Observed: **160 passed, 2 warnings in 2.76s**. Both warnings are the preexisting
SQLAlchemy `declarative_base()` deprecations in shared database/model files.

Run frontend commands from `frontend`:

```sh
operations_node=/Users/roger/.nvm/versions/node/v22.19.0/bin/node
operations_node_path=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin:/usr/local/bin
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 "$operations_node" \
  node_modules/jest/bin/jest.js --runInBand \
  __tests__/admin/operations/etl-review-regressions.test.ts
```

Before source-set/membership repair: **16 failed, 7 passed, 23 total**. Six
five-source omissions and six one-source plans were accepted; four inherited
skipped-source names were accepted. Valid complete, invalid planned memberships
and duplicate membership controls passed. After adding the independent date
cases but before repairing dates: **8 failed, 33 passed, 41 total**. Nonexistent
Gregorian dates, 24:00, year zero and unsupported minute-only timestamps passed
the old guard; other invalid clocks/offsets and valid date controls passed.

Final full Operations frontend replay substitutes `__tests__/admin/operations`
for the test path: **3 suites, 79 passed, 0.803s**. Updated existing rendered
fixtures contain all six sources, with all twelve dispatch controls disabled.

```sh
env -i PATH="$operations_node_path" NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 \
  "$operations_node" node_modules/typescript/bin/tsc --noEmit
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 "$operations_node" \
  node_modules/next/dist/bin/next lint --file app/admin/etl/page.tsx \
  --file app/admin/ingestion/page.tsx --file 'app/admin/ingestion/[jobId]/page.tsx' \
  --file lib/admin/ingestion.ts --file lib/admin/ingestionPolling.ts \
  --file lib/admin/etl.ts --max-warnings=0
```

TypeScript: exit 0, no output. Lint: `No ESLint warnings or errors`; only the
existing Next CLI deprecation notice. No install, lockfile edit or deployment.

## Invariant and caller coverage

- Planner packaging: admin schedule, summary, single-source schedule and health
  all call `_calendar_plan` through the same loader. Fresh backend-only replay
  covers all four; package precedence remains backend `etl` and `seeding`.
  Root `etl/kenya_pipeline.py`, `test_knbs_e2e.py` and `test_smart_scheduler.py`
  import the root compatibility entry point. The public class/helper and direct
  CLI are executed by the retained compatibility test. The canonical source
  bytes are unchanged; financial/source/seeding behavior is not modified.
- Response membership: `frontend/app/admin/etl/page.tsx` consumes only
  `parseSchedule`. Full key-set validation covers every decision, and explicit
  allowlist membership protects both planned and skipped summary collections.
  Retained valid/partial/duplicate/unknown/prototype-name cases test the boundary.
- Authentication privacy: both mounted `admin.router` and `etl_admin.router`
  use `OperationsRoute`. Eight routes receive actual JWT unknown-key errors and
  hostile 401/403 dependency errors. Existing 5xx and unaccepted dispatch
  controls pass. Shared auth source and other routers remain separately owned.
- Dates: `parseSchedule` validates plan timestamp and each `next_run`;
  `parseEtlHealth` validates its timestamp; `parseIngestionJob` validates start,
  finish, creation and optional metadata `since`; `parseIngestionList` delegates
  each row to `parseIngestionJob`. The shared parser is exercised at each entry
  with the same hostile timestamps, plus leap/fraction/offset/naive controls.

Worker dispatch #554 remains unavailable. Cross-lane integration, final browser
and image/deployed acceptance are coordinator work. Existing #556/#557 cover
response validation and dates; authentication diagnostics are tracked in
[#564](https://github.com/Rodgers31/audit_app/issues/564). Missing production
packaging was reported to the coordinator for deduplicated issue tracking.
