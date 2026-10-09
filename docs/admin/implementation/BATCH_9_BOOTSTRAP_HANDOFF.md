# Review correction handoff — 2026-10-09

Current local acceptance, all seven inline classifications, both body-only
findings, caller-owned transaction bounds and fresh default-fixture execution
are recorded in [PR590_REVIEW_ACCEPTANCE.md](batch9-bootstrap-evidence/PR590_REVIEW_ACCEPTANCE.md).
Actual main `b0ec603ccbf29d5ae7f6540faa3d484964334fb1` has been merged into the
review candidate without source conflicts. The historical author handoff below
remains preserved; its draft/dependency state, source hash, `not_run` metadata
and default skipping behavior have been superseded by the dated review report.
Final published head, GitHub replies and hosted/merge acceptance belong to the
coordinator.

---

# Batch 9 — bootstrap budget ownership (#582)

Author delivery for coordinator acceptance. **Dependent draft: target
`codex/batch8-native-exclusion`, pinned #584 head
`9e97ca3f1ca43f103a8655447a86d889456a218a`.** Do not merge or retarget until
the coordinator accepts #584. #582 and #545 remain open.

## Identity and ownership

- Managed worktree: `/Users/roger/.codex/worktrees/1183/audit_app`; initial
  status was clean/detached at verified main
  `672c5c011ce57dc41551f5fbc642bc4e69134c43`.
- Branch: `codex/batch9-bootstrap-ownership`. Both remote pinned refs matched
  before branching and immediately before publication preparation.
- Exact implementation/evidence commit:
  `57fdad4e2a8bc43a7ebc250823491191fd0d3719`.
- The delivery head is the documentation-only commit containing this handoff.
  Obtain its exact identity with `git log -1 --format=%H --
  docs/admin/implementation/BATCH_9_BOOTSTRAP_HANDOFF.md`; the attached draft
  PR and final author report also name the full delivery SHA. This separates
  the tested implementation identity from the final handoff commit without
  inventing a self-referential commit hash inside its own contents.
- Final product SHA256 (`backend/bootstrap.py`):
  `4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`.
  The shared seam is unchanged, SHA256
  `a62033df887862e34bca064a3ddd2aace56730a4f573aced8e07ceb3b8a257a6`.

Changed-file ownership is limited to `backend/bootstrap.py`, uniquely named
`backend/tests/test_batch9_bootstrap_ownership.py`,
`backend/tests/test_batch9_bootstrap_sessions.py`,
`backend/tests/batch9_bootstrap_fixture/sitecustomize.py`, this handoff and
`docs/admin/implementation/batch9-bootstrap-evidence/`. No change to main.py,
shared claims/models/migrations, ETL, workflow, frontend, dependencies, common
contracts/roadmap or sibling handoffs. The primary checkout was not edited,
switched, reset or used for installs; its Python was executed read-only.

## Resulting behavior and call inventory

Bootstrap calls the reviewed `enter_domain` seam for national_budget before
reference mutation. Its nonwaiting refusal creates a visible FAILED
`ownership_refused` / `source_mode=not_run` observation while reference work
can proceed. `force=True` bypasses only the old scheduling courtesy, never
shared ownership. National_budget is excluded from that coarse recent-RUNNING
probe so native-first empty startup still initializes the reference counties.
The unchanged courtesy for other domains has a separate issue below.

The registered budget handler runs with live PDF fetching disabled and its
actual job ID, inside a savepoint in the supplied bootstrap session. Coherent
results receive a budget terminal observation plus the reference provenance's
budget status/job correlation. Budget error or malformed result rolls that
savepoint back, persists FAILED with ownership_retained, and preserves reference
initialization. It deliberately retains the claim, even for a synchronous
budget failure, as required by this lane's uncertainty policy.

The caller commits its budget/reference transaction before acknowledgement.
Only successful persisted completion is acknowledged. The unchanged shared
seam proves continuity and mutates release on its lock-holding backend.
Connection death, lost continuity, interruption, missing receipt, failed or
ambiguous commit retain authority. There is no timeout/age reclaim or unlock
fallback. Existing early country and fiscal-period helper commits remain
unchanged; county/budget writes retain their final outer-commit semantics.

Real caller inventory (searched backend, .github and scripts):

