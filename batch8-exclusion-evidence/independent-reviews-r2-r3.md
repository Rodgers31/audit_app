# Independent Spec / Standards reviews, rounds 2–3, and resolutions

Reviewers were separate read-only agents. Each was given the fixed base, the full
diff (`review-diff-r2.patch` sha256 `2c580ae0…26b`, `review-diff-r3.patch` sha256
`aff93479…c336`), the frozen spec, #572/#554 and the prior reports. Findings are
summarized faithfully below. Resolutions are the author's, each with its
receipt.

## Round 2 — Spec

| # | Severity | Finding | Resolution |
|---|---|---|---|
| F1 | resolved | Scope ownership validated before any handler | `scope-binding-red.txt` → `scope-binding-green.txt` |
| F2 | resolved | Acknowledgement bound to entered execution | same |
| F3 | partial | Inventory is honest, but follow-up issues not opened and handoff absent | #581, #582, #583 opened; handoff written |
| 1 | BLOCKING | No honest release: the receipt CHECK forced a fabricated return. Plus an unbounded RUNNING-row refusal; merging migrates production | `reconciled_by`/`reconciliation` columns and CHECKs; procedure in handoff; RUNNING census is a pre-merge gate in #583 |
| 2 | BLOCKING | A refused domain left no observation row | `_record_not_run`, FAILED `ownership_refused` rows; scope tests assert them |
| 3 | non-blocking | Timeout release is in-spec | kept |
| 4 | non-blocking | 5 s tolerance vs `started_at` taken before entry | `started_at` now taken after ownership is held |
| 5 | non-blocking | Some process tests decided by older checks; concurrent duplicate adapters and dispatch lock loss untested | 3 new process tests |
| 6 | non-blocking | Inventory follow-ups | #581, #582 |
| 7 | non-blocking | Nonce wording false | corrected; later a digest is stored (round 3) |
| 8 | note | Dispatch entry ignored `dry_run` | `command.dry_run is dry_run` at entry; test `[dry_run]` |
| 9 | note | Evidence predated final tree | final suite `impacted-suite-5.txt` with patch hash; probes rerun |
| 10 | note | Batch 7 port constants changed | disclosed in handoff |

## Round 2 — Standards

No documented-standard violations. Lock order and model/migration parity checked
out.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | BLOCKING | Any RUNNING row refuses its domain forever, from the first nightly after merge | No age limit (that would be an expiry takeover). Round 3 limits the refusal to rows without a claim tag (`unclaimed_running`). Production census is a pre-merge gate (#583) |
| 2 | BLOCKING (if transaction pooler) | Session advisory lock committed → `continuous()` lands on another backend; lock leaks into the pool | `pg_try_advisory_xact_lock` in a transaction held open until `close()`. Not exercised on a real pooler (#583 gate) |
| 3 | non-blocking | No honest operator release | see Spec 1 |
| 4 | non-blocking | Refusal leaves no trace | see Spec 2 |
| 5 | non-blocking | Lock leaks on `close()` error path | `close()` rolls back, else invalidates |
| 6 | non-blocking | Claims retained even when provably nothing ran | `finish()` releases never-entered dispatch claims as `failed`; Batch 7 test adjusted and a new test added |
| 7 | non-blocking | Two ack guards deletable with tests green | per-guard tests with positive control; `guard-mutations.txt` |
| 8 | non-blocking | Nonce wording | corrected |
| 9 | non-blocking | Stale evidence | rerun |
| 10 | non-blocking | CI never exercises the PostgreSQL path (hard-coded owned URL gates) | disclosed; hosted CI not executed |
| 11 | discretionary | Swallowed rollback exceptions; misleading logs | accepted; fails closed |
| 12 | discretionary | Eager `models` import from the CLI | lazy import |
| 13 | discretionary | Migration copies running Batch 7 claims | see round 3 B4 |
| 14 | discretionary | Duplicate receipt predicate; port scope creep | not changed; disclosed |

## Round 3 — combined re-review (`review-diff-r3.patch`)

No blocking code defect. Round-2 items verified RESOLVED, except operator
release (PARTIAL: the handoff text was stale) and follow-up issues (then not yet
opened).

| # | Severity | Finding | Resolution |
|---|---|---|---|
| B1 | BLOCKING gate | RUNNING refusal now applies to every native domain at merge | `unclaimed_running` limits it to untagged rows; census gate in #583 and the handoff |
| B2 | non-blocking | Release must clear claim, `etl_dispatch_domains` row and RUNNING row | in the procedure and #583 |
| B3 | non-blocking | Idle-in-transaction cutoff on the lock transaction; autocommit engine | `SET LOCAL idle_in_transaction_session_timeout = 0`; continuity verified right after locking; autocommit test. Pooler-side cutoff remains a gate |
| B4 | non-blocking | Migrated Batch 7 claims look never-entered | backfill marks `execution_started` commands as entered (entry digest of a random value) |
| B5 | non-blocking | Never-entered release trusts non-entry alone | also requires no correlated non-refusal observation |
| 6–8 | notes | Refusal-row ordering safe; no deadlock cycle; CHECK parity and SQLite OK | — |
| 9 | non-blocking | Evidence hygiene (probe predates models; baseline exit captured from a pipe; suite hash unprovable) | probes rerun; baseline recaptured with pytest's own exit; suite header hashes the same patch format |
| 10 | note | A failed best-effort dry-run status update now blocks the domain | listed in the handoff limitations |

Round-3 adversarial findings 1–2 and their fixes: `adversarial-r3/REPORT.md`,
`round3-regressions-red.txt` (round-2 code: 7 failed, 3 controls passed), and
the green suite `impacted-suite-5.txt`.
