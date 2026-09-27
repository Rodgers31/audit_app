# Consolidation #327 — 27 September 2026

Consolidates #330, #333 and #336 into existing #327 with all source commits preserved. Automatic merges touched main.py, the pending-bills fetcher and frontend types.

## Focused verification

202 preservation, citation, edition and revenue backend tests; 18 frontend tests; TypeScript passed. Independent probes exercised page-only reissue, refused truncation and shared resume plus edition selection.

The sessions already ran broad tests and PostgreSQL probes; this pass concentrates on combined boundaries. No whole-repository re-audit or paid bot review was requested. Jest used forceExit for the existing open handle. New main-targeted CI is required on the pushed consolidation head.

## Copilot review received at 16:38 UTC

All four new findings were reproduced and corrected:

- The standalone reconciliation probe imported a test fixture, failing the whole-tree import guard. It now builds explicit synthetic source data itself, works from another working directory, and fails explicitly even under `python -O` if stale evidence is accepted.
- #337: stale ORM state and competing approvals could overwrite newer evidence. Reconciliation now locks the source document before any savepoint flush, refreshes source and extraction state, and retains the lock through loading and the caller's transaction. The parent lock also covers an empty extraction set. Pending new/dirty/deleted extraction objects are refused before an implicit flush can bypass review. The shared boundary covers national and county extraction.
- Impossible calendar dates such as 2026-02-29 and 2026-04-31 now return absence instead of silently rolling into another month. Valid leap days remain accepted.
- Revenue notes, report-card labels and the cash/opening-balance KPI use shared English, Swahili and plain-English translations. Quoted source terminology, fiscal periods, zero values and absence remain intact.

The other backend CI failure was a literal pair of county names in the existing disposable PostgreSQL harness. The guard's documented reason annotation now identifies that synthetic fixture; no guard implementation or public data was changed.

### Executed checks

- Core backend command: `pytest tests/ --ignore=tests/integration -m 'not slow' --maxfail=5 -q` — **4,730 passed, 21 skipped**. The optional PostgreSQL cases are executed separately below.
- Real PostgreSQL 17, disposable loopback database: **12 passed**, with three observed `pg_stat_activity` transaction lock waits. Coverage includes stale extraction and source identity, unrelated metadata preservation, competing writers, first insertion into an empty document, rollback, independent documents and pending extraction mutations. Before the fix, the initial cases produced seven failures and two passing controls; the three pending-mutation cases also failed against the baseline module.
- Existing extraction preservation/recovery/hostile-input/national-walk tests — **82 passed**, including valid reviewed revisions and surviving audit/extraction IDs.
- Standalone normal/optimized subprocess tests plus the whole-tree import guard — **3 passed**, after reproducing the original import failure and stale-write failure.
- County-ranking guard suite — **350 passed**, after reproducing the harness false positive.
- Frontend date, revenue-note and actual overview/report-card render tests — **22 passed**, following seven baseline failures and ten passing controls. TypeScript passed. Jest used the existing `--forceExit` workaround.

Run the PostgreSQL cases with `RECONCILIATION_TEST_DATABASE_URL` set to a loopback database named `codex_reconciliation_test` on a nondefault port, then `pytest tests/test_reconciliation_postgres_concurrency.py -q -s`. Each test creates and drops only its own random schema. No production database was used. The standalone SQLite probe verifies stale-session refusal; it does not establish PostgreSQL locking.

The locking choice follows [SQLAlchemy's refresh guidance for locked ORM queries](https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html#sqlalchemy.orm.Query.with_for_update) and [PostgreSQL transaction-held row locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS), and was exercised with actual competing database sessions.

## Remaining limits

#337 is corrected by this review update and is linked for closure when #327 merges. Fresh CI on the pushed commit is still required. Backend deployment must precede updated seeds; #318 stays separate until deployment and backup. Native Swahili review remains tracked by #307. No browser or production-runtime validation is claimed by the unit/component checks above.

No production deployment, seed, data cleanup or merge to main was performed. Source issues stay open where production acceptance is pending.
