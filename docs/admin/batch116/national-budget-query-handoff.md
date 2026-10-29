# B116 national-budget metadata invalidation — issue 831

Base `f33cdcfb3afbcb7d1634f39b4df7e0fe92d0025e`; branch `codex/b116-national-budget-831`.
Worktree `/Users/roger/.codex/worktrees/b116-national-budget-831/audit_app`.
Related original-plan issues: #831, #802, #800, #699. No issue-closing directive is included.

## Change and contract

Missing-proof native authority invalidation reads only the locked source ID, JSON container type and domain-key presence. It removes the single JSON path in PostgreSQL rather than assigning a full metadata object. Absent bindings preserve existing null/absent/empty metadata without a redundant write. Present bindings, including null/false/empty values, are removed; sibling domains and unrelated metadata remain. Malformed authority containers refuse explicitly. The ORM metadata attribute expires on every successful path, preventing a pre-lock snapshot from being reused.

The existing bounded transaction advisory/domain lock, source row lock and constraint/readback checks remain. The national writer takes the domain lock before any source/financial autoflush, coalesces missing-proof operations per distinct source, and executes a pending invalidation before a later positive proof. No source/authority snapshot is cached across those boundaries. The final invalidation reads current PostgreSQL state. Both writing and no-write paths force deferred constraints and recheck narrow projections before success. No commit is introduced.

Positive capabilities still run the existing intact capability/receipt, source identity, country, artifact, running-job and retained-origin checks individually. Positive-authority persistence is not given a cross-row cache or a new source qualification rule. Old immutable receipts and job lineage remain intact. This repair optimizes missing-proof invalidation; it does not claim bounded full-metadata reads for positive report admission.

## Executed evidence

Private evidence root: `/Users/roger/.codex/visualizations/2026/10/28/01a18474-8655-7252-9ac0-696cf07b214e/B116_831`.
Each run retains command, read-only source snapshot/hashes, stdout, JUnit, actual optimization/UID, and a generator/entry-hash-bound result read back from disk.

- Original unchanged27-case cohort: `baseline-normal-v2` and `baseline-optimized` each **12 failures /15 passes**, no skips, at the verified base.
- Corrected permanent bounds/shape controls against the original product: `regression-red-v2`, **21 failures /18 passes**. Early missing-fetch-date test setup failures remain diagnostic only.
- Author stale-ORM no-op regression: `no-op-stale-red`, **1 failure /1 pass**, repaired by expiring metadata on absent bindings.
- Independent findings reproduced by the author: `review-findings-red` **2 failures**; permanent `permanent-review-red` **3 failures**. Refined real-PG lock witness: `permanent-lock-deterministic-red` **1 failure**, showing the advisory/financial transaction cycle. The repaired witness requires a real advisory wait before financial lock acquisition and both writers completing.
- Final complete affected selection: `published-normal` / `published-optimized`, **155 passed per actual Python mode**, no skips/errors/failures. These include the original27,42 acquisition cases in total,8 permanent ordering/reader/concurrency cases, and105 existing native parser/PG/lineage cases. Counts overlap with earlier runs and are not added.
- Independent Spec and Standards reviews are recorded separately in `spec-review/FINAL.json` and `standards-review/FINAL.json`; Spec8 and Standards32 pass in each actual Python mode, with zero remaining findings; their reports identify executed hostile cases and exact final source hashes.

All execution uses cached image `sha256:7ad6f8ec1ad4062d071ffeb31abbf2d3947b265075f7e92de2c4440b37a1dd64`, read-only snapshots, UID65534, network none, no credentials or Docker socket, dropped capabilities/no-new-privileges, finite CPU/memory/PID/filesize/tmpfs/wall limits. Actual Python3.12.15 modes0/1, FastAPI0.156.8, Starlette1.9.0, SQLAlchemy2.0.55 and PyJWT2.15.1 are read back. Both private PostgreSQL fixtures are loopback-only; the social fixture uses unchanged migrated head `a756b20a0001`. There is no hosted CI/production acceptance claim.

