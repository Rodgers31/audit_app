# Batch 9 CI restoration — #587

Baseline: `672c5c011ce57dc41551f5fbc642bc4e69134c43` on
`codex/batch9-ci-restoration`. The coordinator owns approval, immutable hosted
verification, commits, PR creation and merge. This repair does not enable any
workflow or use a production connection.

## Required execution boundaries

- Both required frontend jobs provide the inert absolute API URL at job scope,
  so lint, types, tests and the build can load the actual Next configuration.
  Synthetic Supabase configuration belongs only to the build. At unit-test
  scope it initializes an asynchronous auth session under fake timers; the
  unchanged retry-budget tests demonstrated that regression before correction.
- The backend launcher schedules every existing core test file, retaining the
  existing `tests/integration` exclusion and `not slow` marker selection. Eight
  legacy ETL files run in a separate process with the real root ETL package;
  the remaining files use the real administrative ETL package. Both bind real
  backend seeding, including inherited Python children from repository-root
  working directories. The generated child startup module anchors real package
  specs with a lazy import finder; actual initializers execute after fixtures
  choose their own configuration. Missing declared package files refuse startup
  instead of falling back to the root stub. The repository root is not added to
  `PYTHONPATH`.
- Collection receipts bind scheduled and collected files, unique test node IDs,
  real package paths and the generator. Empty, missing, inconsistent or duplicate
  receipts cannot certify the gate. Ambient `PYTEST_ADDOPTS` is refused and
  configuration `addopts` is explicitly overridden, so execution cannot be
  replaced by collection or an undisclosed selector.
- Both backend cohort coverage databases must exist and measure files. They
  are combined before XML, HTML and terminal reporting; reporting errors remain
  failures. Coverage retains the original backend source scope. The extracted
  recovery definitions now compile with their actual existing source filenames,
  with a negative control for historical synthetic filenames.
- The Chromium launcher compares the original configuration's actual collected
  cases with six disjoint fixture inventories. No test body or existing skip is
  changed. Every child must emit a fresh report with the same case identities;
  missing results, contradictory accounting, unexpected failures and flaky
  outcomes fail the complete gate. Reports from previous invocations are removed
  before each child starts.

| Chromium cohort | Cases | API / Next ports | Fixture |
| --- | ---: | --- | --- |
| Public | 269 | 8141 / 3141 | Existing synthetic public API |
| Users | 4 | 8151 / 3151 | Actual users router and owned PostgreSQL audit data |
| Operations | 6 | 8152 / 3152 | Actual operations router fixture |
| Overview and audit | 5 | 8153 / 3153 | Actual audit API fixture |
| ETL UI | 28 | 8162 / 3162 | Existing frozen UI contract fixture |
| Coordinator | 11 | 8163 / 3163 | Actual router, PostgreSQL and native worker |
| **Complete original Chromium selection** | **323** | | |

Publication acceptance remains a separate existing job; its cases are not added
to the 323-case original-browser count. Each cohort builds and serves real Next
production output with its own inert loopback configuration. The ETL UI fixture
has no `/fixture/health` route and its admin health route requires auth, so
readiness uses its existing public `/fixture/requests` endpoint.

The browser launcher owns a unique UUID-named, labeled PostgreSQL container on
verified-free loopback port 55494, pinned to the existing Linux amd64 image
digest. Explicit `BATCH9_CI_BROWSER=true` plus port `55494` is the only accepted
override. Existing standalone fixture defaults 55471 and 55483 remain intact.
Readiness checks the final TCP server, avoiding the image's temporary Unix
initialization server. Cleanup verifies exact name and ownership, including a
partially created container when Docker startup fails. It never removes a
foreign-owned container.

## Evidence and current gate status

Raw output, executable adversarial probes and source manifests are retained in
the coordinator's `BATCH_9_SESSIONS/CI_RESTORATION` evidence directory. Original
hosted run `37978064797` remains a historical failed attempt.

- Fresh owned CPython 3.13.9 runtime; installed requirements-dev pins and fresh
  engine-strict frontend installation on Node 22.19.0. Hosted jobs use CPython
  3.12 and require their own fresh immutable execution.
- `workflow-controls-final-lazy.log`: **51 unittest controls pass**,
  including actual Next configuration loads, real conflicting ETL/seeding
  execution, inherited child packages, coverage aggregation, selectors and the
  existing CI/manual contract checks.
