# #611 bounded design proof

Read [DESIGN.md](DESIGN.md) first. Production epoch-aware storage is **not
activated**. The client accepts versioned xid8 bookmarks; the owned-only API
prototype proves their storage semantics. The ordered Alembic migration,
legacy-history admission and restore/retention certification remain pending.

`launch_probe.py` retains the original actual HTTP/root-writer test input bytes.
Its epoch-one 200 assertion is intentionally red on the launch reader. It is not
part of the normal backend test collection. `test_prototype.py` imports those
identical test functions using the provisioned prototype fixture.

Fresh owned PostgreSQL must be available on loopback55534 as database issue611,
owner inert with an inert password. Do not use a production connection or
another lane's database. Set up a disposable PostgreSQL17 cluster; the lane's
controlled epoch-one fixture uses an offline counter adjustment described in
DESIGN.md. The recorder sets explicit inert configuration before imports.
Select an owned Python runtime with the declared backend dependencies installed.

From the repository root:

```sh
python3 docs/admin/implementation/batch11-issue-611-evidence/record.py \
  --python /absolute/owned/venv/bin/python \
  --out /absolute/fresh/external/output \
  tests/admin_audit_epoch/test_prototype.py \
  tests/admin_overview_audit/test_review_boundaries.py \
  tests/admin_overview_audit/test_audit_boundary.py
python3 docs/admin/implementation/batch11-issue-611-evidence/verify_run.py \
  /absolute/fresh/external/output/run.json
```

The recorder refuses existing or symlinked outputs, common Git metadata and
all registered checkouts. It rechecks destination identity after execution and
before publishing. It records all tracked and nonignored source, actual child
exit, raw logs, JUnit identity
counts and runtime. It accepts no skipped cases. `verify_run.py` requires exact
scalar types, complete retained execution metadata, exact raw JUnit identities,
captured runtime output, current Git/source status, and raw output hashes. Normal
and optimized verifier runs disable source bytecode writes themselves. These are
local consistency checks; they cannot authenticate someone able to rewrite all
records and outputs together. It reports **current local backend replay** only. Old receipts
cannot become current by editing their HEAD/hash fields. Historical receipts,
failures and setup attempts are kept separately; this verifier intentionally
refuses them when source or generator identity has moved.

For Chromium, use the owned frontend `npm ci` installation and the
`frontend/e2e/admin-audit-epoch/playwright.config.ts` config. Provide
`ISSUE611_BROWSER_PYTHON`, a fresh `ISSUE611_BROWSER_OUTPUT`, and explicit inert
`NEXT_PUBLIC_API_URL=http://127.0.0.1:18034`,
`NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:18034`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY=inert`. Launch from an allowlisted environment.
The API and UI use18034/13034, and the browser blocks nonloopback requests.
The fixture performs explicit database cleanup/readback before Playwright exits;
after an interrupted/failed attempt, inspect and clean only these owned resources.

Full backend core, actual Alembic upgrade, hosted gate and deployment acceptance
are not claimed. #611 and #583 remain open. See the committed lane handoff and
external final postcommit binder for source correspondence and remaining work.

The published `history-v1.tar.gz` and `history-index.json` retain prior diagnostic
bytes, failures and independent reports. `python3 docs/admin/implementation/batch11-issue-611-evidence/verify_packet.py`
checks the actual bundle and producer inventory without extracting it. It reports
only historical bundle integrity, with `current_acceptance=false`. Then replay the
live recorder and verifier above into a new external destination. No old
`run.json` or generator identity has been rewritten to match this publication.
