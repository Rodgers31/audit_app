# Candidate 5 query-only Spec review

No remaining findings in the three product-file query-consolidation delta. This is scoped safety/query-count acceptance; the unchanged 120-second budget is **not** accepted as sufficient at observed network latency.

All 5,812 manifest entries verified against mapping SHA256 `c7ac48ad2c46cd68646cebf525df7895666d5984b43ecc2070e2c0516ed62a4b`. Independent delta inventory confirms only `native_report_authority.py`, `native_report_observations.py`, and `social/generation/service.py` change product behavior from frozen recovery-review-4.

Executed 34 independent cases on an owned guarded PostgreSQL 17/Alembic-current fixture in capped network-isolated Docker; zero failures/errors/skips:

- 20 current-job shape/head/audit scoping controls; exactly one SQL execute per `_job`, with a separate audit scoped recheck still refusing a matching newer auditee.
- Three tighter/default timeout and transaction-local restoration controls, plus two real contended mutex waits (65 ms inherited and default 2-second cap). These verify the MATERIALIZED bound takes effect before the advisory wait.
- Four missing/existing generation/delivery control concurrency cases, preserving one row, OFF delivery defaults, lock order and one/two-query existing read paths.
- One real authority-lock wait with job completion after transaction start, proving the statement clock validates the newly visible committed job.
- Two actual-qualified source-marker initialization cases, including competing missing-root transactions and existing-root read without an insert.
- One real 46-row complete baseline and retained unchanged replay, preserving the completed marker membership and no new drafts.
- One full retained-baseline query profile: 46 completed baselines, zero refusals/drafts/publications/targets, **1,366 SQL execute calls**, 1.893 seconds with the local driver. Forty-five consumes use 28 calls; the first uses 32 because both delivery controls and root are initially absent. With those existing, this shape implies 1,362 calls. Original identical profile used 1,784 calls.

No SQL/source qualification, dependency-witness, cursor-integrity or source-eligibility check was bypassed in these executions. The missing branches retain insert-on-conflict and reselect, and the job SELECT retains a source/domain-qualified newer-head EXISTS. The two financial/report job timing points remain. Scoped audit freshness remains distinct from global freshness.

The original 130-ms-per-execute RED remains in the parent evidence directory. Query-only savings still imply about 177 seconds for a complete baseline at that latency before additional wire overhead. A final budget/performance candidate needs its own worst-branch execution evidence. No candidate-5 high-latency positive, production throughput, deployment or worker activation claim is made.

Commands, XML, before/after source hashes, manifest verification and statement-by-statement profiles are adjacent. No product files were edited by this reviewer. Owned fixture remains reserved for the forthcoming bounded budget delta and will be cleaned afterward.
