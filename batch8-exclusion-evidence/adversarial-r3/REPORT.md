# Independent adversarial execution, round 3 (#572)

Transcribed by the author from the reviewer's final message. The reviewer's
tooling refused to write this file; every script, log, results file, exit code,
source-identity file and cleanup receipt beside this file is the reviewer's own.

Reviewed source: HEAD `97fe774` plus uncommitted diff `review-diff-r3.patch`
(sha256 `aff93479…c336`). Source hashes at start and end were identical
(`source-identities-start.txt`, `source-identities-end.txt`). Runtime: CPython
3.13.9, SQLAlchemy 2.0.46, psycopg2 2.9.11, PostgreSQL 16.15 at
127.0.0.1:55485. Each scenario ran in its own `batch8_adversarial_r3_<hex>` schema
(103 schemas). Sockets were limited to loopback.

| Run | Exit | Checks | Passed | Failed | Harness errors |
|---|---|---|---|---|---|
| run-pg-01 (superseded) | 1 | 134 | 125 | 9 | 4 |
| run-pg-02 | 1 | 194 | 188 | 6 | 0 |
| run-sigalrm-01 | 0 | 18 | 18 | 0 | 0 |
| run-sqlite-01 | 1 | 17 | 16 | 1 | 0 |
| run-pg-extra-01 | 1 | 8 | 7 | 1 | 0 |

Final runs: 237 checks, 229 passed, 8 failed. The 4 harness errors in run-pg-01
were the reviewer's own mistakes (a CHECK it violated, a stray RUNNING probe row,
and connection exhaustion from per-scenario pools).

## Finding 1: finish() released migrated Batch 7 claims whose CLI did or may have run (4 checks)

`F2_migrated_started_with_completed_cli_job_finish`, `F2_migrated_started_no_job_finish`
and their `…_native_unblocked_after_release` follow-ups. A running command with
`execution_started=true` was backfilled by the migration with `entered_at` NULL,
so `finish()` treated it as never entered: the command became failed, the claim
was released and a native run proceeded. Expected: interrupted and retained. The
control with `execution_started=false` passed. This is reachable only by calling
`finish()` with the pre-migration generation; `register_worker()` interrupts and
retains such claims.

## Finding 2: entry nonce copied from the database lets a non-entering object acknowledge (4 checks)

`G_forged_db_copied_entry_cannot_release_lockloss_retained_claim`,
`G_forged_db_copied_entry_cannot_release_retained_native`,
`X1_dispatch_lockloss_forged_db_entry_ack`,
`S5_sqlite_forged_db_copied_entry_cannot_release_retained`. Setting `entered=True`
and `entry=<entry_id SELECTed from the claim>` on a fresh object made
`acknowledge` succeed, including after lock loss. In X1 this turned an
unverified dispatch into a normal release. Rated low-to-medium: it needs
in-process code and read access to the claim row.

## Prior-round reproductions now rejected

Round-1 finding 1 (uncorrelated scope, A1): exit 1, 0 handler calls, claim
untouched, one FAILED `ownership_refused` row. Round-1 finding 2 (wrong-domain
acknowledgement, A2/A2b): `DomainOwnershipError`, claim retained.

## Passed (summary)

- 34 forged-scope variants: no handler started, no claim or command moved.
- 11 entry-precondition cases.
- Concurrency: shared-scope ×5, independent scopes ×3, real duplicate adapters
  ×3, entry racing finish ×8 (both orders, no inconsistent outcome), native
  entry ×5, raw reserve ×5, real CLI ×3.
- Acknowledgement: 22 rejected job shapes, 9 rejected id values, nonce/kind
  mismatches; a valid ack releases exactly once; lock-backend termination is
  rejected.
- Refusal rows can never be acknowledged and never complete a command.
- 44 raw-SQL schema probes.
- 18 SIGALRM checks: per-domain and global timeouts, swallowing and raising
  handlers, re-entrant entry, KeyboardInterrupt retention, dispatch timeouts.
- Non-UTC session time zones.

## Observations (not counted as failures)

1. A native handler that calls `enter_domain` for another domain strands that
   domain's claim. Fail-closed.
2. A failed RUNNING insert retains the claim and leaves no `ingestion_jobs` row.
3. On SQLite, dispatch entry is refused by a naive/aware datetime `TypeError` in
   `fresh()`, not by an explicit guard.
4. The reconciliation CHECK accepted blank strings.

## Cleanup

`cleanup.py` exited 0. 103 schemas were dropped, 0 left, 0 advisory locks held.
All engines were disposed. The SQLite evidence database was moved out of the
repository by the author, to the session's raw-evidence directory.
