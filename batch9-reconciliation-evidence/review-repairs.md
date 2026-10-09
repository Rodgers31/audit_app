# PR #592 coordinator review repairs

Reviewed author head `950a0d54ace562acdf1ade46d66dc7fa18d50cb5` against main
`b0ec603ccbf29d5ae7f6540faa3d484964334fb1`. The author history is retained;
main was merged without rewriting it at `93f39ded212edb9e847221cdb7def25900015159`.
The executions below retain their actual precommit target and content hashes.
They are local fixture evidence. Production acceptance for #583 remains pending.

## Complete review triage

| Review input | Classification and repair | Regression evidence |
|---|---|---|
| Inline 4235341157, `run_receipt.py` environment and output | Valid, understated across active generators. Removed embedded database credentials. An explicit untracked owned loopback URL is required; non-owned targets and conflicting connection overrides refuse before execution. Only public settings serialize; private values, connection URLs, and Unicode-escaped variants are redacted in nested JSON, Markdown and console output. | `receipt-red-behavior.log`: seven actual failures before the shared boundary repair. `escaped-secret-red.log`: one actual failure before Unicode-escaped redaction repair. Final nine publication controls pass within both 111-case selections. |
| Inline 4235341189, Spec receipt environment/output | Valid. Applied the same publication boundary to Spec, Standards and behavior generators. New output paths append review evidence; original receipts are preserved and explicitly retired for current acceptance. | Actual Spec generator: 20 controls on each supported runtime. Standards: nine controls on each. Behavior: 91 named controls on each. |
| Inline 4235341241, writer census scope | Valid. Census uses the actual tracked-file inventory, selects its declared Python/workflow/compose scope, enumerates every omitted tracked path, and sets whole-repository coverage false. Procedure requires separate review of omitted source, deployed configuration, and runtime process census. | Census regression proves scope and omissions. `writer-census-review.json`: 397 selected files, 15 mapped domains, 1,219 anchors. This is source evidence, not a production host/process fact. |
| Full review bodies and summary | All bodies read. Their concrete findings are the three items above; operational safety reminders are retained as acceptance gates. No additional concrete body-only defect was silently ignored. | Product reconciliation sources, exact claim/effect/RUNNING transactions and migration constraints replayed on both runtimes. Production/provider feasibility remains an operator gate. |

The first two baseline attempts failed in regression harness setup (missing fixture
files, then an overbroad subprocess mock). They are not behavioral red evidence.
The corrected seven-failure baseline is the actual red evidence. Original generator
bytes and all intermediate receipts remain in the external review packet.

## Additional integration repairs

The original tests assumed port 55493 and an author's private password. An actual
alternate-port run produced 82 passes, four process failures and 23 setup errors.
Fixture consumers now use the explicitly configured owned URL, a literal loopback
host, valid explicit port, and owned database name; no implicit production target,
fallback, missing-prerequisite skip or alternate fake CLI was added.

The minimum runtime then produced 108 passes and one refusal because the owned
PostgreSQL 17 fixture had autovacuum running. The product correctly refused a
background writer. The ephemeral fixture now starts with autovacuum off and proves
that setting. Production configuration and the product's writer refusal remain
unchanged. An intermediate cleanup helper missed stopped adapter descendants after
the supervisor exited; exact UID/PGID/command ownership discovery repaired it.
The four owned orphan groups were removed and the final process cohort passes.

## Final executions

