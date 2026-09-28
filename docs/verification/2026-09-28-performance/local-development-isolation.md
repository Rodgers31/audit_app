# Local development isolation receipt — issue #356

Branch: `codex/local-dev-isolation`, based on `37c6c37c565b3190ae0f72fb5fa895daf68abe24`.

## Change

`scripts/local_dev.py` checks inherited endpoints before startup, clears
database and Supabase variables for child processes, refuses private env files
in the isolated checkout, and runs on ports 13080/18080. The default API uses
the existing browser acceptance fixture with a persistent SQLite file. Optional
`docker-compose.local.yml` provides a dedicated persistent PostgreSQL 17 database
on loopback port 55432. Both modes use the same synthetic county/budget/audit
fixture and suppress background jobs. PostgreSQL queries carry
`application_name=auditgava-local-dev-api`. Production diagnostics have a
separate command with a read-only transaction and require a read-only DB role.
The existing `docker-compose.dev.yml` stays unchanged for the develop deployment.

## Verification

- Guard regression was red before the launcher existed (the test's expected
  rejection text was absent); after implementation,
  `/Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest backend/tests/test_local_dev_launcher.py
  backend/tests/test_local_dev_fixture_workflow.py
  backend/tests/test_database_import_modes.py -q` passed **18 tests**.
  The launcher tests execute both `check` and `api` with inherited remote
  database/API targets, including a loopback URL with a remote libpq `host`
  override. They reject before process startup.
- Two additional fixture preflight tests first failed against a seeder that
  accepted unrelated tables and extra rows. They now pass: existing databases
  are inspected before any DDL, and only the exact synthetic fixture shape is
  reopened.
- `/Users/roger/Documents/projects/audit_app/venv/bin/python scripts/local_dev.py db-up` created and waited for the
  isolated PostgreSQL service to become healthy. Docker was initially stopped;
  it became available during the session. No production database was accessed.
- `/Users/roger/Documents/projects/audit_app/venv/bin/python scripts/local_dev.py api --db postgres`, followed by
  `/Users/roger/Documents/projects/audit_app/venv/bin/python scripts/local_dev_smoke.py`, passed. After stopping and
  restarting the API, the same smoke passed against persisted rows: one
  country, two audit rows. `pg_stat_activity` identified the query client as
  `auditgava-local-dev-api`.
- `/Users/roger/Documents/projects/audit_app/venv/bin/python scripts/local_dev.py api` (SQLite fallback), followed by the
  same smoke, passed. The fixture test also starts two fresh Python processes
  against one SQLite file and verifies identical responses without duplicate
  rows.
- Representative responses: two county list entries; Nairobi detail KES
  100 billion by default and KES 50 billion in FY2024/25; latest fiscal
  period FY2025/26 9M; one published synthetic warning; the later uncited
  audit row withheld; Mombasa budget `null`; national fiscal summary
  `no_data` with `current: null`.
- `/Users/roger/Documents/projects/audit_app/venv/bin/python scripts/local_dev.py frontend` served `/counties` and
  `/counties/nairobi` with HTTP 200 on port 13080. Headless Chromium opened
  Nairobi detail and observed local `127.0.0.1:18080` API responses at 200.
- `BROWSER_TEST_PYTHON=/Users/roger/Documents/projects/audit_app/venv/bin/python
  npx playwright test -c playwright.acceptance.config.ts
  e2e/acceptance/counties.spec.ts` passed **2 browser tests**, including
  sourced zero versus absence and fiscal-period selection.
- The same Playwright command with `e2e/acceptance/z-refresh.spec.ts` passed
  **1 browser test**, covering the existing fixture mutation and signed cache
  invalidation path after the fixture extraction.
- `scripts/production_diagnostic.py` was exercised only against the local
  PostgreSQL container; it returned client counts from a read-only transaction.
- After moving the local service to `docker-compose.local.yml`, `docker compose
  -f docker-compose.local.yml config --quiet` passed and the PostgreSQL API
  smoke passed again. `git diff --exit-code 37c6c37c565b3190ae0f72fb5fa895daf68abe24
  -- docker-compose.dev.yml` confirmed the develop deployment Compose file
  matches the base exactly.
- `git diff --check` and `python -m py_compile` passed for changed Python.

## Limits and follow-up

The SQLite fallback is limited to routes supported by the acceptance fixture;
PostgreSQL-specific features need the Compose path. Neither fixture verifies
real publication URLs, and its synthetic links deliberately use
`example.invalid`. The old county audit-list route emits `source.page: null`
even though the stored synthetic finding has `page_ref="p. 2"`; this pre-existing
route behavior is outside issue #356 and is tracked as [#359](https://github.com/Rodgers31/audit_app/issues/359).
The coordinator owns combined suite/CI and PR
review. No production snapshot, production read, or deployment was performed.
