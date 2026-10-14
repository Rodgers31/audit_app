# Batch 13 Lane A — truthful bootstrap workflow outcomes

Draft PR: https://github.com/Rodgers31/audit_app/pull/655. Assigned accepted base
`c8970e3953717fc0f0ca3a54e22f7e3e509eec0f`, tree
`1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8`. Implementation commit
`eae16293aed64df1dba92cf45d24d6aa8e307754`. The final delivery head is the commit
containing this handoff, obtained with `git log -1 --format=%H --
docs/admin/implementation/BATCH_13_A_HANDOFF.md`; the external `DELIVERY_V1.json`
binds its exact immutable head/tree and PR readback after publication. No rebase
or alternate source base was used.

Owned chat: `01a1372d-e734-72c2-b955-705f28bc8185`, “Batch 13: bootstrap outcome
reporting”. Checkout: `/Users/roger/.codex/worktrees/ebbf/audit_app`, exclusive
branch `codex/batch13-bootstrap-outcomes`. The recorded coordinator exception in
`NEXT_AUTHORS_V1/OWNERSHIP_RESOURCES.md` permits only the weekly/manual bootstrap
body in `seed.yml`, narrow tests/docs and this handoff. Product bootstrap,
ownership, data, migrations, dependencies and other workflow jobs are unchanged.

## Behavior and producer contract

Both weekly schedule and manual `run_bootstrap` enter the same job/body. It now
prints the existing success line only when the actual initializer returns
literal `True`. Any other return logs “Bootstrap seeding deferred or incomplete;
inspect bootstrap logs and retained ownership before retry” and exits 2.
Ordinary exceptions retain their traceback and Python exit 1. Unchanged forced
process exits/signals retain their Python/shell semantics; this is not a new
supervisor for `SystemExit`, process death or `os._exit`.

`initialize_reference_data` returns False both before effects when another
non-budget owner prevents admission and after reference work when budget
execution is refused/incomplete. False therefore cannot mean “nothing ran” in
every case. True requires the existing committed reference/budget completion
and acknowledgement contract. The wrapper acquires/releases no claims, does
not fabricate terminal observations and does not retry or force admission.

Production caller inventory searched across backend, scripts and workflows:
the weekly/manual wrapper is repaired; `main._startup_sequence` already consumes
writer permission and separately proves required references; manual/force calls
share unchanged initializer ownership. Test callers remain test controls.
`_seed_national_budget` has one product caller inside the initializer. No other
unconditional workflow success print was found. The policy in #583 remains the
operator/production release gate.

## Executed local evidence

