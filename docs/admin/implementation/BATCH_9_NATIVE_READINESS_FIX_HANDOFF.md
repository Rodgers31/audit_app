# PR #584 admission readiness repair — issue #594

Author handoff status: local acceptance passes; coordinator and independent reviews were
pending at that handoff. No file was staged or committed, and the author made no push, PR,
Actions setting change, production connection, production write or merge.

## Problem and resulting behavior

The original native CLI could enter another claim and commit an inert effect
after `uq_seeding_active_domain` was removed, even with an earlier entered claim
still retained. Successful `ON CONFLICT DO NOTHING` did not prove that its
essential domain arbiter existed. The original SQLite control supplied by the
legacy ETL author is preserved in that author's evidence; this packet reproduces
the defect independently on SQLite and PostgreSQL.

`backend/seeding/exclusion.py` now reads all required claim columns and checks the
actual storage arbiter before admission. PostgreSQL checks the search-path
resolved real table, a valid/ready/live immediate unique index whose sole key is
`domain`, and the reviewed `released_at IS NULL` predicate. SQLite checks the real
main table, matches metadata with SQLite's ASCII case identity, rejects temporary
shadows regardless of ASCII letter case, and verifies uniqueness, sole domain key
and the same predicate. An equivalent valid index may have another name. Missing
tables/columns, views, missing/nonunique indexes, wrong or multiple keys, wrong
or narrower predicates, and invalid PostgreSQL indexes refuse admission.

The helper performs no schema repair, claim clearing, expiry or takeover. Its
diagnostics contain no raw database exceptions. Retained claims remain unchanged
when readiness is refused.

## Shared path coverage

| Path | Readiness boundary |
| --- | --- |
| Native `seed --domain` and `seed --all`, including dry run | `DomainExecution.open()` checks the execution connection; `reserve()` checks the actual acquisition transaction before inserting a claim. |
| Dedicated worker acquisition | Its existing call to shared `reserve()` checks the same transaction that commits the command/token claim. |
| Actual dispatch adapter | Its existing `DomainExecution.open()` call refuses broken storage before it persists `execution_started`. |
| Actual CLI inside authenticated dispatch scope | `_enter_dispatch()` checks the entry transaction before consuming the claim or calling a handler. |
| Normal acknowledgement/release | Existing savepoint and outer lock-connection commit remain unchanged; actual backend-death controls verify authority stays retained when proof/commit fails. |

PostgreSQL's table read holds `ACCESS SHARE` on the execution transaction; an
actual ordinary index drop is blocked until that transaction closes. Concurrent
privileged index DDL can invalidate an index despite that lock. A controlled
concurrent-drop test proves a dispatch entry refuses the invalidated index, but
this repair does **not** certify fencing of arbitrary privileged DDL during an
already executing handler. Schema operations still require operator coordination.

No legacy ETL, bootstrap, reconciliation, adapter/worker caller, model, migration,
frontend, dependency, workflow, dispatch mapping or default was edited.

## Source and observed acceptance

Starting commit: `5c68fb1b4454bad60db9bf12f9b7c68ce4549168`, the coordinator's
main-plus-original-#584 candidate. The tested fix is uncommitted; receipt
`target_commit` fields identify this starting HEAD, while the following content
hashes identify the actual tested modified source:

| File | SHA-256 |
| --- | --- |
| `backend/seeding/exclusion.py` | `711c028e0cf704cf2b3c47aed07f82447832472488470ca15d73317cf17166b7` |
| `backend/tests/test_batch9_native_schema_readiness.py` | `04953a41dd4d1cbf0a751389e1d3e1510c082c9040e2cbeaac64e6ee078bc727` |
| `backend/tests/batch9_native_readiness_fixture/sitecustomize.py` | `8dba2c966e2821829ea16e60518defda86770243f485f82320c1b628701504be` |

| Run | Actual result |
| --- | --- |
| Current Python 3.13.9 / SQLAlchemy 2.0.46 | 73 passed, zero skipped/xfail: 70 new controls plus 3 existing SQLite ownership tests. |
| Minimum Python 3.12.15 / SQLAlchemy 2.0.23 | The same 73 tests passed, zero skipped/xfail. |
| Six ASCII-case controls on reviewed first repair (`5b8963f6…`) | Six behavioral failures on each runtime: four CLI/shared-reserve TEMP shadow admissions and two refusals of valid main tables. |
| Historical 64 new tests on isolated original starting source | 45 behavioral failures, 19 positive passes. The missing-index native/adapter module processes actually commit effects on the original source and fail the refusal assertions. This earlier selection predates six new ASCII-case controls. |
| Historical minimum runtime selected original entry controls | Four behavioral failures: actual CLI SQLite/PostgreSQL and actual native/adapter module processes. |
| Critical Python lint and whitespace | Passed with the read-only minimum runtime and `git diff --check`. |

Selections overlap and their counts must not be added. The real CLI and dispatch
implementations run in every entry control; only the registered domain handler
is inert. Module-process fixtures load the actual domain modules first, then
replace the handler registry and block external transports. Effects are confined
to dedicated inert fixture tables in the owned database.

The PostgreSQL matrix includes a real invalid index left by a failed concurrent
unique build, missing/wrong indexes both before worker acquisition and after
dispatch claim, both healthy acquisition orders, real dry-run/normal module
returns and subsequent release, actual backend termination after continuity
proof and before commit, concurrent invalidation before actual dispatch entry,
ordinary DDL lock behavior, and a non-public search-path table with a valid public
index that must not mask its own missing arbiter. SQLite includes actual CLI
refusal, incomplete storage, renamed valid indexes and temporary shadow tables.

