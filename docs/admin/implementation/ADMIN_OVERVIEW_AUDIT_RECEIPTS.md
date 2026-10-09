# Admin overview / audit executed receipts

Task #548, parent #545. These are local executed receipts, not production acceptance. Final code head: `372d6e2` (initial implementation `ee735c3`; pinned base `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`). Documentation-only closeout follows on the same branch.

## Environment and complete commands

All commands use the isolated worktree. Python 3.13.9 is read from the existing primary venv, with this worktree's absolute PYTHONPATH and dotenv disabled. Node 22.19.0 and installed dependencies are reused read-only; manifests/lock unchanged. PostgreSQL 17.11 is the owned disposable container on loopback55473; the explicit opt-in below only targets that database. No test starts the main production application or a worker/provider/email mutation.

From `/Users/roger/.codex/worktrees/admin-overview-audit/audit_app/backend`:

```sh
env -i PATH="$PATH" PYTHONPATH=/Users/roger/.codex/worktrees/admin-overview-audit/audit_app/backend PYTHON_DOTENV_DISABLED=1 DATABASE_URL=postgresql://inert:inert@127.0.0.1:55473/admin_overview_audit ADMIN_OVERVIEW_AUDIT_POSTGRES=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest tests/admin_overview_audit tests/test_etl_admin_endpoints.py -q
```

From `/Users/roger/.codex/worktrees/admin-overview-audit/audit_app/frontend`:

```sh
env -i PATH="$PATH" NEXT_PUBLIC_API_URL=http://127.0.0.1:8153 node node_modules/jest/bin/jest.js __tests__/admin/overview-audit --runInBand
env -i PATH="$PATH" PYTHON_DOTENV_DISABLED=1 BROWSER_TEST_PYTHON=/Users/roger/Documents/projects/audit_app/venv/bin/python NEXT_PUBLIC_API_URL=http://127.0.0.1:8153 NEXT_TELEMETRY_DISABLED=1 node node_modules/@playwright/test/cli.js test --config=e2e/admin-overview-audit/playwright.config.ts
env -i PATH="$PATH" NEXT_PUBLIC_API_URL=http://127.0.0.1:8153 NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next lint --file app/admin/page.tsx --file app/admin/layout.tsx --file app/admin/audit-log/page.tsx --file lib/admin/audit.ts --file lib/admin/overview.ts
env -i PATH="$PATH" NEXT_PUBLIC_API_URL=http://127.0.0.1:8153 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8153 NEXT_PUBLIC_SUPABASE_ANON_KEY=inert-overview-anon NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build
env -i PATH="$PATH" node node_modules/typescript/bin/tsc --noEmit --incremental false
```

Run browser, production build and TypeScript sequentially: they share generated `.next` files. A concurrent author attempt produced missing generated files and was discarded, then replayed sequentially. A browser assertion initially included Next's global route-announcer alert; it was corrected to inspect the admin main region. An initial lint invocation omitted the repository-required explicit API URL and was rerun with it. These setup failures are not behavior regression receipts.

## Retained regression coverage

| Suite | Boundaries exercised |
| --- | --- |
| `test_audit_boundary.py` | Real route/auth/private headers, unavailable table, filters/date bounds/UTC overflow, stable same-time order, ID/time snapshot, legacy payload policy, actual reset/roles/delete/ETL callers, transaction failure isolation and safe logging. |
| `test_audit_postgres.py` | Forced lower-ID late commit, native JSONB/private UTC response, no POST, Unicode visibility rejection on real PostgreSQL17.11. Explicit lane-only opt-in; no external DB. |
| `parsers.test.ts` | Impossible calendar dates, future/capture bounds, exact rows/totals, hostile counters, payload/URL/visibility schema, fresh heartbeat plus scan, atomic malformed snapshot bookmarks. |
| `pages.test.tsx` | Actual owned React pages with React Query: truthful scope, unavailable/malformed data, available/unavailable calendar plans, labelled form/history, deep-page Prev, malformed-bookmark Refresh URL and real refetch, nav specificity. Transport/auth/motion mocks are explicit. |
| `controls.spec.ts` | Actual rendered Chromium desktop/mobile pages and controls, real HS256 admin/citizen API auth, middleware redirects, private safe payload, filters/URL/back/expansion/snapshot pagination, error/malformed/deep-page/Refresh, keyboard nav/mobile overflow. Additive Operations health response is explicitly intercepted in one separate contract scenario; remaining reads use real fixture routers. |

