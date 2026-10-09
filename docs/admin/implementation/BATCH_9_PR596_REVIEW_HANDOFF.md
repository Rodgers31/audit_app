# PR596 review handoff — #581

The coordinator-owned review branch is `codex/batch9-pr596-review` in
`/Users/roger/.codex/worktrees/batch9-pr596-review/audit_app`. It starts from author
head `b4128f7012951d79e0fc4c58305a60a3baafd7aa` and merges accepted main
`b0ec603ccbf29d5ae7f6540faa3d484964334fb1` at
`76fbdbf59cbfe5eb86df54e18b37c7e07f4acf10`. These are local scoped repairs;
independent coordinator review, hosted checks, GitHub replies and merge remain
with the coordinator. No production, provider, financial source, Render, Actions,
shared runtime or native author checkout was changed.

## Review triage

| Review claim | Reproduction and resulting behavior |
| --- | --- |
| Thread `PRRT_kwDOPmNsm86q-cgz`, comment 4235342990: optimized verifier | The original verifier emitted PASSED with a deliberately failed historical receipt under `python -O`. Active verification now uses explicit failures and refuses corrupt receipt verdicts/exits, generator/source identities and archive bytes under both interpreters. |
| Thread `PRRT_kwDOPmNsm86q-chK`, comment 4235343021: alternate loader Engine | Constructor override, `configure(bind=other)` and a changed default bind all reached a different Engine before the fix. `OwnedSessionFactory` now rejects those paths before acquisition; the configured Engine override remains supported. Existing Connection, dynamic-bind, thread/task and closed-session controls remain. |
| Thread `PRRT_kwDOPmNsm86q-chg`, comment 4235343055: worker thread failure | A failed child disappeared inside the background thread while scheduling continued. The scheduling parent now waits synchronously, propagates `CalledProcessError`, unlocks in finally and launches no next source after failure. Real child writer authority and retained interrupted claims remain unchanged. |
| Body-only moderate receipt label | Independently reproduced source changes and recorder changes being mislabeled successful. `run_receipt.py` now compares source, HEAD and generator before/after; zero child exit alone cannot certify drift. Original recorder/verifier snapshots and original receipts remain available. Historical receipts are checked against exact archived Git bytes; fresh candidate acceptance requires separate execution receipts. |
| Body-only moderate SQLite pooling label | `NullPool` discarded the in-memory SQLite schema after each close. It now applies to PostgreSQL; SQLite preserves its native pooling. The owned in-memory writer completes one effect and releases normal claims. |
| Body-only moderate backfill-concurrency label | No defect reproduced in the actual default concurrency path. The real backfill CLI at concurrency 3 processes two distinct inert documents, commits two effects, retains zero normal claims and records two successes/zero failures. The current loader's synchronous write section does not yield while owning its scope. Future coroutine changes still need task-lifetime review; no concurrency workaround or claim release was introduced. |
| CI integration finding | The actual launcher rejected the undeclared root-ETL session importer. Its file is now explicitly in `LEGACY_ETL_TESTS`; launcher regressions and the full CLI collection verify ownership and actual package identities. This is part of #581 and was already recorded by the coordinator. |

Original ownership observations explicitly use `counts_scope=ownership_only` and
zero financial counts. They are not financial census receipts. No terminal
observations were fabricated, no interrupted claims were released, and no
migration/activation or operator reconciliation was performed.

## Executed local verification

The fresh source-bound packet is
`batch9-legacy-etl-evidence/review-verification-manifest.json`. It binds 25 exact
candidate files, seven executed checks and the archived executed recorder.
`review/{current,minimum}.json` and their raw `.log` files each record **115 passed,
zero failures/skips/xfails**: 61 actual PostgreSQL process controls, 20 portable
legacy session controls, 31 receipt/owned-target controls, and three existing
native SQLite regressions. The cases and fixture bytes are identical between
Python 3.13.9 / SQLAlchemy 2.0.46 and Python 3.12.14 / SQLAlchemy 2.0.23.

