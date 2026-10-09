# Batch 7 ETL worker handoff — #554 / #545

Author checkout: `/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app`.
Branch `codex/batch7-etl-worker`, pinned base
`f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d` / tree
`712b43650b1203ffd84583b67d07d30775669b1e`.
Final tested implementation source: `c8cfc5931f22a4cc121005e3f5285845a9480336`;
subsequent delivery commits contain handoff/review/resource receipts only.
Frozen v1 contract and examples were read from the shared Batch 7 directory.
The dirty primary checkout remained read-only. No AGENTS.md/CLAUDE.md was found
in this checkout or its applicable ancestors. Current #554/#545 bodies and the
committed Operations/Batch 6 handoffs supplied the accepted compatibility scope.

## Result and boundaries

The API provides private, administrator-only dispatch capability, durable 202
acceptance, deterministic bounded history and identity-matched command detail.
Default `ADMIN_ETL_DISPATCH_ENABLED` is absent/disabled; legacy triggers continue
to return `503/manual_dispatch_unavailable` without commands, observations or
success audits. Calendar/health remain calendar/unverified evidence.

Commands and actor acceptance audits commit atomically. Full actor/key identity
is unique; same-intent replay recovers the original receipt after generation
expiry and never dispatches again. Changed source/dry-run conflicts. Private
validation/storage failures do not echo inputs or internal diagnostics.

Dedicated entry point: `python -m admin_etl_dispatch_worker` from the owned
backend with an explicitly enabled flag, direct PostgreSQL configuration and
owned seeding settings. No API/main lifespan/background consumer was added.
It runs a real DB-clock heartbeat, serializes claims and holds a durable domain
block. A child invokes the unchanged `run_seed_command` with static arguments.
Actual CLI session inserts carry internal command/claim correlation metadata.
Exit zero alone, an empty registry, missing/malformed matching observation or
lost fence cannot become completed. A once-only execution marker is persisted
before invocation, so duplicate adapter processes cannot rerun a claim.
Completed observations must also have coherent timestamps relative to the
DB-clock claim (five-second maximum host clock skew), nonnegative integer counts
and an empty diagnostic list. Unknown evidence interrupts and keeps the block.

Supported mapping: **OAG → `audits`**, grounded in
`seeding/domains/audits/__init__.py` registration and OAG registry behavior,
demonstrated with an inert registered domain in the actual CLI. The source
registry, domain writers/parsers, publication gates and native runner were not
changed. Treasury, CoB, KNBS, OpenData and CRA remain unavailable: each needs a
separately grounded one-domain mapping and demonstrable receipts. This mapping
does not assert financial freshness or deployed readiness.

## Lease loss and quiescence

Stale generation tokens cannot update receipts. API polling can durably mark an
expired running receipt interrupted; dedicated restart does the same. Neither
path clears the domain block. Interrupted work is never automatically replayed,
even if its native observation later finishes or an advisory connection closes.

No unblock endpoint, cleanup/backfill or automatic reconciliation is shipped.
Before further conflicting work, a separately reviewed operational procedure
must disable acceptance, stop all supervisor process groups/orphan children
and any independent scheduler/native CLI, verify owned processes and database
sessions have stopped, reconcile the exact command's possible effects and
observations, and approve any explicit domain-block release. Lease expiry,
process PID disappearance alone, and absence of a DB advisory lock are not
proof that financial effects stopped. No such operational release was run.

The durable block serializes this dedicated dispatch lane. The unmodified
independent native CLI does not participate in its domain lock. A RUNNING native
observation conservatively prevents claiming, but this cannot close the race
where an independently launched CLI starts later. Activation therefore requires
exclusive native-runner ownership/quiescence or a reviewed shared runner seam;
this PR remains default-off and does not launch a production service. This is a
material integration/activation limitation, not a local concurrency certification
for every external financial process.