`auditFilters` has one owned production consumer (audit page), and every submit/clear/page/Refresh/history path uses it. Both audit reads (overview and audit page) use `decodeAudit`. `decodeHealth` has one production consumer (overview), covering card and alert branches together. The separate ETL page and producer are Operations-owned, so no edits were made there. Every current audit writer uses the shared backend payload guard; the four caller cases above are executed. Direct privileged SQL outside that helper remains an explicit storage assumption in the handoff.

## Observed pre-fix failures

Initial API and UI cases were executed against pinned production source before edits. Later cases were executed against the immediate pre-fix working source; those intermediate sources have no manufactured Git SHA. Spec findings were red at `ee735c3`. Each named case remains in the final suites and was replayed green. Raw local logs remain under `/tmp`; the durable excerpts and SHA256 below preserve the observed evidence without committing large DOM dumps.

### Pinned API baseline

Local log `admin-overview-audit-backend-red.log`, SHA256 `a072d529d79195a8338a3604a1d4ca260a0f840ceeadc3f8b2be9d1424963d21`.

```text
E       assert 500 == 422
E       assert 200 == 422
E       assert 200 == 422
E       assert 500 == 503
E       assert 'INERT_SECRET' not in '{"entries":...more":false}'
E           assert 'INERT_SECRET' not in "{'email': '...ERT_SECRET'}"
E           assert 'INERT_SECRET' not in "{'anything'...ERT_SECRET'}"
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_snapshot_excludes_later_backdated_insert
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_filters_are_bounded_and_errors_private[days=999999999]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_filters_are_bounded_and_errors_private[page=10001]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_filters_are_bounded_and_errors_private[page_size=101]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_filters_are_bounded_and_errors_private[action=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_private_success_and_authorization
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_absent_storage_is_unavailable_not_empty
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_legacy_payload_is_redacted_on_read
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_actual_reset_caller_persists_safe_payload
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_recording_failure_never_logs_parameters_or_poison_caller
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_independent_transaction_and_unknown_payload
11 failed, 1 passed, 2 warnings in 0.23s
```

### Pinned rendered UI baseline

Local log `admin-overview-audit-ui-red.log`, SHA256 `ba93f61d56e53e1650bf62b8d3fef9c8f9d7c7e539c759292206c995e83ea4e3`.

```text
  ● overview does not certify a running worker from scheduler calculation
  ● overview explicitly reports unavailable audit and failure evidence
  ● overview rejects malformed numeric counts instead of showing a value
  ● audit filters are labelled and submitted together into browser history
  ● empty out-of-range audit page retains a previous-page control
  ● audit rejects malformed successful data as unavailable evidence
  ● admin navigation exposes current subsection and named keyboard navigation
Test Suites: 1 failed, 1 total
Tests:       7 failed, 7 total
```

### Impossible dates, missing rows and snapshot bounds

Local log `admin-overview-audit-parser-red.log`, SHA256 `2a185b91b0474308ad4c93768a10a161e48e766039d8dfd5e21fb367121e3764`.

```text
  ● impossible calendar dates never certify fresh worker evidence
  ● missing rows cannot certify empty evidence with nonzero totals
  ● frontend snapshot bounds match API and reject future capture time
Test Suites: 1 failed, 1 total
Tests:       3 failed, 11 passed, 14 total
```

### Forced PostgreSQL lower-ID commit race

Local log `admin-overview-audit-pg-red.log`, SHA256 `0be6ec45af8712efc0e0d7f09f0c7957231d32baa47addd111dfa368ff260edc`.

```text
E       assert 2 == 1
FAILED tests/admin_overview_audit/test_audit_postgres.py::test_late_commit_of_earlier_allocated_id_cannot_change_snapshot
1 failed, 1 passed, 2 warnings in 0.18s
```

