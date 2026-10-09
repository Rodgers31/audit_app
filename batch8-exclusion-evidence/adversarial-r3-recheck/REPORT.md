# Independent adversarial re-verification of round-3 fixes (r3b)

Transcribed by the author from the reviewer's final message; the reviewer's
session rules did not allow it to write a report file. The scripts, exit
codes, summaries, `diff-vs-prior.jsonl` and the cleanup receipt beside this file
are the reviewer's own. Raw run logs and results JSONL were moved by the author to the
session raw-evidence directory (`…/BATCH_8_SESSIONS/NATIVE_EXCLUSION_CLAUDE_EVIDENCE/adversarial-r3-recheck/`).

Environment: CPython 3.13.9, SQLAlchemy 2.0.46, PostgreSQL 16.15 at
127.0.0.1:55485, server TimeZone UTC, HEAD `97fe7746` plus the uncommitted diff.
Every engine used NullPool; the schema prefix was `batch8_adversarial_r3b_`.
Source hashes at start and end were identical: `exclusion.py` 1183e9f6…,
`admin_etl_dispatch_worker.py` 587bdba0…, `models.py` 251a139d…, migration
579388af…. The prior harness's hard-coded old backfill INSERT was replaced by
reading the current migration's INSERT at run time; the new migration attacks
call the real `upgrade()`.

| Run | Exit | Checks | Pass | Fail | Prior |
|---|---|---|---|---|---|
| pg (run 1) | 1 | 192 | 183 | 9 | 194 / 188 / 6 |
| pg (run 2) | 1 | 192 | 183 | 9 | same 9 as run 1 |
| pg_extra | 0 | 8 | 8 | 0 | 8 / 7 / 1 |
| sqlite | 0 | 17 | 17 | 0 | 16 / 1 |
| sigalrm | 0 | 18 | 18 | 0 | 18 / 0 |

The 9 pg "failures" are all prior expectations that no longer match intended
behavior. The reviewer classified every change as fixed or INTENDED, with **no
regressions**. All 8 prior product failures are resolved:

- **Copied `entry_id` (4 checks):** all now pass.
- **Migrated started claims (2 checks, plus 2 follow-ups that no longer apply):**
  now `finish()` returns False, the command is interrupted and the claim is
  retained.

The other changed checks reflect intended changes: the backfill now marks
started commands as entered, only the entry digest is stored, and the
blank-space CHECK.

New attacks: `new_attacks_pg.py` (106 checks, 96 pass, 10 fail) and
`new_attacks_sqlite.py` (19 checks, 16 pass, 3 fail).

- **Copied `entry_id` forgeries:** refused on every path (native, dispatch,
  migrated, SQLite) and in every variant, with true-nonce positive controls.
- **Raw nonce never exposed:** it appears in no SQL, parameter, log, output or
  table dump, while the capture did see the digest.
- **Migrated claims:** behave correctly through `finish()` and
  `register_worker()` across started/not-started combinations and every
  observation shape.
- **Tagged and untagged RUNNING rows:** behave as designed.
- **Idle-in-transaction timeout:** a 300 ms server setting no longer breaks a
  1.5 s run.
- **Autocommit engines:** refused.
- **Model/migration parity:** confirmed.

**Product defect (low): whitespace-only reconciliation accepted** (all 13 new
failures). `length(ltrim(rtrim(x))) >= 1` strips only ASCII spaces, so a tab,
newline, CRLF, NBSP or U+3000 still passes. Only operators write these columns.

**Note: refusal predicate key-existence.** `finish()` treated any row with an
`ownership_refused` key as a refusal, whatever its value. A forged
`{"ownership_refused": false}` row (which needs database write access) let it
release a never-entered claim.

**Note: fail-closed by design.** A never-entered claim that `register_worker()`
interrupted has no runtime release path.

Cleanup: 243 schemas listed and dropped, 0 remaining, 0 advisory locks, the public
schema untouched.

## Author resolution

- **Refusal predicate:** fixed. `finish()` now ignores only rows whose
  `ownership_refused` is exactly `true`. Regression cases `false` and `'no'` are
  in `test_unentered_claim_with_a_correlated_run_observation_stays_uncertain`,
  seen red with the old predicate (`guard-mutations.txt`, round 3b) and green in
  `impacted-suite-6.txt`.
- **Whitespace-only reconciliation:** recorded as a limitation, not fixed. No
  portable PostgreSQL/SQLite CHECK rejects all Unicode whitespace without
  embedding raw control characters in the constraint. Only reviewed operator
  action writes these columns; see #583.
