# Independent adversarial execution, Batch 8 #572

Pinned HEAD: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, tree `f22a430a4402d79867da63ad97db8c8d474d3a71`. The author diff was uncommitted during review. Exact source digests and snapshot are retained as `source-identities-01.txt`, `reviewed-diff-01.patch`, and `exclusion-01.py`.

Executed on macOS 27.0.1 arm64, CPython 3.13.9 and SQLAlchemy 2.0.46 using the existing runtime read only. All persistence/effects are owned isolated schemas beginning `batch8_adversarial_` within the owned loopback PostgreSQL container `batch8-exclusion-afa1-db` (55485). No author pytest fixture, public-table resets, provider/publisher call, remote service, author process mutation or runtime installation was used. The initial agent setup contained no test execution; it is not counted as a pass.

Command (append desired `> run-NN.log 2>&1`; capture its actual exit status):

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/Users/roger/.codex/worktrees/afa1/audit_app/backend DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker /Users/roger/Documents/projects/audit_app/venv/bin/python batch8-exclusion-evidence/adversarial/execution_checks.py
```

Only the actual native runner's session factory, registered handler and builtin-loader are replaced to provide inert local effects. Ownership and adapter/worker code run unchanged. The handler inserts one owned inert counter row and returns a `DomainRunResult`; real native commit and dry-run rollback paths run.

## Findings in initial author implementation

`run-01.log`: exit **1**, 53 checks executed, 51 passed, 2 failed. Expanded `run-02.log`: exit **1**, 91 checks executed, 89 passed, same 2 failures. Expanded `run-03.log`: exit **1**, 99 checks executed, 97 passed, same 2 failures. `results-02.json` and `results-03.json` retain the expanded structured results; `execution_checks-03.py` retains the exact 99-check script, with `source-identities-03.txt` proving the author source had not changed since the initial reproduction.

1. **Uncorrelated scope bypasses a retained native claim.** Create a native durable claim for `audits`; ordinary actual CLI invocation rejects it (`exit=1`, effects unchanged, claim retained). Construct `DomainExecution(factory, 'audits', retained_native_id)`, call `open()`, and invoke actual `cli.run_seed_command` within `dispatch_scope(execution)`. No dispatch command exists and no authenticated adapter was invoked. Observed `exit=0`, inert effects increase from **1 to 2**, and the retained native claim is released. Expected no handler invocation/effect and claim retained. The new scope path checks only a process-local object's engine, domain, unused state, and live advisory lock; it does not require the adapter's legitimate durable correlation.

2. **Acknowledgement can release another domain's claim without entry.** Create a retained native claim for `retained_domain_a` and a coherent terminal job correlated to it. Construct `DomainExecution(factory, 'unrelated_domain_b', retained_A_id)`, call `open()`, then `acknowledge(A_terminal_job_id)`. Observed acknowledgement accepted and A released while `execution.entered=False`; the held advisory lock was B's lock. Expected `DomainOwnershipError` and A retained. No native runner invoked or completed in this call. This weakens the domain continuity proof by failing to bind the object to the claim's domain and its prior authenticated/acquired entry.

The author was notified with exact reproductions before fixes. No implementation changes were made by this reviewer.

## Executed positive and negative controls

Actual native committed effect and dry-run rollback; malformed domain and identity shapes; missing/stale/noninteger terminal job IDs; absent/wrong metadata and completed error shapes; hostile counts including booleans, NaN, infinity and out-of-range values; ordinary CLI flags cannot impersonate a retained claim; duplicate acquisition rejects; malformed scope shapes do not start the handler; a forged dispatch terminal observation without a synchronous return acknowledgement is interrupted with the durable claim retained; malformed child exit-code types and stale command/token/generation do not release; valid real adapter invocation, duplicate adapter rejection, valid supervisor finish and subsequent native execution succeed.

Further executed controls: terminating only the reviewer-owned advisory-lock PostgreSQL backend causes direct acknowledgement to reject (`OperationalError`) and subsequent actual native invocation to fail without an inert effect; explicitly uncertain execution rejects acknowledgement and retains native exclusion; a valid actual adapter completes, its worker lease expires, and supervisor `finish` rejects while retaining authority and blocking the next actual native runner. Each scenario uses a separate owned schema; no claim cleanup/release is inserted to make these cases pass.

Scope limits: these independent checks exercise direct/public Python entry points and real PostgreSQL transactions; they are complementary to, and do not replace, the author's separately launched worker/native process suite. This report makes no hosted, production, provider or migration acceptance claim.

## Reverification and cleanup

Pending author fixes and independent rerun. All raw failed runs remain retained. After notifying the author, the reviewer ran `cleanup_schemas.py` with the same clean environment/read-only runtime. `cleanup-01.log` records exit **0**, exactly **10** reviewer-owned schemas dropped, and **0** of those schema names remaining. No author/public schema, author process, provider, or shared runtime was changed. The script closed/disposed all owned database connections; it spawned no child server or worker. No sentinel was touched on failed execution.
