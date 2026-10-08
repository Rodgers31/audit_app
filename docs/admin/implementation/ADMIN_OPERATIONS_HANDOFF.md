# Admin Operations — Batch 6 handoff

Issue [#547](https://github.com/Rodgers31/audit_app/issues/547), parent
[#545](https://github.com/Rodgers31/audit_app/issues/545). Local Operations
implementation is reviewable; dedicated worker acceptance remains open in
[#554](https://github.com/Rodgers31/audit_app/issues/554). A calculated calendar
does not establish scheduler activity, execution, or financial data freshness.

## Checkout and scope

- Worktree: `/Users/roger/.codex/worktrees/admin-operations-batch6/audit_app`
- Branch: `codex/admin-operations-batch6`
- Pinned base: `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`
- Implementation reviewed at: `1f2fed01b7029864f2e42a527586971d71840e5b`
- Final source repairs reviewed at: `9a593f3b565fb6d1f23008809359e3b8c7519861`;
  the final delivery commit adds the executed browser controls and this evidence.
- Final revision: the commit containing this handoff, resolved with
  `git rev-parse HEAD`; its full identity is included in the final chat brief.
- Scope: ingestion endpoints in `backend/routers/admin.py`, ETL admin router,
  Operations helpers, the two frontend surfaces and lane tests/evidence.

The dirty primary checkout was not edited, switched, reset, stashed or used for
installation. Shared auth, Axios, middleware, models, migrations, manifests,
lockfiles, financial/source/publication/seeding code and `backend/main.py` were
read-only. Existing auth and `record_admin_action` signature are preserved.
`frontend/node_modules` in this worktree reuses the compatible read-only
coordinator runtime after byte comparison of both lockfiles. Runtime: Python
3.13.9, Node 22.19.0, Next 15.5.27, React 19.2.4, Jest 29.7.0, Playwright 1.58.2.

## Behavior and acceptance matrix

All API paths below are relative to `/api/v1/admin`. All mounted Operations
responses, including auth, validation and storage failures, carry
`Cache-Control: private, no-store` and `Vary: Authorization`.

| Reachable action or boundary | Result and evidence |
| --- | --- |
| Ingestion list GET `/ingestion-jobs` | Existing domain/status/time filters retained. Days 1–365, page 1–10,000, page size 1–100, domain identifier up to 100 characters, status up to 32. Stable `started_at DESC, id DESC` ordering; SQL diagnostic counts with scalar projections. Real route tests, PostgreSQL list projection, rendered filters and browser list. |
| List Domain/Status/Time window controls | Accessible labels, changes push history and reset page; custom bounded time windows remain representable. Hostile/duplicate URL values canonicalized with replace. Unit rendered controls and Chromium actual requests/history. |
| Clear filters | Pushes `/admin/ingestion`, restoring defaults. Verified in Chromium. |
| Prev/Next and empty later page | Bounded pagination, current filter preservation; an empty later page retains Prev. Browser page 2 history and empty page 4 recovery; parser checks page identity, lengths, totals, duplicate IDs and `has_more`. |
| Desktop row/detail link and mobile card | Explicit keyboard link; Enter opens detail. At 390px mobile cards retain dry-run, counters, status and navigation without horizontal overflow. Chromium. |
| List Refresh/Retry | Uses actual API; loading, empty and error states remain distinct. A failed/malformed/forbidden refresh removes prior success counts. Hidden controls disabled/guarded. Unit tests and malformed-response Chromium refresh/Retry. |
| Ingestion detail GET `/ingestion-jobs/{job_id}` | IDs 1–2,147,483,647; invalid UI IDs make no request. Missing 404 differs from unavailable failure and supports Retry. Response ID must equal requested ID. Real route and rendered/browser checks. |
| Detail counters/timing/dry-run | Displays recorded observation status, not live worker activity. Pending start is labeled Awaiting execution; negative counters unavailable; reversed timestamps withhold duration rather than invent zero. SQL stored-state route regressions. |
| Detail diagnostics/metadata | Raw storage remains intact; browser receives only a generic withheld notice with exact `error_count` and allowlisted operational metadata. Unknown/nested/secret diagnostic shapes never render. Backend privacy and UI defense tests. |
| Detail Refresh/Retry/back | Failed refresh hides stale data; controls stop hidden; SmartBackLink preserves list history/filter/page when reached through list. Unit controls and Chromium history/detail/refresh. |
| GET `/ingestion-jobs/stats/summary` | Existing compact domain/status aggregation preserved with equivalent valid/empty/all-time/future-window outputs. Invalid stored negative counters unavailable. HTTP days bounded; direct-call legacy None/0/-1 controls preserved within -365–365. SQLite equivalence and dedicated PostgreSQL original controls. |
| GET `/etl/schedule` | Validated six-source calendar decisions and derived summary; both `should_run_now` and UI `should_run` agree; `evidence: calendar_plan`. Config dictionaries withheld. Unknown, absent, empty, malformed, contradictory or bad-date planner data fails closed. Actual standalone planner import and mocked adverse planner tests. |
| GET `/etl/schedule/summary` | Existing summary keys retained for Overview, explicitly tagged calendar evidence and unavailable manual dispatch. Same decision-derived summary, not independent execution counts. Real route tests. |
| GET `/etl/schedule/source/{source}` | Six supported source names; unknown 404. Returns plan evidence, validated source decision and timestamp. Real route tests and historical supported endpoint suite. |
| GET `/etl/health` | `scheduler_status`, `worker_status`, `data_freshness` always `unverified`; only `plan_status` is available/unavailable. Planner failure does not fake health. Real route and UI parser tests. |
| ETL Refresh | Reads schedule/health, renders planned/unverified labels and recoverable failures, hides failed prior successes. Hidden controls disabled. Unit and Chromium; no mutation acknowledgement. |
| ETL Run Now/Dry Run controls; POST `/etl/trigger/{source}` | Controls rendered disabled with reason. Known-source real/dry-run/repeated/stale requests return safe 503 `manual_dispatch_unavailable`; no job accepted, DB write or success audit. Unknown source 404; nonboolean dry_run/extra fields 422. No DB/runner dependency. Actual mounted API, direct duplicate tests and Chromium POST controls. |
| Anonymous/nonadministrator | Existing require_admin and real Next middleware block access; every Operations route tested with anonymous/nonadmin failure. Fixture JWT decode/role lookup is inert, not a live Supabase verification receipt. |
| Polling/cache/auth boundary | List/detail poll pending/running observations every 15s while visible and authorized. Stop on terminal/error/hidden; hidden transition aborts requests. Actor-scoped keys and abort/remove on role/actor/unmount prevent old responses crossing actors. Jest fake-time/in-flight regressions. No real worker claimed. |
| Unsupported/malformed API responses | Runtime guards reject arrays, unknown statuses, bool/NaN/infinite/unsafe counts, bad dates, inconsistent IDs/pages/summaries and false execution evidence. Safe recoverable UI errors; raw upstream exception bodies never displayed. Independent adverse parser/route tests plus one intentionally intercepted browser 200. |

Direct route-call validation guards prevent bypassing SQL pagination limits.
Detail storage reads can contain runner diagnostics internally; list SQL never
selects those bodies and public detail projects them out. Metadata allowlist:
`source_mode` in the known modes, boolean `manual_trigger`,
`dropped_by_global_budget`, `dry_run`, and parsed ISO `since`. Arbitrary planner
config, metadata and errors are not returned. Validation responses never echo
input; internal 5xx/storage exceptions become static safe unavailable responses.
Raw diagnostic logging was not added.

## Observed red/green evidence

The committed regression files are executable evidence; compact retained command
outputs are in [operations-evidence](operations-evidence/). These distinguish
author fixtures, independent adverse execution and actual rendered browser runs.

| Reproduction | Observed red | Final green / paths sharing invariant |
| --- | --- | --- |
| Author route regression against pinned code | 20 failed, 12 passed (0.84s) | Final route run 134 passed: real/dry-run command rejection, health, planner decisions/failures, query/ID limits, stable projection privacy and malformed bodies. |
| Author rendered frontend regression before UI repair | 13 failed (8.69s) | 15 author tests plus 23 independent adverse tests = 38 passed. URL/history, empty page recovery, keyboard/dry-run, stale success hiding, visibility/terminal polling and plan/error states. |
| Initially hidden pages before their first read | 2 failed, 13 skipped (0.328s) | Same two cases pass (0.306s), included in final 38. List and ETL wait rather than claim empty or failed results; detail already shared this guard. |
| Fresh backend import collision | 1 failed, 32 deselected (0.41s) | Same test 1 passed (0.35s), included in final full lane. Standalone root planner loaded without shadowing backend `etl` or `seeding`. |
| Negative stored counters / reversed timing | 4 failed, 33 deselected (0.17s) | All included in final 134 pass. List/detail/stats share unavailable counter behavior; reversed detail/list duration withheld. |
| Independent backend adverse tests | Reviewer reproduced config transfer, direct pagination bypass, input echo/internal failure payloads and strict-date gaps; fresh import independently confirmed | 67 retained reviewer cases included in final 134 pass; reviewer combined earlier 100 pass, no remaining confirmed backend finding in exercised scope. |
| Independent frontend adverse tests | Initial 4 failures among 17: three real gaps and one revoked-cache harness expectation corrected | Strict `plan_status` identity, hidden Refresh/Retry and exact redacted error count repaired. Expanded 23 adverse cases pass; no remaining confirmed frontend finding in exercised scope. |

First browser runs caught two harness expectations (back correctly preserved page
2; CSS capitalizes a lowercase status) and the separately retained fresh-process
planner collision. Expectations were corrected to supported behavior; the import
defect was repaired and independently reproduced. Final actual Chromium run is
six passing journeys. An initial shell PATH missing Node was infrastructure,
not a claimed product red. The shared historical PostgreSQL harness refused
Operations' port/database in five setup errors; it was not weakened or pointed
at another lane. The new lane wrapper replays its unchanged controls on owned
PostgreSQL, with 11 passes.

## Exact executed commands

Commands run from the worktree root unless the frontend directory is specified.
The shell variables here are task-specific shorthand for the exact absolute
paths/env passed during execution; no inherited production env or dotenv loaded.

```sh
operations_tree=/Users/roger/.codex/worktrees/admin-operations-batch6/audit_app
operations_python=/Users/roger/Documents/projects/audit_app/venv/bin/python
operations_node=/Users/roger/.nvm/versions/node/v22.19.0/bin/node
operations_node_path=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin:/usr/local/bin
operations_pg=postgresql+psycopg2://postgres:operations-inert-test@127.0.0.1:55472/operations_batch6
```

Baseline, before implementation: **30 passed, two warnings, 0.61s**.

```sh
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH="$operations_tree/backend" DATABASE_URL=sqlite:////tmp/batch6-operations-bootstrap.sqlite \
  "$operations_python" -m pytest backend/tests/test_etl_admin_endpoints.py \
  backend/tests/test_web_ingestion_ownership.py backend/tests/test_ingestion_query_transfer.py -q
```

Author route red then green used the same environment above and
`-m pytest backend/tests/test_admin_operations_lane.py -q`. Fresh import red/green
added `-k fresh_backend_import`; stored-state red used
`-k 'negative_stored or reversed_recorded'`. Final backend:
**134 passed, two warnings, 2.10s**.

```sh
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH="$operations_tree/backend" DATABASE_URL=sqlite:////tmp/batch6-operations-bootstrap.sqlite \
  "$operations_python" -m pytest backend/tests/test_admin_operations_lane.py \
  backend/tests/test_admin_operations_adversarial.py backend/tests/test_etl_admin_endpoints.py \
  backend/tests/test_web_ingestion_ownership.py backend/tests/test_ingestion_query_transfer.py -q
```

Dedicated disposable PostgreSQL, valid/empty/all-time/future controls and scalar
JSON diagnostic kinds: **11 passed, two warnings, 0.89s**. Selected-value byte
estimates are decoded-value estimates, not wire bytes or provider billing.
Original aggregate controls assert output equality and ≤10 selected rows/<4096
estimated bytes; list adds **2 queries, 21 rows, 1832 estimated bytes** for 20 jobs,
with neither raw `errors` nor `metadata` in selected column names.

```sh
docker run --detach --rm --name auditgava-operations-batch6-db \
  -e POSTGRES_PASSWORD=operations-inert-test -e POSTGRES_DB=operations_batch6 \
  -p 127.0.0.1:55472:5432 postgres:16-alpine
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH="$operations_tree/backend" DATABASE_URL="$operations_pg" \
  OPERATIONS_TEST_DATABASE_URL="$operations_pg" "$operations_python" \
  -m pytest backend/tests/egress/test_admin_operations_pg.py -q -s
```

In `frontend`, author UI red/green used the following Jest command with
`__tests__/admin/operations/operations-ui.test.tsx`. Final full Operations UI:
**2 suites, 38 passed, 0.82s**.

```sh
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 "$operations_node" \
  node_modules/jest/bin/jest.js --runInBand __tests__/admin/operations
env -i PATH="$operations_node_path" NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 \
  "$operations_node" node_modules/typescript/bin/tsc --noEmit
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 "$operations_node" \
  node_modules/next/dist/bin/next lint --file app/admin/etl/page.tsx \
  --file app/admin/ingestion/page.tsx --file 'app/admin/ingestion/[jobId]/page.tsx' \
  --file lib/admin/ingestion.ts --file lib/admin/ingestionPolling.ts \
  --file lib/admin/etl.ts --max-warnings=0
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8152 \
  NEXT_PUBLIC_SUPABASE_ANON_KEY=operations-inert-anon-key REVALIDATE_SECRET=operations-inert-revalidate \
  "$operations_node" node_modules/next/dist/bin/next build
```

TypeScript exit 0. Scoped lint zero warnings/errors (Next CLI deprecation notice).
Production build exit 0, compiled 4.2s, full build lint/types and route generation
passed. Minimal browser fixture returns 404 for unrelated public finance
prefetches; those synthetic logs are not financial/deployment acceptance.

Browser fixture from root and production Next server from frontend were started
as separate loopback processes. **Six Chromium journeys passed in 10.3s**:

```sh
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHON_DOTENV_DISABLED=1 \
  "$operations_python" backend/tests/admin_operations_browser_fixture.py
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8152 \
  NEXT_PUBLIC_SUPABASE_ANON_KEY=operations-inert-anon-key REVALIDATE_SECRET=operations-inert-revalidate \
  "$operations_node" node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3152
env -i PATH="$operations_node_path" NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8152 "$operations_node" \
  node_modules/@playwright/test/cli.js test -c e2e/operations/operations.config.ts
```

Real Next middleware/AuthProvider/Axios and mounted backend routes execute against
a temporary SQLite database (45 synthetic jobs) and inert identities. Fixture
JWT verification/role lookup and Supabase auth/profile transports are explicitly
synthetic; external HTTP is blocked. No main lifecycle worker or production
services start. One browser journey deliberately intercepts a malformed response;
the other reads and direct POST rejections use the real fixture API. Independent
UI tests use mocked Axios/auth and jsdom, not a substitute for the browser run.

## Independent review dispositions

Standards and Spec reviews compared the pinned three-dot diff independently and
rechecked the final source delta and draft handoff. Retained reports:
[Standards](operations-evidence/standards-review.md) and
[Spec](operations-evidence/spec-review.md).

Standards: zero documented hard code violations. The duplicate header dependency
finding was repaired and full route/privacy checks replayed. One possible
Repeated Switches smell in existing list/detail badge styling is retained as a
nonblocking judgment call, consistent with preserving the approved shell.

Spec: zero newly confirmed source defects or scope creep; dedicated dispatch and
Overview integration remain the two tracked boundaries below. The reviewer
independently ran 104 route/adverse tests (two warnings, 1.42s) at the first source
head; final author 134 covers those plus existing compatibility suites.

Both reviewers identified an overstated draft receipt for Clear filters and the
Domain/Time window controls. Those controls were added to the retained browser
journey and actually executed successfully in the final six-test replay. The
final matrix therefore describes executed evidence. All review agents completed.

Backend adversarial reviewer: 67 retained cases, final earlier combined
100 pass; no remaining confirmed backend finding in exercised scope.
Frontend adversarial reviewer: 23 retained cases, combined 36 pass;
no remaining confirmed frontend finding. Both completed, not interrupted.
Author final checks include their test files and the later stored-state repairs.

Owned fixture/API and Next server sessions were interrupted normally after final
verification. `docker stop auditgava-operations-batch6-db` removed its `--rm`
container; loopback ports 8152/3152/55472 have no remaining listeners. The browser
fixture's atexit cleanup removed its owned temporary database directory. No other
lane resources were stopped. The worktree remains attached for PR review.

## Defects, compatibility and concrete remaining work

All-state issue searches preceded new tickets; related closed #252/#304 and
existing operational parents did not track these exact defects.

- [#554](https://github.com/Rodgers31/audit_app/issues/554): prior manual command
  inserted a pending observation and recorded success without any consumer.
  This change safely rejects unaccepted commands. Remaining: design/connect a
  dedicated worker dispatch, explicit acceptance ID/state, repeat/stale command
  idempotency/lease controls, accepted-only audit and real/dry-run end-to-end
  execution evidence. This needs coordinated worker/startup/source ownership.
- [#556](https://github.com/Rodgers31/audit_app/issues/556): calendar calculation
  masqueraded as healthy runtime evidence and UI used the wrong decision key.
  Local plan/evidence contract repaired; operational scheduler/worker/freshness
  evidence remains unverified.
- [#557](https://github.com/Rodgers31/audit_app/issues/557): unbounded/unsafe
  monitoring data, diagnostics, malformed UI state and stale polling repaired
  with retained route/parser/control regressions.
- Overview compatibility: legacy summary keys are retained, but scheduler status
  now unverified and running counts carry `calendar_plan`. Existing overview
  treats nonhealthy as unhealthy and labels counts as running. Reproduction and
  suggested owner [#548](https://github.com/Rodgers31/audit_app/issues/548) posted
  in [contract comment](https://github.com/Rodgers31/audit_app/issues/548#issuecomment-6071172346).
  Its consumer files were not edited by Operations. Owner must distinguish
  planned counts and unverified execution during cross-lane integration.

No production/deployment acceptance, broad entire-repository test/coverage gate,
Trivy security scan, real account/worker/provider/storage mutation, financial
freshness certification, migrations, emails or paid design/bot review requested.
The two existing SQLAlchemy declarative_base warnings remain in read-only shared
database/model files. Full staging/production gates in TESTING_GATES.md remain
coordinator/deployment work; scoped local results do not certify them. API
security review exercised auth/privacy/bounds/errors using inert transports;
no Strix service run. No work was interrupted. Issues remain open for acceptance;
coordinator handles review comments and final merge.
