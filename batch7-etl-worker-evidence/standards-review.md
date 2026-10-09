# Independent Standards review

Reviewed source: `e98a4be3998f7da4e2326a068802a879e393fb97`.
Base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`.
Diff: `git diff f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d...e98a4be3998f7da4e2326a068802a879e393fb97`.
Origin: #554; frozen Batch 7 SPEC.md and current issue body read.

Standards consulted: `.github/copilot-instructions.md`, `TESTING_GATES.md`,
`CONTEXT.md`, and code-review, git-workflow, audit-api-fastapi,
state-persistence-invariants and verify-boundary-shapes skills. Tooling-enforced
style issues excluded.

## Documented violation

**[P1] Capability fails open after commit failure — resolved in follow-up.**
`backend/admin_etl_dispatch.py:169-175` set `available` and lease fields before
`db.commit()`, then reset only `worker` on failure. A failing commit returned
`available:true`, worker `ready`, non-null generation and enabled `oag`.
This violates verify-boundary-shapes §2: “Gates fail closed; unknown shapes are
untrusted shapes.” An independent direct call against the original function
failed its unavailable assertion. Author's mounted PostgreSQL regression
`test_capability_transaction_failure_cannot_certify_ready` retained actual red
and green receipts (`capability-commit-red.txt`, `capability-commit-green.txt`).
Follow-up clears availability, generation and both lease timestamps;
independent direct replay passed. No other documented-standard violations found.

## Judgment smell

**Possible Duplicated Code [P3] — resolved.** The original worker duplicated
child terminate/wait/kill cleanup. Follow-up delegates both paths to
`stop_child`; inspected implementation preserves timeout/escalation behavior.

## Final source recheck

Uncommitted follow-up deltas inspected against the reviewed SHA:

- `admin_etl_dispatch.py` blob `3ba242157bd88e65e5d82647d777cc4d7457e48a`
- `admin_etl_dispatch_worker.py` blob `a5fc5e8c0c99039f1099829872f263eca87ebae6`
- unchanged adapter blob `2ea040c52770dae16166b7868022c7961008604f`
- `routers/etl_admin.py` blob `27b604e2c6b9eaba1364822d7aa6bafd172cda35`

UTC AfterValidator rejects naive values and normalizes offsets. Independent
direct checks passed for UTC output and eight nonboolean intents returning
HTTPException 422 before storage. Stronger correlated-observation gate validates
time/count/error shapes and retains exclusion on uncertain receipts. Inspected
author red/green receipts (eight boundary cases) and actual lost-ack/non-UTC
PostgreSQL controls. Suggested tightening two adversarial test assertions;
author changed them to exact 422 and interrupted/execution_unverified/no-job/
occupied-domain outcomes, inspected in final delta.
Final router normalization validates direct dictionaries through TriggerBody;
malformed bodies return static 422. Independent storage-free replay confirmed
four valid legacy/default-off shapes return 503 and three malformed shapes 422.
Author compatibility receipts retain two red/four green cases. No new Standards
finding from this delta.

## Limits

Review was read-only except this report; no product lifespan, install or shared
PostgreSQL mutation performed. One attempted isolated pytest check failed at
conftest's SQLite engine options before collection; direct checks passed.
Hosted/full-suite gates remain unexecuted as disclosed. Native CLI exclusion is
the reproduced residual shared seam #572, not certified completion. Remaining
Standards findings: zero documented breaches and zero unresolved smells.