| Receipt under `review/` or `behavior/` | Actual result |
|---|---|
| `publishing-final-scope-current.json` | Python 3.13.9 / SQLAlchemy 2.0.46: 111 passed, zero failed/skipped/xfailed; source unchanged. |
| `publishing-final-scope-minimum.json` | Python 3.12.15 / SQLAlchemy 2.0.23: the same 111 passed; source unchanged. |
| `behavior/review-publishing-final-current.json` | 91 controls passed; generator and product source unchanged. |
| `behavior/review-frozen-minimum.json`, `review/frozen-minimum.json` | 91 controls passed; outer wrapper exit zero, source unchanged. |
| `spec-final.json`, `spec-final-spec.md` | 20 actual selected controls passed on each runtime. |
| `standards-{current,minimum}.json` and corresponding Markdown | Nine controls passed on each runtime. |
| `ci-controls-final-{current,minimum}.json` | Eleven preparation/cleanup unittest methods passed on each runtime, including invalid ports, all 15 ambient libpq inputs, image validation and resource ownership boundaries. |
| `critical-lint-final.json` | Critical flake8 errors absent across changed Python files. Flake8 6.1.0 used the separate existing read-only CI lint runtime. |
| `final-cleanup.json`, `temporary-artifact-relocation.json` | Exact owned fixture identities removed; no owned adapter/operator processes or client sessions left. Temporary policy/IO artifacts were moved outside the checkout with byte hashes and retained privately. |

These counts overlap and must not be added as unique coverage. The first lint
attempt lacked flake8 and is retained as a setup failure. One intermediate minimum
behavior wrapper returned 90 because the Standards generator changed while it ran;
its child controls passed, but that broad wrapper is not accepted. The subsequent
frozen minimum replay above replaces it for current acceptance. No execution has
been relabeled as a later commit rerun.

The broad wrappers also hash unrelated documentation and evidence helpers. After
the 111-case, Spec and CI-control runs, the Standards generator's default output
name and census reference were updated to preserve append-only history; its final
version was then executed successfully on both runtimes. The handoff addendum was
written after all tests. These later changes are visible as content differences
against the earlier broad wrappers, not concealed as unchanged final-candidate
hashes. Reconciliation/product, receipt boundary, preparation helper and tested
fixture source bytes remain bound to the recorded successful executions. The
coordinator's independent final-candidate review and CI replay are still pending.

`publication-supersessions.json` verifies 44 historical JSON/review documents remain
byte-identical and marks their publication/source/scope claims superseded. The
current packet's custody manifest maps each copied receipt to its original path
and checksum. Generator bytes are retained at the recorded Git blobs or copied
with their exact checksum; copied artifacts are not portrayed as new executions.

## Owned CI preparation interface

```sh
python .github/scripts/prepare_reconciliation_test_fixture.py prepare \
  --state "$RUNNER_TEMP/reconciliation-fixture-state.json" --port 55496
python .github/scripts/prepare_reconciliation_test_fixture.py cleanup \
  --state "$RUNNER_TEMP/reconciliation-fixture-state.json"
```

Preparation uses `GITHUB_ENV` (or explicit `--github-env`) and exports only
`BATCH9_RECONCILIATION_DATABASE_URL`, after readiness, whole migration and exact
e583/template/claim/jobs/audit/RLS/index/autovacuum readback. Required prerequisites
are Docker, installed backend/alembic dependencies and the cached native immutable
image `public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.
Local image readback is PostgreSQL 17.11. No pull or mutable replacement is used.
Ephemeral trust authentication contains no credential in the exported URL.

The helper SHA256 is
`1f891334f3f9c1b72217a45654bb189270047cb97669bf61364e9764aa35b36a`.
Random container/network/database names have the owned prefix and nonce labels;
cleanup validates exact bound IDs, image, port and exclusive network membership.
Actual helper preparation and cleanup succeeded at verified-free port 55507
(also at 55497 earlier, before that port was released). The recorded cleaned
state binds their exact resource IDs. The coordinator will add preparation and
always-cleanup steps to both CI workflows after taking this checkout; those
workflow files were deliberately outside this repair lane.

## Remaining operator gates and uncovered-issue disposition

#583 remains open: independent production scheduler/host/operator evidence,
direct connection feasibility, complete writer/process census, fresh effects and
maintenance admission, and audited deployment/migration/activation acceptance
remain required before any production reconciliation. Local fixture evidence is
not substituted for those facts. No production database, Render, GitHub Actions
settings, provider/source operation, claim release or financial write was performed.

The owned CI fixture gap is addressed by this helper and the coordinator's workflow
wiring. The existing #583 covers the remaining operational gates; no duplicate
GitHub issue was opened from this lane. Final push, review replies/resolutions,
independent cross-review and merge remain with the coordinator.