| Entry path | Coverage |
| --- | --- |
| `main.py:117,1704`, `_startup_sequence` → `asyncio.to_thread(initialize_reference_data)` | Actual startup process, both ownership orders, empty/current/superseded data, absent/different JWT ambient values |
| `seed.yml:461-462`, `from bootstrap import initialize_reference_data; initialize_reference_data()` | Exact weekly import/call in separately launched processes; no hosted dispatch |
| Manual `initialize_reference_data()` / `force=True` | Same guarded choke point; separately launched force path proved refusal |
| `_seed_national_budget` | One production caller in initialize; now requires its verified shared execution object |
| Native `seeding.cli seed --domain national_budget` / `--all` | Actual CLI in both acquisition orders, allowed next run, dry-run rollback; no CLI changes |

No production direct caller of the private helper was found outside initialize.
Other seeding domains and dedicated dispatch still use #584's seam unchanged;
dispatch defaults, source mappings, CLI arguments, publication and source scope
were not changed.

## Verification actually executed

All final results are **combined-candidate local verification** including held
#584. PostgreSQL was owned `postgres:16-alpine`,
`batch9-bootstrap-1183-db`, database `batch9-bootstrap-1183`,
`127.0.0.1:55492`. Each author case used a unique schema; independent reviewer
and migration controls used separate `batch9-bootstrap-*` databases because
advisory keys are database-wide. Only inert registry writers ran, with sockets
outside the owned loopback refused.

| Evidence | Pass / fail / skips |
| --- | --- |
| `ownership-current-final` | 20 / 0 / 0, no xfails; Python 3.13.9 / SQLAlchemy 2.0.46 |
| `ownership-min-final` | Same 20 / 0 / 0; Python 3.12.15 / actual SQLAlchemy 2.0.23 |
| `regressions-green-final`, `regressions-min-final` | Same 143 / 0 / 0 on each runtime |
| `additional-scoped` | 45 / 0 / 0 on current runtime |
| `adversarial/current-1`, `adversarial/minimum-1` | Same 22 / 0 / 0 independent controls on each runtime |
| Independent Spec | Exact readiness red, then green on current and minimum runtimes |
| Independent Standards | 8 / 0 / 0 session controls per runtime, plus ORM mode controls |
| `migration-current`, `migration-min` | Actual empty upgrade chain to `e572b8c9a001`, RLS true, zero claim rows |
| `lint-import`, `compile-import` | Critical CI flake8 selection and actual imports pass; four sources parse |
| Receipt readback | 31 JSON receipts plus three independent Spec raw headers validated |

Selections and runtime replays overlap; do not add their counts. Expected
deprecation warnings are retained in raw output. The PostgreSQL process gate
skips by default without its explicit owned URL; all acceptance runs supplied
it and executed with **zero skips/xfails**. No frontend build was needed for a
backend-only change. Raw output whitespace is preserved unchanged; code,
Markdown and JSON pass `git diff --check` with raw `.txt` receipts excluded.

The 20-process matrix proves real acquisition orders for manual, weekly and
web startup against native --domain/--all; a preexisting budget sentinel is
preserved by refused bootstrap; reference counties initialize during refusal;
normal completion allows the next writer; handler exception/returned errors
retain authority; SIGKILL before writes, after uncommitted writes, and after
outer commit retain claims across restart; actual lock-backend death permits
the already running writer's honest commit but blocks every next owner;
native dry-run excludes bootstrap, rolls back its effect and allows the next
bootstrap. Bootstrap itself remains non-dry-run, matching the weekly invocation.

Independent controls additionally attack None/dict/truthy-failure results,
bool/negative/overflow/NaN/infinite counters, mismatched domain/dry_run/errors,
outer reference rollback, a 365-day untagged RUNNING observation, supplied
Engine/Connection factories, invalid receipt followed by valid receipt, and
actual backend death after proof and after release UPDATE before commit.

SQLite verifies supplied-session/savepoint behavior only. It does not provide
the PostgreSQL continuity or independent durable-persistence proof. For a
supplied external SQLite Connection, child claim sessions preserve that bind
and use create_savepoint; a refused claim cannot roll back caller reference
rows. Both supported ORM versions executed this behavior.

Exact commands, environments, commit/source/generator/output hashes and raw
results are in [`batch9-bootstrap-evidence/README.md`](batch9-bootstrap-evidence/README.md)
and its receipt files. The minimum runtime install is owned and retained at
`.local-dev/batch9-bootstrap-min/venv`; no shared runtime was installed into.

