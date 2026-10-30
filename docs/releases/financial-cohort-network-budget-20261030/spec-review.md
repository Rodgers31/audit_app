# Final candidate 7 Spec review

**Scoped pass. No remaining findings.** The query consolidation preserves the reviewed source/cursor/lock invariants, and the increased finite budget completes the independently exercised high-latency baseline path. This review does not authorize production, publishing or worker activation.

## Exact input and carry

`cohort-query-candidate-7`: 5,814 files; mapping SHA256 `8438067e9b6b05b6efb47556a1e1da21445a9c9937be4f1d06a4dac782942860`. Every file hash and exact file set verified before and after execution. Relative to candidate 5, the only new product changes are `backend/seeding/generation_limits.py` and `backend/seeding/cli.py`. The three query product files are byte-identical to candidate 5.

The earlier 34 independent candidate-5 query/lock/job/control/marker cases remain carried for their query-invariant scope, with their actual candidate-5 input receipt preserved. This is **not** an assertion that the whole snapshots are identical or that all 59 controls ran on one hash. Candidate 7's altered deadline, CLI and cohort/replay behavior was executed afresh below; candidate-5 timing did not claim adequacy of 120 seconds.

## New execution: 25 passed, zero failures/errors/skips

| Current-candidate execution | Count | Result |
|---|---:|---|
| Independent typed-deadline, cleanup rounding, dry/default-OFF, started/confirmed receipt and actual whole-CLI caller controls | 22 | Passed |
| Actual retained writer → full baseline with 130 ms sleep after every SQL execute, then fresh retained-job replay | 1 | Passed |
| Actual one-second SIGALRM + real PG outcome write/readback, interrupted financial/report phases | 2 | Passed |

The real high-latency full baseline completed **46/46** in **186.508 seconds**, with **1,366 SQL execute calls**, zero refusals and zero drafts. It stored a v2 completion claim with 46 exact members. The caller supplied an actual 300-second original global deadline, clamping the CLI envelope to 290 seconds; the run finished inside it. A subsequent fresh retained-ingestion job completed as **46 unchanged**, zero baselines/drafts. No publication or target row was created.

The original deployed-equivalent RED remains at `../profile-130ms.json`: after 121.754 seconds it conservatively reported 21 confirmed baselines, zero drafts, and a generation deadline failure. This is a controlled RTT-sensitivity reproduction; it does not measure production latency.

Actual whole-CLI tests spent 80 or 95 virtual seconds in an inert owned source handler under the original 100-second global deadline. The post-commit phase received 10 seconds or no execution budget respectively, and the committed ingestion status/count/errors remained unchanged. The exhausted path did not arm a zero-second alarm or call a generation phase; it recorded known zero work.

The real SIGALRM tests then verified the complementary case: an already-started, interrupted financial phase records unknown counters; an interrupted report phase preserves the exact confirmed partial financial result and marks report progress unknown. Both write/readback paths preserved original source metadata, terminal status, timestamps, counts and errors. The real alarms fired after approximately one second; no worker/provider command was involved.

## Budget assessment and limits

600 seconds is a finite source-specific financial cap, with report phases still 30 seconds and explicit selector/receipt reserve. The code clamps its whole generation envelope inside the original caller deadline minus the existing 10-second cleanup allowance. The source domain/global/CI step/job timeout settings are unchanged by this delta. Invalid/nonfinite/boolean deadline inputs refuse before factory/alarm work; dry/default-OFF paths open no factory in the exercised boundaries.

The derivation cites the separately measured 2,880-call changed cohort at 150 ms/call (432 seconds) plus finite protocol/CPU/receipt headroom. This reviewer independently executed the baseline and fresh replay at 130 ms/call; **the worst changed-account/worker 150 ms execution belongs to the separate Standards receipt**, and no independent claim for that run is made here. Driver-execute latency omits separate connection, BEGIN/COMMIT and pool pre-ping messages; local fixtures are not production source acquisition or a production performance guarantee.

## Provenance and cleanup

All project execution used the frozen source read-only, owned capped offline Docker and a separate guarded PostgreSQL 17/Alembic-current fixture. Commands, JUnit, source-before/after hashes, full manifest checks and per-statement call profiles are adjacent. No product files were edited. The owned `rollout-spec-query5-pg` container was removed successfully and its mode-600 private credentials were deleted; root/other fixtures were untouched.
