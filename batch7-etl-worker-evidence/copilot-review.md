# PR #575 Copilot review repairs

Reviewed source: `2bb1bc90b819eb0d2802a42ed9920731aa98dd60`.
Only acceptance, the seven new UUID model columns, scoped regression tests and this lane's handoff/evidence changed. No seeding domain, source registry, native runner semantics, API lifespan, shared auth, migration or dependency requirement changed.

## Disabled keyed acceptance — valid (4227288440)

The old guard allowed a valid key to reach the database, retire running receipts and return an original accepted command while disabled. The unchanged-source regression produced **6 failures and 4 passing controls**: two keyed direct calls touched the forbidden database; all four native PostgreSQL keyed cases failed their no-work contract, including replay responses of HTTP 202 with newly interrupted receipts.

The enabled check now precedes key parsing/storage for every valid intent. Unknown sources still return 404 and malformed strict bodies still return 422. Tests include real/dry-run, missing/valid/malformed key, new intent/replay, zero database method access, zero SQL and connection checkouts, byte-identical running command/audit snapshots and no new observation. Re-enabling after lease expiry still recovers the original intent and retains domain exclusion.

Inventory: the sole product caller is `routers/etl_admin.py::trigger_etl_run`; acceptance/replay/new command/audit all share `admin_etl_dispatch.py::accept`. Capability and command-history/detail reads are separate observation paths, intentionally capable of retiring stale running receipts; the trigger guard does not change those semantics. Worker claims/finalization and native adapter do not call acceptance.

## SQLite UUID compatibility — valid at declared minimum (4227288471)

The claim was too broad for the installed runtime: exact frozen Base created **32 SQLite tables**, UUID roundtrip returned an actual UUID object, and PostgreSQL UUID DDL compiled on SQLAlchemy **2.0.46 / Python 3.13.9**. However, `backend/requirements.txt` permits **>=2.0.23,<2.1**. A separate owned target install of **2.0.23 / Python 3.12.14** reproduced a SQLite CompileError at `etl_dispatch_worker.generation`, with only the existing JSONB shim. Therefore this is a supported-version defect, not a refutation.

Use SQLAlchemy's generic `Uuid(as_uuid=True)` for all seven new UUID columns. The same exact frozen-model probe goes from red to green on 2.0.23; 2.0.46 remains green. Both produce 32 tables, UUID-object roundtrip and native UUID PostgreSQL DDL. Actual worker/migration/process tests also exercise the unchanged native PostgreSQL schema and UUID identity. No UUID compiler shim or minimum-version bump was added.

## Session configuration concern — no reproduced defect

The body-only review provides no distinct actionable mechanism. Actual unchanged native CLI execution through the adapter completed correlated IngestionJob receipts in **UTC and Africa/Nairobi sessions**, for real and dry-run inert handlers. Real work committed one inert effect; dry-run committed none. The adapter uses an explicitly bound correlation Session subclass; finish reconstructs native timestamp-without-time-zone observations using PostgreSQL's session TimeZone. This is local bounded evidence, not arbitrary production timezone/identity proof.

## Executed final acceptance

- New scoped review suite: **21 passed**.
- Worker/actual process/Alembic migration/adversarial plus operations and native seeding controls: **302 passed, 1 strict xfailed, 3 existing deprecation warnings**.
- The strict xfail is the independently launched native CLI exclusion gap, already tracked in **#572**. Dispatch stays default-off; local repairs do not authorize activation or close that blocker.
- Critical flake8 E9,F63,F7,F82: **0**, exit 0. `git diff --check` passes.
- Hosted Actions/security/full repository coverage and cross-lane UI integration remain coordinator gates.

Full receipts and hashed source/environment manifest: `/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_7_REVIEW/WORKER_REPAIRS.md`.

Original tests restrict their own database to 55481. To respect simultaneous coordinator ownership, verification used an owned Git-archive copy with only three fixture port literals normalized to **55484**. Product source/test logic was otherwise identical; the new review file explicitly guards its own 55484 database. This normalization was not committed into the original fixture allowlists.