- `frontend-jest-corrected.log`: **147 suites, 2077 passed, one existing skip**.
  Lint, `npx tsc --noEmit` and production build pass. Failed intermediate auth
  configuration and descriptor typing attempts are retained separately.
- `adversarial-review/REPORT.md`: independent executable verification; all
  13 permanent browser controls pass, 70 hostile browser inputs are refused,
  and backend receipt, coverage, import and selector failure controls refuse
  success. The same lifecycle control reproduced stale-report acceptance
  against preserved pre-fix source before passing on repaired source.
- `adversarial-review-final/REPORT.md`: independent final review of the lazy
  bootstrap and three fixture repairs. All 25 frozen hashes matched before and
  after 27 Python probes, five county-helper probes and nine actual accessible
  DOM tests. Child configuration precedes real package initialization in both
  cohorts from both working directories. Missing selected initializer files
  abort before the child body; actual initializer exceptions fail at ordinary
  import, with no fallback. This supersedes the earlier eager-bootstrap
  failure-boundary description.
- `frozen-source-manifest.json`: preserves the earlier 18-path freeze;
  `final-source-manifest.json` records the later launcher and three authorized
  fixture corrections and separately records the coordinator-owned #591 packet.
  These local
  receipts refer to the baseline HEAD and a working-tree source manifest,
  rather than claiming that an uncommitted local tree is an immutable commit.
- `browser-complete-frozen.log`: **all 323 identities executed, 312 passed,
  11 existing skips**, all six cohorts successful and owned database removed.
  The ambiguous county selector failed the first complete run and passed this
  unchanged-source run; its demonstrated intermittency still justified repair.
- `backend-complete-frozen.log` / `backend-frozen/summary.json`: **FAILED**,
  administrative cohort 12534 passed / 1309 skipped / four failed; legacy 275
  passed / 41 skipped. Actual combined XML, HTML and terminal reporting all
  succeeded, at 75% backend coverage. Its 13847 + 316 collected cases are broader
  than earlier scoped selections; do not add overlapping scoped counts.
- `fixture-repairs-lazy-bootstrap-scoped.log`: **72 actual cases pass** with
  inherited lazy package selection, including the repaired fixtures, persisted
  SQLite workflow, recovery provenance and the final 13 financial review controls.
- `descendant-lazy-configuration-red.log` and
  `descendant-lazy-configuration-green.log`: the actual child late-configuration
  regression fails with eager initializers and passes with lazy anchoring; all
  ten launcher controls pass.
- `fixture-negative-mutation-red-green.log`: the actual duplicate-router control
  fails under a deduplicated OpenAPI inventory, and the actual blocking-handler
  control fails if its blocked-provider accounting is removed. Both pass under
  the repaired fixtures. The coordinator independently ran all 14 monitoring
  cases on existing FastAPI 0.129.2, verifying genuine older flat-route support.
  `COORDINATOR_OLDER_FASTAPI_REPLAY.md` identifies that receipt as a manual
  transcription of actual session 98215, exit zero.
- `backend-complete-final.log` / `backend-final/summary.json` and
  `backend-final-readback.json`: **PASSED**, administrative cohort 12541 passed /
  1309 skipped; legacy 275 passed / 41 skipped; **12816 passed, 1350 skipped,
  zero failed**, across 14166 collected cases. All scheduled files remain:
  470 administrative files (466 contain cases; four existing support helpers
  define none) and eight legacy files. Both real ETL/seeding identities validate.
  Both coverage databases measure files, and combined XML, HTML and terminal
  reporting succeed at **75%**. Output is archived in `backend-final/coverage`;
  normalized independent readback is retained separately. This full run includes
  the three fixture repairs and precedes the later coordinator schema extension.
- `browser-complete-final.log` / `browser-final-readback.json`: **PASSED**, all
  **323 original identities**, **312 passed / 11 existing skips**, zero unexpected
  failures or flaky results, all six cohort exit codes zero. Archived reports
  are in `browser-final`. The exact owned container is absent and loopback port
  55494 is free. This includes the accessible county selector correction and
  precedes the later coordinator schema extension.