### Timezone overflow and malformed email

Local log `admin-overview-audit-adversarial-red.log`, SHA256 `262f87c705b1ebdf6760499f1576465187519756a7e29e6abe0289b41bc4e124`.

```text
E           assert 'INERT_SECRET' not in "{'email': '...t_to': None}"
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_timezone_overflow_is_invalid_filter_not_storage_outage[as_of-9999-12-31T23:59:59-23:59]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_timezone_overflow_is_invalid_filter_not_storage_outage[since-9999-12-31T23:59:59-23:59]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_timezone_overflow_is_invalid_filter_not_storage_outage[until-0001-01-01T00:00:00+23:59]
FAILED tests/admin_overview_audit/test_audit_boundary.py::test_actual_caller_drops_malformed_email_evidence
4 failed, 14 deselected, 2 warnings in 0.16s
```

### Unicode visibility digits

Local log `admin-overview-audit-unicode-red.log`, SHA256 `427dd1a89742bce154d40c850e5a97cbcaedb8b1157e4bd086befd988662b1e0`.

```text
E       assert 503 == 422
FAILED tests/admin_overview_audit/test_audit_postgres.py::test_visibility_unicode_digits_are_invalid_filters
1 failed, 2 deselected, 2 warnings in 0.12s
```

### Visibility schema agreement

Local log `admin-overview-audit-visibility-red.log`, SHA256 `d7a8c9be3458d375ef4c51158935580f67c14d81bf076d7c27ebbe2b57a51173`.

```text
  ● visibility snapshot schema agrees with API: 3:2:
  ● visibility snapshot schema agrees with API: 2:4:
  ● visibility snapshot schema agrees with API: 3:4294967296:
  ● visibility snapshot schema agrees with API: 3:9:8,4
  ● visibility snapshot schema agrees with API: 3:9:4,4
  ● visibility snapshot schema agrees with API: 3:9:2
  ● visibility snapshot schema agrees with API: 3:9:9
Test Suites: 1 failed, 1 total
Tests:       7 failed, 14 passed, 21 total
```

### Independent Spec findings at ee735c3

Local log `admin-overview-audit-spec-red.log`, SHA256 `5319f166810708c204eb688693fdc6540a4f8ecad9c4ebf9a24e6a9b9360f60d`.

```text
  ● available calendar plan with unverified worker does not invent an ETL alert
  ● Refresh clears malformed snapshot URL with ID NaN
  ● Refresh clears malformed snapshot URL with ID 2147483648
  ● invalid snapshot ID NaN cannot send orphan visibility evidence
  ● invalid snapshot ID 2147483648 cannot send orphan visibility evidence
Test Suites: 2 failed, 2 total
Tests:       5 failed, 29 passed, 34 total
```

### Malformed bookmark Refresh must actually refetch

Local log `admin-overview-audit-refresh-red.log`, SHA256 `088ee3f5bbb3b180f1cafa2abe54233ab571620e78ae21835246b704a47cbcf6`.

```text
  ● Refresh clears malformed snapshot URL with ID NaN
    Expected number of calls: 2
    Received number of calls: 1
  ● Refresh clears malformed snapshot URL with ID 2147483648
    Expected number of calls: 2
    Received number of calls: 1
Test Suites: 1 failed, 1 total
Tests:       2 failed, 9 skipped, 11 total
```

### Backend final green

Local log `admin-overview-audit-backend-final.log`, SHA256 `c69181683a2dee6cee90954c26022d1bff60ce6193ece82dd90a5aaa211cfaa0`.

```text
34 passed, 2 warnings in 0.63s
```

### Frontend final green

Local log `admin-overview-audit-ui-final.log`, SHA256 `bea7dfce2d9373db8925feb47b84b12767331b970074c620d4dc6c6e97fcccf7`.

```text
Test Suites: 2 passed, 2 total
Tests:       34 passed, 34 total
```

### Owned lint

