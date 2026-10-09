# Batch 8 — shared native ETL exclusion handoff (#572)

Status: **author delivery for coordinator review. Not accepted.** #572 stays
open for coordinator acceptance; #554 and #545 stay open (other source mappings
and production activation pending). Dedicated dispatch remains default-off and
limited to the accepted OAG→`audits` mapping. Pre-merge operational gates
(below, and #583) are **not executed**.

## Identities

| | |
|---|---|
| Base (fixed review source) | `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, tree `f22a430a4402d79867da63ad97db8c8d474d3a71` |
| Branch / head | `codex/batch8-native-exclusion`; head = the commit containing this file (see the PR) |
| Worktree | `/Users/roger/.codex/worktrees/afa1/audit_app`; the dirty primary checkout was not touched |
| Runtime | macOS 27 arm64. CPython 3.13.9 + SQLAlchemy 2.0.46 (read-only primary venv). SQLAlchemy 2.0.23 probe on CPython 3.12.14 using the read-only Batch 7 review target install |
| Database | owned `postgres:16-alpine` container `batch8-exclusion-afa1-db`, `127.0.0.1:55485`, db/user `batch7_etl_worker`/`batch7_worker` |

This session resumed an interrupted, uncommitted implementation. Before any
edit, the tracked diff and every untracked file were byte-compared with
`NATIVE_EXCLUSION_RECOVERY_SNAPSHOT`: identical, and nothing was newer than its
manifest. The only processes using that worktree were idle REPLs from the
interrupted session; they were left alone.

## Resulting behavior

`backend/seeding/exclusion.py` is the single seam. `seeding.cli.run_seed_command`
calls `enter_domain(SessionLocal, domain, dry_run)` for every domain, including
`--all`, **before** writing the RUNNING observation or invoking the handler.

**Acquisition.** All ownership lives in `seeding_domain_claims`, which has a
partial unique index on `domain WHERE released_at IS NULL`. A native run inserts
a `native` claim. The worker's `claim()` inserts a `dispatch` claim, whose id is
the server's claim token, in the same transaction that marks the command
running. The first insert wins; the loser starts nothing.

**Durable one-use entry (finding 1).** `entered_at` and `entry_id` record entry.

- A native claim is entered as it is acquired.
- A dispatch claim is entered only by `_enter_dispatch`. In one transaction it
  locks worker → dispatch-domain row → command → claim, the same order the
  worker uses, and re-proves:
  - a fresh worker lease of the scope's generation;
  - the dispatch-domain row bound to the command and token;
  - the command `running` and `execution_started`, with the same domain,
    dry-run intent, token and generation;
  - the claim kind `dispatch`, same domain and command, and not yet entered,
    returned or released.
- Only then is the entry recorded.

Any mismatch stops the run before the handler and before any claim or command
moves. A forged, mismatched or replayed scope starts no work.

**Acknowledgement bound to entry (finding 2).** `acknowledge` releases nothing
unless all of these hold:

- this object entered and holds the entry nonce;
- the claim's domain, kind and command match the object;
- the continuity lock is still held (below);
- a coherent terminal observation is tagged with the claim id.

The claim stores only `entry_digest(nonce)` (truncated SHA-256), so neither
another object nor a database reader can acknowledge. Only someone with
database write access could, and they could change the rows directly anyway.

**Continuity lock (pooler-safe).** The repo targets the Supabase transaction
pooler (`database.py`: default port 6543; the pool comments say so). The lock
is therefore `pg_try_advisory_xact_lock`, held inside a transaction kept open on
a dedicated connection until the run ends:

- it uses `SET LOCAL idle_in_transaction_session_timeout = 0`;
- it is re-checked straight after locking, so an autocommit engine is refused;
- the open transaction pins one backend, and the lock dies with it;
- `close()` rolls back, and invalidates the connection if that fails.

Losing the lock never releases anything; it only prevents acknowledgement.

**Release.**

- **Native:** acknowledgement sets `returned_at`, `job_id` and `released_at`.
- **Dispatch:** acknowledgement sets `returned_at` and `job_id`. The supervisor's
  fenced `finish()` releases the claim after a coherent receipt.
- **Never-entered dispatch claim:** `finish()` releases it if `entered_at IS
  NULL` and no correlated run observation exists other than a refusal row
  (`ownership_refused` exactly `true`). Entry
  re-proves the running command and unreleased claim under the same row locks,
  so nothing can enter afterwards. The command becomes `failed` with no job.
  This covers the race where a native run briefly holds the lock while the
  adapter opens, which would otherwise strand `audits` with nothing executed.
- **Everything else retains the claim:** lost lock connection, worker lease
  loss, supervisor or child death, SIGKILL, SIGINT/SIGTERM before
  acknowledgement, a missing or malformed observation, a failed RUNNING insert,
  or a failed best-effort dry-run status update.

There is no expiry-based reclaim and no unblock tool.

**Timeouts (a deliberate change from the saved draft).** The saved draft kept
the claim after any SIGALRM timeout. The per-domain and global-budget alarms
raise `DomainTimeoutError` in the runner's own thread. So once the CLI has
rolled back and recorded FAILED, the handler frame has returned.

No seeding domain, and no `services`/`etl` helper module it imports, starts
threads, process pools or async tasks. A grep of `backend/seeding` for
`Thread(`, `ThreadPoolExecutor`, `ProcessPool`, `multiprocessing`, `Popen`,
`subprocess.`, `os.fork` and `create_task` found nothing outside tests.

Keeping the claim would have turned every nightly timeout into a permanent
block on that domain. Timeouts are therefore acknowledged like any handler
failure. Unchanged: exit status, FAILED receipt, dropped-domain record and loop
stop. The global-budget path now settles ownership before it `break`s. Reviewers
in both rounds accepted this as in-spec.

**Refusal is observable.** A refused domain writes a FAILED `ingestion_jobs`
row with `metadata.ownership_refused=true`. This is the same mechanism as a
budget-dropped domain (`_record_not_run`, generalized from
`_record_dropped_domains`). The domain stays visible in the run summary and to
freshness checks. Refusal rows are never accepted as terminal observations and
never complete a command.

**Pre-seam RUNNING rows.** A RUNNING observation without a `seeding_claim_id`
tag may be a live writer outside the seam. It refuses its domain in both native
entry and the worker's `claim()`, with **no age limit**: an age limit would be an
expiry-based takeover. Tagged rows are governed by their claim.

**Unchanged:** CLI arguments, `--all`, source-manifest scope, provenance
metadata, dry-run rollback with its preserved observation, and publication.
New observation fields: `metadata.seeding_claim_id`, and `ownership_refused` on
refusal rows. A run's observation `started_at` is now taken once ownership is
held.

**Schema.** Additive migration `e572b8c9a001` (down `e554d7c9a001`):

- **Backfill:** it copies retained Batch 7 dispatch-domain rows in as dispatch
  claims. Those whose command had `execution_started` are marked entered, with
  the digest of a random value. Nobody can acknowledge them, and they cannot be
  treated as never-entered.
- **Permissions:** enables RLS and revokes `PUBLIC`/`anon`/`authenticated`.
- **Downgrade:** refused while any history exists.
- **Constraints:** model and migration carry identical CHECKs (`_domain`,
  `_kind`, `_receipt`, `_reconciliation`, `_entry`).
- **Release:** a claim can be released only by a runner return (`returned_at` +
  `job_id`), by never having entered, or by an operator reconciliation record
  (`reconciled_by` + `reconciliation`, rejecting empty and space-only text). No runtime path writes the
  reconciliation fields.

## Entry-point coverage (finding 3)

The full table, with receipts, is in
[`batch8-exclusion-evidence/writer-inventory.md`](../../../batch8-exclusion-evidence/writer-inventory.md).

**Covered:**
- every `seed.yml` native invocation (`python -m seeding.cli seed --all | --domain X`, nightly and weekly);
- any other caller of `run_seed_command`;
- the dedicated worker → adapter path.

**Not covered** (these take no claim, write no RUNNING row, and use a different lock or none):

| Writer | What it writes | Exposure | Follow-up |
|---|---|---|---|
| `etl.worker` → `etl.backfill` → `etl/database_loader.py` | **`audits`** plus shared reference tables | runs wherever the compose `etl` service runs; `ETL_RUN_ON_START` defaults true | **#581** |
| `etl.scheduler` | same loader | no launcher in the repo | #581 |
| Bootstrap `initialize_reference_data` (every web boot, plus the weekly `seed.yml` job) | calls the `national_budget` handler directly (`backend/bootstrap.py:865`); does not write `audits` | always on | **#582** |
| AutoSeeder | reference `entities` only, rows disjoint from `audits` | on in production | — |
| Alembic `9f033e9c86d3` | one-time `audits.publishable` backfill | once | — |
| Manual scripts | `audits`, `extractions`, `budget_lines`, `loans` | by hand | — |

The light discovery scheduler writes **no** database rows (files and email
only).

What is proven, then, is mutual exclusion between native runs and between a
native run and dedicated dispatch, for every domain the CLI runs. Claiming
exclusion against *all* writers needs the quiescence listed in the inventory.

## Operator reconciliation procedure (not automated; #583)

A retained claim means "a writer may still be running or may have committed". To release it:

1. **Stop every writer of the domain, and prove it.**
   - What to stop: the `seed.yml` schedule and any manual run, the dedicated
     worker and its adapter process group, and the compose `etl` service. For
     `national_budget`, also hold off web restarts and the weekly bootstrap.
   - The proof: no process left, and no `pg_stat_activity` session for that
     role or application.
2. **Work out what committed.** Read the claim row and its observations
   (`ingestion_jobs` where `metadata->>'seeding_claim_id'` is the claim id, plus
   the dispatch command receipt when `kind='dispatch'`).
3. **Release in one transaction:**
   - set the claim's `released_at`, `reconciled_by` and `reconciliation`, with
     the evidence from steps 1–2 as text;
   - for `audits`, clear `etl_dispatch_domains.command_id`/`claim_token`, and
     interrupt the command if it is still running;
   - mark any still-RUNNING observation of that run FAILED, with an error naming
     the reconciliation.

   Never fabricate `returned_at` or `job_id`.

## Pre-merge / pre-activation gates (not executed: no production access)

Merging schedules a production migration: `seed.yml`'s `migrate` job and
`ci.yml`'s `run-migrations` on `main` run `alembic upgrade head` once Actions is
enabled. The nightly then enforces exclusion for every domain. Code deployed
without the table fails closed (every domain exits 1).

1. **RUNNING census.** Take a read-only (`BEGIN READ ONLY`) census of production
   `ingestion_jobs WHERE status='RUNNING'`, grouped by domain. Every untagged
   row refuses its domain until it is reconciled.
2. **Pooler idle cutoff.** Confirm the production connection path (Supavisor
   transaction mode or direct) has no idle-transaction cutoff shorter than the
   longest domain run. The lock was not exercised against a real pooler here.
3. **Quiescence.** Satisfy the quiescence for #581/#582 before relying on
   exclusion against those writers.

## Executed verification

**Environment.** All runs used `env -i`, keeping only `PATH`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1` and
`PYTHONPATH=<worktree>/backend`. The owned URL supplied `DATABASE_URL` and every
owned-database test gate (`BATCH7_ETL_*`, `AUDIT_TEST_POSTGRES_URL`,
`PENDING_BILLS_TEST_POSTGRES_URL`). The worktree has no `.env`.

**Processes.** Process tests launch the real `python -m seeding.cli seed …` and
`python -m admin_etl_dispatch_worker`, which spawns the real adapter, each as a
separate process group. Only the registry handler and auth transports are
inert (`tests/batch7_etl_worker_fixture/sitecustomize.py`), and every socket
except the owned loopback is blocked.

Evidence files are in `batch8-exclusion-evidence/`. Earlier failed and
superseded runs are kept.

| Evidence | Result |
|---|---|
| `baseline-native-exclusion-red.txt` (previous author, base, `--runxfail`) | 1 failed: a second committed effect from an independent CLI |
| `spec-scope-red.txt`, `adversarial/` (previous reviewers) | a forged scope ran work and cleared a retained claim; a never-entered ack released another domain's claim |
| `scope-binding-red-harness-error.txt` | my first red attempt; harness registry error, not counted |
| `scope-binding-red.txt` (saved code, new tests) | **8 failed, 2 passed** (both controls), exit 1 |
| `scope-binding-green.txt` | 10 passed, exit 0 |
| `guard-mutations.txt` | each new guard removed in a scratch copy turns its test red. Worker-generation and kind guards are redundant with the command-generation and command checks |
| `round3-regressions-red.txt` (round-2 code + round-3 tests) | **7 failed, 3 passed** (controls), exit 1 |
| `impacted-suite-1..4.txt` | superseded intermediate runs (failures explained in `independent-reviews-r2-r3.md`) |
| `impacted-suite-5.txt` | 752 passed, 1 failed (round-3 tree, before the round-3b refusal-predicate fix) |
| **`impacted-suite-6.txt`** (final tree; header carries the working-tree patch sha256) | **754 passed, 1 failed** |
| `pending-bills-pg-baseline.txt` | the one failure (`test_runtime_and_source_shaped_positive_controls`, asserts `main.AUTO_SEEDER_ENABLED is False`) reproduces identically on a pristine `git archive` of the base: pytest exit 1, 1 failed, 51 passed. Environment-dependent, unrelated |
| `sqlalchemy-2.0.23-probe.txt` / `-2.0.46-probe.txt` | 18/18 checks each, exit 0 |
| `sqlalchemy-probe-harness-error.txt` | earlier probe run with my harness error, kept |
| `critical-lint.txt` | CI critical lint (flake8 6.1.0 `E9,F63,F7,F82`, owned scratch venv): exactly 1 error, the baseline `scripts/r2_producer_acceptance.py:440` F821 (#569; other lane, PR #578). Changed non-test modules are F-clean |

The 2.0.23/2.0.46 probes cover: SQLite `create_all`; reserve, conflict and
re-acquire; UUID round trip with only the digest stored; the entry and
reconciliation CHECKs; malformed inputs; PostgreSQL UUID DDL; the partial
index; and `ON CONFLICT DO NOTHING RETURNING`.

**Final suite contents (`impacted-suite-6.txt`):** all Batch 7 and 8 ETL suites,
the admin operations suites, the ETL admin endpoints, and every test module that
calls `run_seed_command`.

**Process matrix (`test_batch8_native_exclusion.py`).** All are real separate
processes.

- **Acquisition order:** native first then dispatch; dispatch first then the
  real CLI (`--all` and `--domain audits`).
- **Concurrency:** simultaneous native/native (both argument forms); three
  concurrently launched duplicate adapters, which exit `[0,1,1]` with one
  effect; the worker blocked by a retained native claim alone, with no RUNNING
  row.
- **Normal endings:** dry-run, failure and real completion, each followed by an
  allowed next run; per-domain and global-budget timeouts, which release and
  allow the next run.
- **Kills and loss:**
  - native SIGKILL before and after commit (claim retained);
  - native lock-backend termination with a live writer (retained);
  - dispatch lock-backend termination (command interrupted, retained, native refused);
  - supervisor SIGKILL with a live orphan adapter and a new generation (retained, later commands not run).
- **Batch 7 regression:** the formerly strict-xfail
  `test_independent_native_cli_honors_dispatch_domain_exclusion` now passes
  without the xfail.

**In-process and schema tests:**

- `test_batch8_exclusion_scope.py`: forged and replayed scopes, per-guard
  acknowledgement, the DB-copied nonce, tagged vs untagged RUNNING rows, and
  the autocommit lock.
- `test_batch8_exclusion_sqlite.py`: the real CLI on SQLite.
- `test_batch8_exclusion_migration.py`: RLS and grants, retained Batch 7
  backfill (started vs not started), refused downgrade, entry/receipt/
  reconciliation CHECKs, and blank reconciliation.

## Independent reviews

| Round | Reviewer | Outcome | Record |
|---|---|---|---|
| 1 (previous author) | Spec, Standards, adversarial | forged scope / never-entered ack defects; inventory incomplete | `spec-review.md`, `standards-review.md`, `adversarial/REPORT.md` |
| 2 | Spec | F1/F2 resolved; 2 blocking (no honest release, refusal invisible) | `independent-reviews-r2-r3.md` |
| 2 | Standards | 2 blocking (RUNNING rows, transaction pooler) + 12 others | same |
| 3 | adversarial execution | 237 checks, 229 passed; 2 defects (migrated started claims released; DB-copied nonce acknowledged) | `adversarial-r3/` |
| 3 | Spec+Standards re-review | no blocking code defect; operational gates blocking; 5 hardening items | `independent-reviews-r2-r3.md` |
| 3b | adversarial re-verification of the round-3 fixes | all 8 prior failures resolved, no regressions; 125 new attacks. One low defect (whitespace-only reconciliation, a recorded limitation) and one note (refusal predicate by key, fixed) | `adversarial-r3-recheck/REPORT.md` |

All confirmed findings were repaired, each with a regression seen red first, or
explicitly retained as a limitation or gate below.

## Remaining limitations

1. **Uncovered writers:** #581 (`etl.worker` writes `audits`) and #582
   (bootstrap runs `national_budget`).
2. **Retained claims block their domain until an operator reconciles them**
   (#583). This includes cancelled or killed `seed.yml` runs. No tool exists by
   design; the schema can record an honest release.
3. **No real-pooler verification** of the continuity lock (#583 gate 2).
4. **Fail-closed strandings:**
   - a handler that calls `enter_domain` for another domain strands that claim;
   - a failed RUNNING insert retains the claim and leaves no observation;
   - on SQLite, dispatch entry is refused by a datetime `TypeError` in `fresh()`
     rather than an explicit guard (dispatch is PostgreSQL-only).
5. **Fixture ports:** the Batch 7 PostgreSQL test modules hard-code their owned
   URL. They moved from 55481/55484 to this lane's 55485 so one owned fixture
   runs all Batch 7/8 tests. Batch 7's own review normalized ports only in a
   verification copy, and Batch 7's handoff commands no longer run as written.
6. **CI skips the PostgreSQL tests:** their gates need the exact owned loopback
   URL, so hosted CI would run only the SQLite path.
7. **Hosted GitHub Actions:** not executed (disabled).
8. **Whitespace-only reconciliation text.** The CHECK rejects empty and
   space-only text. Text made only of tabs, newlines or Unicode spaces passes:
   there is no portable PostgreSQL/SQLite CHECK for it, and only reviewed
   operator action writes these columns (#583).
9. **Duplicate receipt predicate** between `terminal_observation` and the
   worker's coherence check (discretionary; unchanged).

## Issues

- Originating: #572 (open, for coordinator acceptance), #554 and #545 (open).
- Opened after all-state deduplication: #581, #582, #583.
- The baseline lint failure is tracked by #569 / PR #578 (other lane).

## Resource cleanup

See the PR description and the final report for the cleanup receipt at delivery.
Owned resources:

- the container `batch8-exclusion-afa1-db` (kept running for coordinator
  replay unless removed at delivery);
- the session scratch directory, holding helper scripts, a lint venv, a base
  archive and a mutation copy;
- the raw-evidence directory
  `…/BATCH_8_SESSIONS/NATIVE_EXCLUSION_CLAUDE_EVIDENCE/`.

Reviewer schemas were dropped by each reviewer (receipts are in their folders).