- `final-static-checks.json` and `final-frontend-checks.json`: critical Python
  lint, diff checks, final frontend lint with zero warnings and TypeScript checks
  pass. Complete-run readbacks confirm all 22 author paths and three coordinator
  packet paths matched the pre-run manifest. The following fixture-only revision
  is frozen separately in `coordinator-schema-source-manifest.json`.
- `workflow-controls-final-schema.log`: **55 controls pass**, including four
  added migration selection/refusal controls. Their original fixture execution
  is red in `coordinator-schema-regression-red.log`; repaired execution is green
  in `coordinator-schema-regression-green.log`. These isolated actual-module
  controls certify exact inventory and refusal before database access; actual
  PostgreSQL preparation, shared reservation and coordinator cases are separate
  execution proofs.
- `coordinator-schema-minimum-green.log` and its readback: the same four exact
  migration controls pass on existing CPython **3.12.15**, FastAPI 0.143.0 and
  SQLAlchemy **2.0.23**, using the minimum runtime without changing it.
- `coordinator-main-final/receipt.json`: **PASSED**, actual main-model e554-only
  PostgreSQL preparation succeeds twice, shared schema remains absent, and all
  **11 exact coordinator browser cases pass**, with zero skips, unexpected or
  flaky outcomes. All 23 author hashes are unchanged and the owned database is
  removed. This is the scoped replay after the migration-aware fixture change.
- The coordinator's `COORDINATOR_CANDIDATE_ACCEPTANCE/receipt.json`: **PASSED**,
  actual held #584 candidate plus the final native schema guard prepares e572,
  a real shared reservation succeeds and is rolled back, and all **11 coordinator
  browser cases pass**, with zero skips, unexpected or flaky outcomes. Exact
  source hashes are unchanged and the owned container is removed. These scoped
  replays overlap the original 323 cases; do not add them to the complete count.

Earlier complete execution exposed fixture defects, now explicitly repaired
within #587 after coordinator source review and GitHub mechanism dedup:

- `test_admin_users_review.py` slow-provider detail test checks that a thread
  started after a fixed 10 ms sleep; one concurrent local execution failed that
  timing assertion. The repaired test uses started/release events and proves an
  unrelated health request completes while the actual provider remains blocked.
  A real event-loop-blocking handler is a permanent negative control.
- Three `test_social_monitoring_startup.py` actual-startup cases traverse
  `main.app.routes` directly. The installed FastAPI 0.143.0 uses lazy included
  routers: the coordinator's isolated diagnosis found zero direct social routes
  while OpenAPI still exposes the expected 35 and actual response/privacy checks
  pass. Public route-context traversal with older flat-route compatibility
  preserves the exact 35 unique registrations and privacy checks. A duplicated
  actual social router must fail; OpenAPI deduplication cannot hide it.
- `e2e/api-failures.spec.ts` county probe uses a shared placeholder that resolves
  to two inputs in `utils/countyResponse.ts`. The helper now selects the exact
  accessible `Search County` searchbox, preserving all original case identities.

No affected case was excluded or quarantined. A further introduced launcher
defect eagerly initialized child seeding/database before the persistent browser
fixture selected SQLite; the frozen run caught its connection attempt to inert
localhost 5432. Lazy package specs correct that startup order, with actual
late-config and persisted-fixture controls. The first complete backend run
after the #591 packet is explicitly superseded:
review fixes changed the launcher during that run, and its aggregate correctly
refused the mixed generator receipt. Intermediate PostgreSQL and ETL-readiness
setup failures also remain historical evidence.

The coordinator then reproduced a distinct combined-candidate fixture gap on
the actual held #584 tree: e554 dispatch schema exists, e572 shared schema is
absent and an actual shared reservation is refused. The prior complete main
runs cannot certify that newer schema. The authorized fixture-only extension
now requires the exact e572 migration when actual model metadata declares
`seeding_domain_claims`, validates every required file before database writes,
and applies the actual e554 then e572 additive modules. Model absence preserves
main's e554-only setup. No shared-schema `Base.create_all`, generic head migration
or fallback substitutes for the real migration. The coordinator retains the
original reproduction in `COORDINATOR_CANDIDATE_PROBE/receipt.json`. The later
actual main and combined preparation/browser receipts above verify both fixture
branches. Their local working trees are explicitly distinct from a fresh
immutable hosted candidate.

## Review and continuation