## Evidence and historical corrections

`batch9-native-readiness-evidence/manifest-case-final.json` binds final source
hashes, copied immutable receipts and the exact retained receipt-generator
bytes. Final run receipts are `green-current-case-final.json`,
`green-minimum-case-final.json`, `red-sqlite-case-v1-current.json`, and
`red-sqlite-case-v1-minimum.json` under that directory's `receipts/`. Runtime
version and critical lint receipts are retained as well.

Correction on 2026-10-09: independent Standards review found that SQLite folds
ASCII identifier case but the first repair's `sqlite_temp_master` name comparison
did not. Uppercase/mixed-case TEMP tables could therefore accept another claim
while main retained an entered owner; the actual CLI committed an inert effect.
The six new controls were run against exactly reviewed source
`5b8963f6d82397bf6bdec43c10de3b487c18f922017ce121dd47f40613920e6f`
before the fix and then against the corrected source. Both TEMP and main metadata
comparisons now use `COLLATE NOCASE`. PostgreSQL guards are unchanged. Positive
uppercase/mixed-case main-table controls prove valid storage still permits
normal return and a subsequent run. The previous `manifest.json`, its 67-test
acceptance, original 45/19 result and all original receipts remain immutable and
are explicitly superseded by the new manifest; they are historical evidence.

Earlier receipts are explicitly **SUPERSEDED** in the manifest; they are not
edited or deleted. Initial `red-current.json` is a setup failure from an in-memory
SQLite import URL incompatible with product pool options, not a behavioral red.
`red-current-full.json` also includes eleven dispatch-fixture setup failures from
passing a UUID object where the real strict request model requires canonical
text. Corrected real dispatch reds are retained separately. The first green had
twelve redundant unsupported SQLite-dispatch parameters; final parametrization
selects PostgreSQL for those real dispatch paths and has zero skips. Final
original-source replay used exactly that earlier 64-test fixture version. The new
ASCII-case replay uses exactly the final fixture bytes on the reviewed first
repair, so it isolates the newly found product defect. The argument-parser setup
error and absent current-runtime `flake8` module were tool/setup failures; no
product finding is inferred from either. Critical lint was then executed with
the read-only minimum runtime's installed `flake8`.

## Replay and resource handoff

Managed worktree:
`/Users/roger/.codex/worktrees/batch8-review-exclusion/audit_app`.

Current read-only runtime:
`/Users/roger/Documents/projects/audit_app/venv/bin/python`.

Minimum read-only runtime:
`/Users/roger/.codex/worktrees/a46a/audit_app/.batch9-min/bin/python`.

From the managed worktree, use a fresh receipt name:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/roger/Documents/projects/audit_app/venv/bin/python \
  batch9-native-readiness-evidence/run_receipt.py reviewer-unique-name \
  /Users/roger/Documents/projects/audit_app/venv/bin/python \
  -m pytest -p no:cacheprovider \
  tests/test_batch9_native_schema_readiness.py tests/test_batch8_exclusion_sqlite.py -q
```

Replace the inner executable for the same minimum-runtime selection. Append
`-k sqlite` before `-q` for a SQLite-only selection that does not request a
PostgreSQL fixture. The wrapper supplies an owned file SQLite URL for application
imports, disables dotenv and bytecode, and sets the explicit inert database URL.
Do not install into either shared runtime or read the primary checkout's `.env`.

Owned container `batch9-native-readiness-db`, network
`batch9-native-readiness-net`, PostgreSQL 16 Alpine, loopback port `55495`;
database/user `batch9_native_readiness` / `batch9_readiness` with the expressly
inert password in the fixture. The test destructively resets only those exact
allowlisted local fixtures. **Serialize PostgreSQL replays.** The owned container
is intentionally retained running for independent review; the coordinator owns
its stop/network cleanup after reviewer handoff. All author subprocesses and
concurrent-DROP threads have completed; no author database replay is running.
The isolated original-source snapshot under `.native-readiness-tools/baseline/`
is a local replay resource, not a product file to stage.

This packet certifies local readiness behavior only. Production migration,
provider feasibility, writer quiescence, existing RUNNING observations,
reconciliation and deployment acceptance remain with the coordinator and their
separate tracked issues.

## Coordinator local acceptance — 2026-10-09

The final SQLite case-matching repair is accepted locally. Independent Spec and
Standards rereviews each reproduced the six case controls failing on the first
repair and passing on final source on both actual runtimes. Standards' original
independent acquisition control now refuses a second owner, preserving one main
claim and zero temporary claims. Both reviews verify the final author packet's
73 passing tests per runtime, its 20 receipt/generator identities and unchanged
PostgreSQL guard bytes. Earlier findings and evidence remain historical.

The coordinator separately replayed the overlapping SQLite selection before the
case correction on both runtimes; those 25-case receipts are historical and do
not replace the final six-case rereviews. The final code and test hashes are in
the dated correction above and `manifest-case-final.json`.

After every reviewer released its database use, the coordinator removed the
exact owned PostgreSQL container and its otherwise empty network, and verified
loopback port 55495 was free. The earlier retained-resource handoff is now
superseded by that cleanup. Replays require a newly owned local fixture.

Immutable combined hosted acceptance and the eventual merge decision remain
pending. No production migration, claim reconciliation or activation is
certified by this local acceptance.