External evidence root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH12_CONTINUATION_V1/NEXT_AUTHORS_V1/A_bootstrap_outcomes`.

The exact unchanged base wrapper was observed red before repair: the first
16-case shell cohort had 12 intended failures and four passes; actual
PostgreSQL base controls reproduced False/exit 0/printed success for retained
deferral and incomplete budget. Fresh calibrated base packets preserve those
same outcomes with the corrected recorder. No unexecuted path is acceptance.

The focused final-source selection contains 64 cases per supported runtime:
20 new exact-shell wrapper controls plus unchanged bootstrap deferral,
observability, reference ownership and caller-transaction controls. Both
prepublication cohorts passed all 64 with zero skips/errors/failures. The new
controls execute normal and optimized Python children, including malformed
truthy returns, missing/syntax-invalid imports and actual exceptions. These
controlled modules establish wrapper behavior; they are not integration proof.

Real PostgreSQL controls use the exact extracted Python body, actual unchanged
bootstrap and actual packaged national-budget handler. No initializer, provider
or domain handler is substituted. Each case executes the accepted migration
chain to explicit `e602b11a0001` and reads that revision. The separate additive
audit target `a611b12a0001` is not applied or certified here.

| Actual case | Exit/result and stored effects |
|---|---|
| Admitted | True/0; one printed success, 47 county references, two completed observations and all 17 acquired claims released by the real producer |
| Retained audits deferral | False/2; warning, no success; the same native claim retained, no fabricated bootstrap job, complete before/after public rows and sequences equal |
| Missing claim schema | Real UndefinedTable/1; no emitted success/deferred outcome, complete rows/sequences equal |
| Incomplete budget | False/2; reference effects and 47 counties remain, completed reference/failed budget observations, one budget claim retained; no success claim |
| Empty migrated baseline | Real CheckViolation/1; early country/fiscal effects and failed bootstrap observation, all 17 claims retained; inherited #652 remains separate |

Admitted/incomplete controls start with a legitimate migrated legacy source
document: URL null and status FAILED, as migration 3c prescribes. This avoids
fabricated available URLs. The empty migrated case remains mandatory and exposes
the genuine inherited availability violation; it is not hidden by preparation.

Every migrated census covers all 53 public tables and all 30 sequences. The
final recorder includes all `pg_sequences` fields plus actual sequence relation
`last_value`, `log_cnt` and `is_called`. Earlier v5/v6 receipts only measured
exposed `last_value`; their narrower scope is retained. Runtime identities are
actual Python 3.13.9/SQLAlchemy 2.0.54 and Python 3.12.14/SQLAlchemy 2.0.23, with
all declared backend constraints checked. “Minimum” describes that ORM/Python
cohort, not every transitive dependency minimum. Native PostgreSQL is verified
17.6 on macOS arm64; no Linux amd64, hosted Actions or deployed claim follows.

Independent Spec executed 60 hostile shell controls; Standards executed 296
controls across dash-c and Actions-style script-file shells. Both found no
product blocker and checked actual database/profile/census bytes. Their counts
and repeated runtime selections overlap and are not summed as unique coverage.
Their reports, final published-byte replay, full source inventory and normal/-O
receipt-reader refusal controls are bound externally by `DELIVERY_V1.json`.

## Failures, resources and cleanup

START/STATUS and every historic failure remain immutable evidence: original
180-second storage timeout; first corrected-guard cache clock mismatch;
missing Homebrew server binary; probe syntax/setup failure; migrated cold-start
constraint failure; and parser failures that mistook quoted source in exception
tracebacks for emitted outcomes. Exact emitted lines are now required. One
minimum-labeled file actually used the current interpreter; its measured
identity remains intact and it is excluded from minimum-runtime acceptance.

The packet reader also detected Git quoting four inherited Unicode archive
paths. Final recorders use NUL-delimited Git names and filesystem decoding and
refuse missing measured files. Old inventories are explicitly qualified;
protected archive/cache inputs were not removed or masked.

Corrected storage guard `a23de901378c4afbac8ff3f6b8e08722ef58ada66bc9dd4154c83f44b47bed5c`
uses the unchanged 180-second bound/original baseline/shared 10 GiB budget.
Fresh before/after phase receipts are external; no rebaseline or cleanup-plan
reuse occurred. Shared Python environments and the hash-verified native 17.6
installation were borrowed read-only. No environment/repository copy or install
was made, and the dirty primary/peer checkouts were untouched.

Each rehearsal owns a unique `batch13_bootstrap_outcomes_<nonce>` OS-temp
cluster/databases at literal 127.0.0.1:55564 under role `batch13_bootstrap`.
Binary hash, cluster system ID, actual principal/database, PID and data path are
bound before exact disposal. Every case DB is dropped/read back absent, that
owned server is stopped, its PID file disappears, the temporary tree is removed
and the reserved port is independently bindable. No Docker resources, broad
process kill, prune or peer cleanup is used. Raw stdout/stderr/census/JUnit and
generator/input/source hashes remain externally preserved.

## Remaining work and coordinator handoff

Implemented/locally verified: the bounded #639 workflow-result repair. Global
CI/Actions activation, combined hosted acceptance, review/merge and issue
disposition remain coordinator-owned. PR655 stays draft. #545/#583/#554/#611
retain their deployed/operator/release criteria; this source delivery does not
certify those parents. No production migration, reconciliation, claim release,
backend deploy, provider/worker activation, paid review or financial source
publication occurred.

New deduplicated #652 is the inherited fresh-baseline bootstrap source-document
availability violation. All 332 issue bodies and 564 complete comments were
inspected before filing; exact source reproduction, impact and limits are in
that issue and its readback. Repair is outside this lane's wrapper ownership.

Consume the external final delivery binder and fresh actual PR head/readbacks
before integration. Preserve the exact warning/exit contract and all tests;
run the unchanged combined required gate on the integrated immutable source.
Production bootstrap activation still needs its separate reviewed release
decision and #652 disposition. Do not interpret exit 2 as authority to clear a
claim or automatically retry.

Proposed coordinator skill lessons: match emitted outcome lines rather than
quoted traceback source; prove the real migrated schema rather than only ORM
metadata; bind cohorts to actual runtime identity; and use NUL-delimited Git
inventories so Unicode paths cannot disappear behind an existence filter.
Concrete reproductions and failed receipts are preserved here; no shared skill
file was edited.