Both launcher suites pass all 11 controls. The actual full CLI collection passes
14,475 backend cases and 336 legacy cases; all 14,811 node IDs are unique and
cohorts are disjoint. Backend uses `backend/etl`; legacy uses root `etl`; both use
real `backend/seeding`. All 20 new session controls belong only to legacy.
`review/collection-{backend,legacy}.json` preserve complete IDs and identities.
Collection is not a full-suite execution claim.

The active delivery verifier passes normally and under `-O`. Twelve additional
actual candidate-packet controls cover valid readbacks and corrupted source,
failed receipt exits, changed generator identity, modified raw output and source
drift under both modes. Invalid copies emit no PASSED provenance. Critical CI
Python lint E9,F63,F7,F82 and whitespace checks pass. Exact raw logs retain
their emitted trailing spaces through file-specific whitespace attributes. Raw process logs for both
runtimes are archived with hashes in `review/process-log-manifest.json`.

Historical author receipts, failures and original `delivery-provenance.json`
were not relabeled as these edited sources. `historical-source.tar.gz` contains
189 source/generator snapshots verified against the actual author/baseline Git
objects, with a pinned digest and manifest. The active verifier supports shallow
checkouts without needing those old objects; `--historical-only` explicitly
certifies author history. The two old active scripts survive as versioned forensic
snapshots; they are not current acceptance gates.

## Fresh fixture and CI interface

Without `BATCH9_LEGACY_DATABASE_URL`, process tests create their own UUID-named
`batch9-review-596-…` PostgreSQL container and Docker network, run the real Alembic
chain and verify database/user/server/head before any destructive controls.
Docker must have the existing approved PostgreSQL image prepared:
`public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`.
The fixture never pulls an unapproved image or skips by default. It needs no
author container, author URL or PR592 reconciliation fixture.

Default target is inert database `batch9-review-596` on loopback port 55506;
`BATCH9_LEGACY_FIXTURE_PORT=55507` permits a separate owned minimum-runtime run.
Only those two ports are accepted. URL queries, alternate host/database/identity,
ambient `PG*` redirects and unknown port selectors refuse before connections.
Child environments forward only the exact selected fixture port. The fixture
reads the single migration head from current checked-out source instead of a
fixed revision, so additive PR592 migration e583b9c9a001 is supported. This lane
actually replayed e572b8c9a001; the combined-source PR592 replay is the
coordinator's remaining integration check.

`review/{current,minimum}-owned-postgres.json` confirm PostgreSQL 17.11, successful
fresh migrations, exact image/container identity and removal of each owned
container/network with its port free. TCP TIME_WAIT is distinguished from live
listeners during the bounded cleanup probe. Every process group is stopped in
its owning test's finally block. Owned runtime dependencies were not installed
into shared runtimes; missing minimum coverage tooling was added only to the
coordinator-owned cloned minimum environment.

## Preserved attempts and remaining ownership

`review/preserved-attempts/` retains the valid optimization, factory, SQLite,
worker and recorder reds. The initial combined portable run's worker stopper
interrupted its harness; `worker-red-corrected.log` is the valid corrected worker
red. Missing test paths, a first plain DBAPI URL guard mismatch, missing minimum
coverage prerequisite and the global SQLite collection URL mismatch are setup
errors. Initial synthetic launcher count expectations were corrected to include
the new file. A first fresh run passed every case but failed its cleanup check on
TCP TIME_WAIT. The deliberately interrupted obsolete-head run is preserved.
Earlier successes with source/generator changes or incomplete review bindings
are superseded; only the seven fully bound checks in the final manifest certify
this candidate. Six pre-fix snapshots were separately compared to their exact
actual Git objects and archived with hashes.

All fixed findings above stay within #581. The native missing-index issue found
by the author was already tracked as #594; this lane creates no duplicate issue.
No new out-of-lane product defect was confirmed. Operational pooler/capacity,
production RUNNING census, writer quiescence and audited reconciliation remain
with #583 and the coordinator's plan. These local controls cannot release claims
or establish production acceptance.

The coordinator should independently review the finished commit, replay combined
migration/CI integration, reply to and resolve the three threads with their exact
regression evidence, and push/merge only after its accepted checks. This lane did
not push, reply, resolve or merge.
