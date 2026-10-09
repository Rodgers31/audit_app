# Independent adversarial execution review

Origin: #554; parent #545; frozen Batch 7 `SPEC.md` (2026-10-03).
Reviewed source: `e98a4be3998f7da4e2326a068802a879e393fb97` versus pinned
`f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`. The first executed pass also
included the author's uncommitted capability commit-error reset fix.

Reviewer owned only `backend/tests/test_batch7_etl_adversarial.py` and this
report. No product files were edited by the reviewer.

## Exact command and isolation

From `/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app`:

```sh
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app/backend \
  DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  BATCH7_ETL_ADVERSARIAL_DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest -q \
  -p no:cacheprovider backend/tests/test_batch7_etl_adversarial.py
```

The password above is explicitly inert owned-local configuration. PostgreSQL
reported `PostgreSQL 16.15 on aarch64-unknown-linux-musl`. All review writes use
engine `connect_args={"options": "-c search_path=batch7_adversarial"}`. The
review fixture creates exactly AdminAuditLog/IngestionJob/Command/Worker/Domain
tables, truncates only those tables in its own schema, and drops only that schema
on teardown. It does not alter public fixtures or stop the shared owned container.
Python 3.13.9 is reused read-only; no packages installed. No product lifespan,
primary dotenv, live settings, source fetch, or service/deployment activation.

## Initial executed findings

Actual first-run result:

```text
8 failed, 56 passed, 2 warnings in 1.81s
```

1. **Direct replay accepts nonboolean intent.**
   `test_direct_replay_rejects_nonboolean_semantic_intent` creates a valid durable
   acceptance and calls `accept(db, ACTOR, "oag",
   SimpleNamespace(dry_run=bad, dispatch_generation=None), str(key))`.
   `bad=0`/`0.0` matches accepted `False`; `bad=1`/`1.0` matches accepted `True`.
   All four calls returned success rather than rejecting malformed input:
   `Failed: DID NOT RAISE any of (ValidationError, HTTPException, ValueError,
   TypeError)`. FastAPI body validation protects HTTP requests; this is a direct
   function boundary bypass. No second audit/job/execution occurred.

2. **Completion trusts incoherent correlated observations.**
   `test_finish_rejects_incoherent_correlated_completed_observation` inserts one
   real local IngestionJob tagged with the command UUID and claim token, marks
   the already claimed command `execution_started=True`, and calls
   `finish(factory, generation, identity, token, 0)`.
   Each input returned `True`, persisted command `status="completed"`, linked
   `job_id=1`, and released the protected domain:

   ```text
   started_at=2100-01-01, finished_at=2100-01-02
   started_at=2000-01-01, finished_at=2000-01-02
   errors=['INERT_PRIVATE_FAILURE'], status=COMPLETED
   items_processed=-1, status=COMPLETED
   ```

   The timestamps are impossible relative to the claimed command and current
   database clock. Nonempty failure diagnostics and negative processed counts
   contradict a trustworthy completed observation. Correlation tokens alone
   did not establish valid execution evidence. The author was notified with
   the exact retained test names before further verification.

The capability storage-commit failure control passed against the author's reset
delta: `available=False`, null generation/timestamps, unavailable worker and
all unavailable sources after a simulated private commit failure on a real fresh
PostgreSQL lease. The Standards reviewer independently identified that defect.

## Executed compatibility and hostile-input controls

The first run executed rejection/receipt controls for None and wrong containers;
strict bool/integer projection, NaN/infinity/negative/zero history bounds;
missing/mismatched/unfinished observations; failed and completed-with-errors
observations; malformed exit-code types; unknown generation and claim tokens;
stale and future worker leases; direct history-call guards. No completed success
was obtained from those controls.

Actual native-adapter tests were then added. Their first run (`-k actual_adapter`)
returned `2 failed, 4 passed, 64 deselected in 0.44s`; both failures were an inert
fixture import-order collision (`ValueError: Domain 'audits' already registered`)
before native work. The fixture now imports the actual audits scope before
replacing its handler. This failure is not claimed as a product defect.

## Independent final rerun