## Red evidence and independent findings

- Pre-edit baseline: 30 existing controls passed; six separately launched
  ownership-order regressions failed on pinned bootstrap (`ownership-red`).
- Spec P1, valid: coarse budget deferral falsely marked empty startup ready.
  Four author red cases and the independent SQL census reproduced it; excluding
  budget from the courtesy produces 47 counties with only the native handler
  entered. Green on current/minimum ORM.
- Standards P2, valid: factory conversion to Engine reused SQLite's DBAPI
  connection and refused acquisition rolled the caller's transaction back.
  Existing population fixture and unique session fixture were seen red.
  Preserving the supplied Connection **alone** was insufficient: independently
  measured conditional_savepoint lost caller_effects and ended its transaction;
  create_savepoint preserved both. Regressions now pass on both runtimes.
- Spec fixture-isolation finding, valid: backend-termination control originally
  scanned cluster-wide advisory PIDs. It now filters to the owned database.
- Final adversarial review: no actionable defect among 22 executed controls
  on each ORM runtime. Spec and Standards re-review: no unresolved scoped
  findings. Reports and detailed limitations are retained independently.

Unsuccessful intermediate runs are preserved and explicitly classified in the
evidence README: the first candidate's supplied-session regression, a test-only
fixture_superseded expectation error (19 pass / 1 fail), and isolated GH auth
configuration failure. None is counted as acceptance. No billable Copilot or
CodeRabbit round or review/merge policy change was requested.

## Issues, remaining gates and resume

- #582: this delivery; kept open for coordinator acceptance.
- #584 / #583: unchanged dependency and operational migration, production
  RUNNING census, pooler cutoff and reconciliation gates. Authors performed no
  production inspection, activation or Actions settings changes.
- #589: separately deduplicated non-budget false readiness. All 288 open and
  closed issues were fetched before creation; configured replay has 289 including
  #589. Actual startup against an empty owned DB with a recent audits RUNNING
  row exits 0 and reports ready while SQL shows zero counties/bootstrap jobs
  (`other-domain-readiness`). It remains outside this scoped budget fix.
- #545: parent roadmap, unchanged and open. Sibling lanes were not bundled.

Local #582 acceptance is met by the executed process and independent controls;
overall acceptance/merge/production verification belongs to the coordinator.
The actual workflow listing showed delivery workflows disabled_manually; no
hosted execution is claimed from TESTING_GATES.md. The draft stays draft and
targets the dependency branch until coordinator retargeting.

Cleanup receipt `cleanup.json/.txt` proves no remaining author fixture schemas,
no other sessions on the owned databases, only the owned main fixture database
remaining before removal, then removal of the named container/anonymous volume
and port 55492 free. Reviewers removed their own processes and databases.
The managed worktree, owned minimum runtime, install log, original dedup
snapshot, tests and all raw evidence remain available. Do not archive this
worktree while review is pending.

To resume, verify the PR head and frozen source hashes; read final reviews and
the evidence README; recreate only the owned fixture if another targeted
receipt is necessary. Keep #584's exact pinned dependency rather than consuming
new sibling changes. Check all PR threads **and** review bodies with pagination;
push any finished repairs before in-thread replies, resolve handled items only,
then re-fetch. Do not request additional paid reviews or merge the delivery.

## Reusable lessons with receipts

1. A scheduling courtesy can safely avoid one writer yet still falsely certify
   readiness. Measure actual readiness plus independently queried reference
   rows; the Spec red/green controls prove the distinction.
2. A supplied SQLite Connection represents caller authority. A factory bound
   to its Engine can roll that authority back on refusal; the Standards ORM
   control proves explicit savepoints preserve it on both ORM versions.
3. Verify destructive rollback against preexisting rows, not only zero new
   effects. Independent malformed-result controls preserved a real budget
   sentinel while retaining ownership.
4. Database-wide advisory locks require separate owned databases for parallel
   reviewers; schemas alone do not isolate same-domain process controls.
5. After writer commit, release uncertainty must assert retained authority and
   the committed effect separately. Backend-death controls prove why a later
   failure cannot truthfully be reported as undoing the earlier commit.

These are handed to the coordinator for consolidation; globally installed
skills were not edited.