The executed race is tracked in [#572](https://github.com/Rodgers31/audit_app/issues/572),
after all-state native-CLI/domain-exclusion/quiescence searches. The precise
shared-seam request is `CONTRACT_CHANGE_REQUEST_BATCH7_ETL_WORKER.md` alongside
the frozen spec. Its strict xfail is visible in the default lane suite; actual
`--runxfail` output retains the two conflicting inert effects (`2 != 1`) in
`native-exclusion-gap-red.txt`. Core runner semantics were not edited.

## Migration and executed evidence

Actual prior Alembic head (ScriptDirectory, no live settings import):
`d8f4a619b203`. Additive head `e554d7c9a001` creates command/lease/domain tables
with constraints, indexes, RLS and revoked public/client grants. No old PENDING
observation is converted or cleaned up. Downgrade refuses accepted history or a
fresh ready worker. PostgreSQL upgrade/downgrade/re-upgrade preserved a legacy
PENDING observation and the exact existing ingestion column/type list.

Read [baseline and red/green receipts](../../../batch7-etl-worker-evidence/baseline-red-green.md)
and [author final output](../../../batch7-etl-worker-evidence/final-author.txt).
Final combined replay: **281 passed, 1 strict xfailed (#572), 3 warnings in
25.39s**, retained in [final-combined.txt](../../../batch7-etl-worker-evidence/final-combined.txt).
This includes the 70 independent adverse cases with strengthened assertions.
[Exact commands and cleanup receipts](../../../batch7-etl-worker-evidence/commands.md)
provide the complete reproducible clean environment.
The new PostgreSQL tests force duplicate accepts, two consumers, actor isolation,
lost acknowledgment, audit rollback, stale generation, lease expiry and restart.
The process tests launch the real worker and adapter; only the registered domain
handler and auth transports are inert. Real mode commits one isolated effect,
dry-run rolls it back while preserving its actual observation, failure produces
a failed receipt, and death before/after an explicit inert commit retains the
block. SIGSTOP pauses only a supervisor while its child survives expiry.

Canonical author command uses the exact clean environment below and
`-m pytest backend/tests/test_batch7_etl_postgres.py backend/tests/test_batch7_etl_process.py
backend/tests/test_batch7_etl_migration.py backend/tests/test_batch7_etl_contract.py
backend/tests/test_batch7_etl_adversarial.py
backend/tests/test_admin_operations_lane.py backend/tests/test_admin_operations_adversarial.py
backend/tests/test_etl_admin_endpoints.py backend/tests/test_web_ingestion_ownership.py
backend/tests/test_ingestion_query_transfer.py backend/tests/test_seeding_cli_budget.py
backend/tests/test_seeding_utils.py -q`.

```
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1
PYTHONPATH=/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app/backend
DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker
BATCH7_ETL_TEST_DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker
BATCH7_ETL_ADVERSARIAL_DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker
/Users/roger/Documents/projects/audit_app/venv/bin/python
```

Runtime/resource ownership: read-only Python 3.13.9; Docker `postgres:16-alpine`
container `audit-batch7-etl-worker-db`, loopback **55481**, database/user
`batch7_etl_worker`/`batch7_worker`. No product API port/server was needed (mounted
TestClient has no main lifespan). Inert child PYTHONPATH adds only the owned
`backend/tests/batch7_etl_worker_fixture`; it blocks external sockets and aborts
startup if registry setup fails. Native child logs are discarded, optional
native file logging is disabled in the adapter. Test subprocess groups are
stopped in fixture finalizers. Frontend 3162/8162/55482 were not used.

The runtime lacked flake8; installed repository-pinned `flake8==6.1.0` only in
owned external `etl-worker/tools` venv. Critical CI lint (`E9,F63,F7,F82`) was
executed on every changed Python file, including migration and fixture. No
manifests/runtime dependencies were mutated.

## Review and remaining acceptance

Independent [Standards](../../../batch7-etl-worker-evidence/standards-review.md),
[Spec](../../../batch7-etl-worker-evidence/spec-review.md) and
[adversarial](../../../batch7-etl-worker-evidence/adversarial-review.md) review
ran against `e98a4be3998f7da4e2326a068802a879e393fb97` versus the pinned base,
then rechecked the exact final source blobs committed at `c8cfc59`.
Standards: readiness-after-failed-commit defect fixed, optional duplicate child
cleanup factored; zero remaining findings. Spec: UTC, readiness, direct intent
and observation-coherence findings fixed; #572 remains the sole material shared
exclusion requirement. Adversarial: original **8 red / 56 green**, author replay
**8 red then 8 green**, final independent **70 passed in 1.94s** plus **10**
direct-route shape/default-off controls. Reviewers completed without interruption.
Final combined verification caught and repaired two valid legacy direct-dict
compatibility cases (retained red and four-case green); all final controls pass.

Each boundary's guard covers all entry paths: API acceptance and actor/key replay
share strict intent checks; capability/accept/claim/finish serialize against the
worker row; polling and restart fence stale receipts while leaving exclusion;
native adapter and duplicate launches share once-only execution; finish alone
authorizes release from matching coherent observation evidence. No historical
PENDING row or external runner path is silently redirected through these guards.

Owned test process groups were stopped by finalizers. Before database cleanup,
SQL observed **0 other database connections** and **0 reviewer schemas**.
`docker stop audit-batch7-etl-worker-db` removed the owned `--rm` container;
55481 has no listener and no owned worker/adapter process remains. No API server
or other lane resources were used/stopped. Worktree remains attached for review.
Only the repository-pinned lint-tool venv and small pinned-source evidence remain
outside Git in the owned visualization directory; hashes/ownership are recorded
in [resource-manifest.json](../../../batch7-etl-worker-evidence/resource-manifest.json).

#554 and #545 remain open. New deduplicated #572 remains open. Coordinator owns
actual UI/backend replay with #568, final review-comment handling, mapping/shared
runner seam decisions, operational activation/migration and issue acceptance.
No production migration/worker/service, real fetch/publication, provider/user/
storage/email mutation, paid review or repository policy change was performed.

Hosted security/quality/coverage gates and the broad full-repository suite were
not executed. GitHub Actions remains disabled. Local PostgreSQL fixtures and
native CLI receipts do not certify deployed worker readiness or financial
publication/dry-run correctness of every real domain handler.