The author reproduced all eight red cases separately before fixing them; retained
author receipts are `adversarial-author-red.txt` and
`adversarial-author-green.txt`. The reviewer then executed the exact full command
above independently after those fixes and the inert fixture import-order repair.
The first independent final rerun produced `70 passed, 3 warnings in 1.88s`.
After Standards tightened the rejection assertions and the author repaired
valid legacy direct-route dictionary compatibility, the reviewer independently
repeated the full exact command. The final actual result was:

```text
70 passed, 3 warnings in 1.94s
```

No remaining success-on-bad-input defect was found in the executed cases. The
capability failure reset, nonboolean replay guard, and observation coherence
guards all passed. Known valid failed observations remained failed receipts.

The six actual native-adapter controls ran `execute()` and the unchanged
`seeding.cli.run_seed_command()` with one inert registered audits handler:

- A real-mode handler inserted one `inert.adversarial.effect` local audit row;
  dry-run rolled back that same insertion (one versus zero persisted effect).
- Both modes produced exactly one correlated native IngestionJob and a completed
  command with the matching observation ID.
- Reinvoking the same adapter claim returned exit 1, left one handler invocation,
  and produced no duplicate observation or effect.
- Unknown command/token/generation and an empty registry returned exit 1 before
  invoking the handler or creating an observation.

The runtime blocked Python socket transport except owned PostgreSQL
`127.0.0.1:55481` while exercising the native handler. No native source handler
was called. The reviewer ran the adapter directly; dedicated worker subprocess
death/restart/heartbeat interleavings remain covered by the author's separate
process suite, not independently certified by this report. Native CLI-wide
exclusion remains the previously tracked #572 activation gap; this review did
not change or close that issue.

Final executed source identities (SHA-256), with HEAD still
`e98a4be3998f7da4e2326a068802a879e393fb97` and author fixes uncommitted:

```text
99f932555be6c13d58af987acf784cff48b6b04d847d3e0fdcfc04708aec1550  backend/admin_etl_dispatch.py
b2366dc63a02ab21b516083bc570c63bef1f1f135889fa1df04f4341a852b384  backend/admin_etl_dispatch_worker.py
64094148d82155cc400e6afe00543704fbc6113616e50983f9f748e59f05688a  backend/admin_etl_dispatch_adapter.py
f4286680982572a0d148a4fba458e95bd6a0fa3267ff97fe406b1c08872ab79b  backend/routers/etl_admin.py
5b176aad19f84abc3dad4ff6d838f3da76e28830888d28ba59e4013c484cb6e9  backend/tests/test_batch7_etl_adversarial.py
```

The final independent run includes the tightened assertions: direct replay must
raise safe HTTP 422; incoherent observations must return False, persist
interrupted/execution_unverified with no job ID, and retain the occupied protected
domain. All eight strengthened regressions passed.

The reviewer also independently executed the final router delta without touching
storage. With the same clean environment above and no dispatch enablement,
`trigger_etl_run('oag', body, ACTOR, BombDb(), None)` was called using a BombDb
whose every attribute access raises AssertionError. Actual results:

```text
None 503
{} 503
{'dry_run': False} 503
{'dry_run': True} 503
{'dry_run': 0} 422
{'dry_run': 1} 422
{'dry_run': 'false'} 422
{'extra': 'INERT_PRIVATE_FAILURE'} 422
[] 422
False 422
direct_router_shape_and_default_off_controls=10 passed; storage_accesses=0
```

This verifies the direct route preserves valid default-off 503 calls and rejects
malformed dictionaries/containers before acceptance. These ten additional
controls ran inline and are separate from the 70-case pytest count.

Post-run SQL `SELECT count(*) FROM pg_namespace WHERE
nspname='batch7_adversarial'` returned `review_schema_count=0`. Schema teardown
completed after every invocation. No reviewer subprocessor or server was
launched; no process or connection remains. The shared owned PostgreSQL container
was left running for the author. Public data, other lanes, and primary checkout
were untouched. Existing SQLAlchemy/python-json-logger deprecation warnings
were reported by pytest; no hosted/deployed readiness claim is made.