## Measurements

The same40 financial rows share one source with an unrelated64KiB field. Decoded selected-value estimates exclude protocol/TLS/pooler overhead.

| Source state | Baseline source SELECTs / writes / bytes | Final source SELECTs / writes / bytes |
| --- | --- | --- |
| No authority |121 /1 /5,252,089 |4 /0 /2 |
| Stale national binding plus sibling |121 /1 /5,254,240 |4 /1 /23 |

The final four reads are resolution, row lock, pre-constraint scalar projection and post-constraint scalar readback. The same bounds hold for one row. Returned columns contain IDs and scalar projection aliases, not metadata. The unrelated padding, sibling binding, acquisition fields, old Extraction JSON, financial values and qualification state are asserted independently after commit. The actual public budget-lines reader returns identical response objects before/after authority invalidation, including actual spending50/51; no figures are substituted or published by this repair.

## Independent review disposition

| Axis | Confirmed finding | Result |
| --- | --- | --- |
| Spec | Delaying missing-proof work could let financial autoflush precede the domain lock and deadlock against a positive writer | Domain lock now precedes any writer query/autoflush; permanent actual PostgreSQL wait/lock witness executed red and green |
| Standards | Absent-key no-op skipped deferred constraint completion/readback, allowing a queued trigger to restore stale authority at commit | No-write path retains the constraint barrier and narrow readback; permanent real deferred-trigger cases executed red and green |

No other actionable review finding is accepted without executable evidence. Early fixture setup failures, the reviewer's initially overstrict null expectation and a terminal-newline source-drift refusal remain historical, not passing final evidence.

## Coverage and remaining gates

| Contract | Supported evidence / limit |
| --- | --- |
| Missing or stale authority, fixture/live acquisition, archived/history retention, large unrelated metadata | Actual isolated PostgreSQL cohort; no new source acquisition is inferred from fixtures |
| Current identity, retained-origin/job lineage and concurrent replacement | Existing real-PG locked-current/retained lineage plus independent actual row-lock wait |
| Mixed proof/invalidation ordering and rollback | Permanent multiple-order and transaction/financial-refusal controls; old evidence retained |
| Financial results/qualification | Stored values and actual public reader unchanged; no numeric adapters or new source rollout |
| Shared native helper | All four existing native domains and falsy bindings; actual SQLite branch independently exercised |
| Production/browser/activation | Unperformed here. Coordinator owns deployment/integration, Chrome qualification and any separately authorized production acceptance. Publishing/uploads/automatic approval/scheduling/publication/native/social/supervisor/admin workers remain off |

## Ownership and dependencies

Only native_report_authority.py, national_budget/writer.py and closely scoped acquisition/authority tests are product/test changes. No generation, pending-bills, borrowing, schema, grant, credential, dependency, workflow, repository variable or provider setting changes. The shared helper applies the same invalidation contract to national, KRA, audits and pending-bills callers. Their public persist signature is unchanged.

#802 may consume existing positive native bindings and exact committed financial lineage. It must retain financial qualification and should integrate after this query repair; no unmerged #802 implementation is included. #800 and #801 keep their assigned writer/source ownership. No sibling branch is cherry-picked. Reused issues are #831/#802/#800/#699; no distinct new issue was filed for candidate regressions fixed here.

The PR stays draft. Existing one-approval/five-required-check policy, disabled normal CI, and prior Copilot automatic/new-push/draft and Vercel Preview tracking OFF controls are preserved. Fresh repository API policy/workflow readbacks are in the evidence root; personal/Preview UI readbacks are retained in BATCH_114_RECEIPT_RELEASE, with a coordinator-only fresh-readback request in the shared831 directory. No bot review or hosted workflow is requested. Chrome was not claimed by this author.

Coordinator still needs: review the draft PR and final evidence, integrate sibling changes/rebase as required, handle normal branch-policy approvals/checks, perform a coordinated Chrome smoke, then separately authorize release/production checks. No whole original-plan acceptance issue is complete solely from this local PR.