Independent Standards review found partial-start cleanup, now fixed and covered
by executable ownership controls. Independent Spec review found descendant ETL
ownership, now fixed with actual red/green controls for both cohorts from both
working directories. Independent adversarial review found stale-report,
accounting, receipt-schema and hidden-selector false successes; all reproduced
failures have permanent controls and passing re-verification.
Final independent Standards, Spec and adversarial reviews of the lazy bootstrap
and three fixture repairs are clear. Standards and Spec separately reviewed the
later coordinator schema extension; both are clear and Spec independently
replayed its four controls.

The coordinator separately owns #591's substantive financial source-context
review; this change does not approve or refresh those pins. Its detector and
product source modules remain unchanged. Preserve that ownership when staging.

Before a code merge, review the final complete local results, resolve genuine
remaining baseline defects through their issues, commit the reviewed repairs,
integrate them into the held #584 candidate, and dispatch a new authorized full
hosted attempt against its immutable SHA. Preserve all earlier failed attempts.
Production rollout and operator reconciliation remain separate coordinator gates.
Handoff-only status changes are recorded separately from tested code in
`post-verification-source-manifest.json` and `final-delivery-source-manifest.json`.
Preserve the earlier complete-run and coordinator schema manifests rather than
rebinding historical evidence to the latest working tree. The coordinator now
has exclusive ownership of this checkout and the released test resources; the
author has not staged, committed, pushed or changed workflow state.

Lessons for future batches: derive readiness from actual fixture endpoints,
inventory case identities before partitioning, exercise real inherited package
imports, keep build-only auth configuration out of unit tests, and prove fresh
execution rather than trusting an exit code or an existing receipt.

## Reopened hosted infrastructure gate — #598

The author resumed exclusive ownership at `f63db60d10a3704c311c5f31a870b8cf9dcf165b`
for the approved registry transport repair. Hosted combined run `37989790306`
at `1ccc71a56ce7e84a0bfc15a3a406d5f022dba298` failed on unauthenticated Docker
Hub pulls in backend service setup and original browser fixture setup. The
earlier complete local main, combined coordinator and generator receipts above
precede this transport edit. Preserve their actual source bindings; none certify
the newly edited generator or repair's fresh hosted delivery.

The ordinary fixture retains its exact `67f41722…` index and both architecture
children, now referenced explicitly through the official DOI ECR repository.
The seven-job CI/manual contracts use approved pinned DOI PostgreSQL 17 and Redis
7 services. Optional service preparation accepts only the exact approved PG17
reference, validates its cached native image, preserves an identical local
`postgres:17` alias, refuses an existing mismatch and verifies a newly created
alias's ID. The actual shared local alias was not written during verification;
the fresh hosted runner must exercise alias creation to retain all role/RLS cases.

`REGISTRY_TRANSPORT_598` retains the pre-edit manifest, red controls, executable
registry proof with 34 captured byte-identical response files, six actual
amd64/arm64 Docker pull/readiness/cleanup receipts, and scoped source-bound checks.
Final current workflow controls pass **71**. Relevant minimum controls pass **42**
(25 image, five configuration, 12 manual), overlapping the current selection.
The broader minimum launcher attempt's five missing-coverage setup failures are
retained, not labelled green. Actual backup/restore/acquisition and role/RLS
suites pass **92 without skips on each runtime**. The failed first Docker
receipt generator is preserved separately from its corrected second generator.

Independent review exposed inherited malformed `RepoDigests` acceptance and
unstructured malformed-architecture refusal. Both preparation-validator repairs
have actual red/green controls; valid canonical image metadata aliases remain
supported. Preserve the first review manifest/diff and use the distinct second
freeze for final review. The transport replay accounted for all **323 browser
cases: 312 passed and 11 existing skips**, six zero-exit cohorts, with owned
database cleanup. Browser generator and fixture hashes stayed unchanged while
helper/control repairs were made; this is not a whole-tree frozen execution.

See `docs/operations/owned-postgres-test-images.md` for the exact approved index
and architecture manifest identities, receipt limitations and source chronology.
The inactive Docker deployment workflow's remaining Docker Hub test services
are a deployment-preflight gate under #545/#598. Production images, product
models/migrations, Supabase's pin and the coordinator's three #591 packet paths
are outside this repair. The coordinator still owns immutable integration,
fresh full hosted verification, any workflow enablement, commit and merge.