Local log `admin-overview-audit-lint.log`, SHA256 `126461655dea274e8fd1cbc5d718d82dc6d4bec6d9cc7a0696270bf8b8130728`.

```text
✔ No ESLint warnings or errors
```

### Production compilation

Local log `admin-overview-audit-build.log`, SHA256 `56667e947b4400d410957a5afa61377ebafec662bda5d11706abc0681db8e9bf`.

```text
 ✓ Compiled successfully in 4.4s
├ ○ /admin                               6.64 kB         243 kB
├ ○ /admin/audit-log                     3.62 kB         240 kB
├ ○ /admin/etl                            5.6 kB         238 kB
├ ○ /admin/ingestion                     4.39 kB         237 kB
├ ƒ /admin/ingestion/[jobId]             3.06 kB         235 kB
├ ○ /admin/social                          396 B         264 kB
├ ƒ /admin/social/[postId]                 427 B         264 kB
├ ○ /admin/social/accounts               6.74 kB         249 kB
├ ƒ /admin/social/accounts/callback        179 B         104 kB
├ ○ /admin/social/new                      409 B         264 kB
├ ○ /admin/users                         3.62 kB         236 kB
├ ƒ /admin/users/[userId]                10.4 kB         239 kB
```

## Final execution notes

Backend: 34 passed, two existing SQLAlchemy deprecation warnings (21 lane cases plus 13 existing ETL cases). Frontend: 34 passed across two suites. Lane lint: no warnings/errors; Next lint command has a deprecation notice. Full TypeScript: exit0, empty output after build completed. Next production build: exit0; local API/public prefetch warnings do not prove provider/deployment readiness.

Final Chromium replay: five passed in25.2s, exit0. The replay began after production build and TypeScript finished. Screenshots are local `/tmp/admin-overview-audit-desktop.png` and `/tmp/admin-overview-audit-mobile.png`; captures wait for motion completion. Loopback-only browser requests, synthetic identities/token key and fixture SQLite transport; no real account/provider operation. Anonymous redirects reach public pages whose absent fixture API routes produce expected404 logs. No cross-browser, deployed cookie, database ACL/epoch, worker execution, or full other-lane workflow acceptance is claimed.

```text
  ✓  1 e2e/admin-overview-audit/controls.spec.ts:25:5 › actual audit API, filters, snapshot pagination, back history, payload and refresh failures (10.1s)
  ✓  2 e2e/admin-overview-audit/controls.spec.ts:55:5 › overview cards and mobile keyboard navigation preserve shell and truthful scope (2.8s)
  ✓  3 e2e/admin-overview-audit/controls.spec.ts:73:5 › deep empty page recovers and invalid URL numbers stay bounded (3.9s)
  ✓  4 e2e/admin-overview-audit/controls.spec.ts:89:5 › documented Operations health contract keeps available plan distinct from unverified worker (974ms)
  ✓  5 e2e/admin-overview-audit/controls.spec.ts:99:5 › anonymous and citizen sessions cannot render or read audit evidence (1.7s)
  5 passed (25.2s)
```

Final browser log SHA256 `c23870a521bde3f47c38c978e86bbfdc009b3d8ee9390884d122576eb442ad35`.

## Final independent review and cleanup

Standards PASS at372d6e2 (zero violations/smells; all13 recorded hashes verified). Spec PASS at372d6e2 (zero remaining author-fixable findings; independent34-test frontend replay and contract probes). Adversarial PASS at372d6e2 (independent27 atomic URL probes,32 health probes and34-test frontend replay; no new findings). These are separate local reviews, with no paid/bot review requested. The initial independent backend replay was21 lane cases passed with two warnings, including actual PostgreSQL tests.

After reviews, `docker stop batch6-admin-overview-audit-pg` succeeded; its --rm container disappeared. `docker ps -a --filter name=batch6-admin-overview-audit-pg --format '{{.Names}}'` returned empty. `lsof -nP -iTCP:3153 -iTCP:8153 -iTCP:55473 -sTCP:LISTEN` returned no listeners (exit1 means none). No unrelated process/container was terminated. The isolated checkout and its ignored dependency symlink remain for coordinator review.
