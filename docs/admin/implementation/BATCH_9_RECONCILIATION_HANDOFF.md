# Batch 9 — audited reconciliation handoff

## Coordinator review addendum — 2026-10-09

The author delivery below is preserved as historical context. PR #584 is now
merged into main `b0ec603ccbf29d5ae7f6540faa3d484964334fb1`. PR #592's review repairs,
complete comment triage, current scoped writer census, final frozen verification
and owned CI fixture interface are in
`batch9-reconciliation-evidence/review-repairs.md`. All original historical
receipts remain byte-identical; `publication-supersessions.json` declares their
publication/source/scope claims superseded for current acceptance. The current
local cohort passes 111 cases on each supported SQLAlchemy runtime; counts overlap
with the separate 91-control behavior reviews. Production/operator acceptance
for #583 remains pending. The original dependency/head/receipt identities below
have not been rewritten to portray a later execution.

## Delivery identity and acceptance

This is the scoped implementation/procedure delivery for [#583](https://github.com/Rodgers31/audit_app/issues/583).
It depends on [draft PR #584](https://github.com/Rodgers31/audit_app/pull/584), branch
`codex/batch8-native-exclusion`, pinned at
`9e97ca3f1ca43f103a8655447a86d889456a218a`. The dependent draft targets that branch,
not main. Verified main before checkout was `672c5c011ce57dc41551f5fbc642bc4e69134c43`.

Reviewed implementation commit: **`b7329bf1b25ef1ffdeebd42184fa77d597b373fb`**.
Branch: `codex/batch9-claim-reconciliation`.
Managed author checkout: `/Users/roger/.codex/worktrees/a46a/audit_app`.
The following documentation-only commit contains this handoff and
`batch9-reconciliation-evidence/delivery_manifest.py` and
`batch9-reconciliation-evidence/delivery-manifest.json`. Its exact delivery
SHA is published in the draft PR body, GitHub `headRefOid`, coordinator message
and final author report; a commit cannot contain its own SHA. The manifest proves
all nine final tested source files equal the implementation commit's blobs.
Original receipts honestly retain their precommit base HEAD and content hashes;
no execution has been relabeled as a postcommit rerun.

**Local implementation and procedure acceptance: PASS. Production/operator
acceptance for #583: PENDING.** Independent Spec, Standards and behavior reviews
pass with no unresolved local implementation finding. Coordinator review and
GitHub review remain separate. This packet can remove #584's missing reviewed
reconciliation tooling/procedure code gate after coordinator acceptance; it does
not complete #583 or authorize migration, activation, outage or release.

## Owned changes

| Files | Change |
|---|---|
| `backend/seeding/reconciliation.py` | Separate PostgreSQL maintenance inspect/plan/apply API; separately trusted signed host/scheduler/operator evidence; exact census and public-table effect hashes; committing admission/domain/table/row locks; atomic audit, claim, dispatch and correlated RUNNING dispositions. |
| `backend/seeding/reconcile_operator.py` | Retained direct connection and explicit newline JSON inspect, plan and apply requests. Deployment-provisioned policy path/hash; uncertain outcome on database/commit failure; no automatic reconnect or retry. |
| `backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py` | One additive migration after `e572b8c9a001` validates meaningful Unicode-whitespace-aware reconciliation fields. Existing invalid releases fail upgrade; history/RLS/grants/index remain preserved. Weakening downgrade refuses. |
| `backend/models.py` | Only the corresponding reconciliation CHECK expression changes. |
| Four `backend/tests/test_batch9_reconciliation*.py` files and `backend/tests/batch9_reconciliation_fixture/sitecustomize.py` | Owned PostgreSQL/SQLite, migration, atomicity, real native CLI and supervisor/adapter/orphan process controls with an inert registry. |
| `batch9-reconciliation-evidence/` and this unique handoff | Append-only author receipts, independent reviews/verifiers, writer census, read-only production census template, operator procedure, provenance, cleanup and delivery mapping. |

No native acquisition/dispatch runtime, ETL/bootstrap, sibling batch files,
frontend, requirements/lockfiles, workflow settings or shared primary checkout
was changed. Dispatch remains default-off and OAG→audits-only.

## Actual verification and red/green evidence

| Execution owner and receipt | Result |
|---|---|
| Author `final-current.json`: Python 3.13.9 / SQLAlchemy 2.0.46 | 102 passed, 0 failed, 0 skipped, 0 xfailed. |
| Author `final-minimum.json`: owned Python 3.12.15 / SQLAlchemy 2.0.23 | Same 102-test selection: 102 passed, 0 failed, 0 skipped, 0 xfailed. |
| Independent behavior `behavior/{current,min}-final-stable.json` | Same 91 named controls on each runtime; no source drift, skips or unresolved failure. |
| Independent Spec `spec-review.md` | Same 20 repaired correlation, atomicity, new-owner, autocommit, preclaim and migration controls on each runtime; 20 passed each, zero skips. |
| Independent Standards `standards-review.md` | Boundary/source/procedure review and actual separate adapter refusal plus slow PostgreSQL update/expiry controls on current and minimum runtimes; no remaining blocker. |
| `scoped-critical-lint.json`; `app-import-{current,minimum}.json` | Scoped critical lint and model/operator/app imports passed. Imports did not run app lifespan/bootstrap. |
| `delivery-manifest.json`; `cleanup.json` | 39 machine receipt generators, nine tested-source commit mappings and 397 census hashes verified; only owned local container stopped; no temporary clone DB/session/process leftovers. |

Counts overlap; they must not be added as unique coverage. Author final command:

```text
<runtime> -m pytest backend/tests/test_batch9_reconciliation.py backend/tests/test_batch9_reconciliation_constraints.py backend/tests/test_batch9_reconciliation_processes.py backend/tests/test_batch9_reconciliation_migration.py backend/tests/test_batch8_exclusion_sqlite.py -q --tb=short
```

Each receipt records exact command, clean owned-target environment, runtime,
source/generator hashes, raw output and exit code. Both final selections include
actual PostgreSQL migration/history/RLS/owner-role and PUBLIC permission checks,
SQLite batch migration/index history and valid subsequent real native and
dedicated runs. Process controls use actual CLI/supervisor/adapter code with
inert audited effects, SIGSTOP/SIGKILL groups, live orphan discovery and database
backend termination. No actual source/provider/storage/auth API was invoked.
Behavior controls separately exercise new TCP admission refusal, blocked
concurrent admission reopening, old-plan restart refusal, precommit backend
loss/rollback and explicitly injected **postcommit report loss**, followed by
durable readback. The report-loss wrapper is identified in its receipt.

Preserved failures establish specific repaired defects:

| Red receipt | Failure before repair; final disposition |
|---|---|
| `whitespace-red.json` | 36 failed / 10 passed: actual PG/SQLite accepted whitespace-only operator text. Unicode whitespace CHECK repair verified on both runtimes. |
| `initial-core.json`, `correlation-effects-red.json` | Explicit-null legacy tags, native foreign dispatch tags and effects changed after operator census were accepted. Final strict correlation and inspect→sign→plan→apply census binding refuse them. |
| `unicode-record-red.json` | Accepted long Unicode evidence overflowed the durable 4000-character field when ASCII escaped. Durable text now preserves Unicode and is prevalidated. |
| `minimum-valid-apply-red.json` and independent `behavior/min-valid-red-rollback.json` | Actual SQLAlchemy 2.0.23 valid apply failed on ORM metadata annotation. Pure table Core DML fixes native/legacy apply; failed attempts rolled back. |
| `mutation-expiry-red.json` and Standards historical slow-update control | Evidence expired during writes but release committed. Final in-transaction evidence/maintenance/continuity checks now roll everything back. |

Earlier setup/verification failures remain classified honestly: Spec minimum's
irrelevant `--no-cov` option failed before collection; Standards first adapter
fixture ordering failed; behavior finalizers had unsuccessful setup attempts.
Historical Standards embedded diagnostics identify earlier generator/source
hashes and are not final acceptance receipts. Final verifiers and final machine
receipts are retained with matching generator bytes. The two
`full-*-candidate.json` runs reported 102 passed / 21 skipped because the original
Batch 8 PostgreSQL fixture hardcodes another port. They are **not acceptance
evidence**. Final selections have zero skips and make no claim to have executed
that unrelated hardcoded-port selection. No hosted CI execution is claimed.

## Operator use and unresolved dependencies

Read `batch9-reconciliation-evidence/operator-procedure.md` before any actual
operation. The source census covers 397 files, 15 registered domains and 1218
candidate anchors; it is not a deployed-host discovery receipt. Every configured
host/scheduler must attest all ten writer categories, including #581 legacy ETL,
#582 bootstrap, native jobs/manual calls, supervisors and orphan adapters,
ordinary application/provider clients, AutoSeeder, Parliament and manual SQL.
Signatures authenticate trusted statements; they do not prove omitted hosts or
false process-death claims. PID and process birth identity, external effects,
launch/reconnect/restart fences and independent policy deployment remain real
operator responsibilities.

The tool requires an independently certified retained **direct PostgreSQL**
connection, actual superuser/catalog visibility, target-wide closed database
admission, no other target backends and no prepared transactions. These strict
requirements are locally proved on PostgreSQL16. Actual Supabase feasibility,
provider privileges/control and pooler-client admission are **UNVERIFIED** and
may make this implementation unavailable there. There is no reduced-visibility
or unlocked fallback. The effect census refuses above 100000 rows per public
table, above 1000 selected/history observations or statement bounds; non-public
and external effects also require operator review. Whole-DB outage/readiness and
automatic restart control must be approved before use. Evidence timestamps
invalidate evidence, never automatically restore fences or reclaim claims.

Coordinator-reported production facts, not author inspection: PostgreSQL17.6 via
transaction pooler port6543, deployed revision `ea1645a4c0b5`, no dispatch/claim
tables; two untagged fiscal_summary and one national_budget RUNNING observation.
The actual pooler read-only probe survived 1020.0017 seconds with the same backend
and diagnostic advisory lock, then rolled back. That bounded observation does
not certify other cutoffs/direct mode or host quiescence. Current Render commit
`2d3cd5959df1914bf068cb0381057d1bcbbabf81` is pinned, Auto-Deploy is off; deployed
startup unconditionally calls `initialize_reference_data`, so AUTO_SEEDER=false
does not fence bootstrap restart. Current workflow/CI repair and rollout gates
belong to the coordinator. **All three production observations remain untouched.**

All local review findings were repaired in scope. No duplicate follow-up issue
was created after the open/closed issue census. #583's actual census/effects,
provider/policy/host evidence, authorized outage, migration/activation, real
reconciliation and restoration remain pending. #581/#582 integration and the
parent #572/#554/#545 gates remain with their owners. This draft does not close
any of those issues and must never be merged by this author session.

## Resume and retained state

The managed worktree, owned runtimes and stopped local container data are
retained. Container identity is
`b70fa66e1693ac4c41ce20a58142672631367db1208630c08da59b2a7b62d843`, name
`batch9-reconciliation-a46a-db`, loopback port55493, migrated template database
`batch9-reconciliation-a46a`. Verify that exact identity and the free owned port
before restarting it for review; never repurpose an unrelated service. Tests
clone/drop distinct prefix-owned databases. Reviewers can rerun with the
receipt's exact environment and use a **new** receipt name:

```text
.batch9-min/bin/python batch9-reconciliation-evidence/run_receipt.py review-minimum .batch9-min/bin/python -m pytest backend/tests/test_batch9_reconciliation.py backend/tests/test_batch9_reconciliation_constraints.py backend/tests/test_batch9_reconciliation_processes.py backend/tests/test_batch9_reconciliation_migration.py backend/tests/test_batch8_exclusion_sqlite.py -q --tb=short
```

Only restart/stop this retained fixture under the corresponding local review
scope. Finalizers and cleanup receipts are append-only; inspect their named
outputs instead of overwriting them. Do not reuse fixture keys or local evidence
as production authority. Before resuming dependent work, verify PR #584's exact
head, final delivery SHA, unresolved GitHub reviews and operational gates.

Reusable lessons supported by the red/green receipts: bind the operator's
effects decision to the census **before** planning; exercise actual minimum
runtime DML; check evidence freshness after mutation as well as before it;
preserve Unicode while enforcing storage bounds; and distinguish authentic
operator statements, database fences, process death and durable commit outcomes.
