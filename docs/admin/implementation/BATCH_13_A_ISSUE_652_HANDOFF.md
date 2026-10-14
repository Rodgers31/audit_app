# Batch 13 Lane A — bootstrap source registration (#652)

This bounded continuation uses the existing owned checkout
`/Users/roger/.codex/worktrees/ebbf/audit_app` on separate branch
`codex/batch13-bootstrap-source-652`, from assigned accepted main
`c8970e3953717fc0f0ca3a54e22f7e3e509eec0f` (tree
`1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8`). The prior open draft PR
[655](https://github.com/Rodgers31/audit_app/pull/655), head
`e82339a1459e5032c6fc2847086418995e15a709`, and its immutable delivery remain
preserved. That independent wrapper outcome repair is not included in this
branch.

The appended coordinator exception in canonical
`NEXT_AUTHORS_V1/OWNERSHIP_RESOURCES.md` and
`CONTINUATION_SCOPE_EXCEPTIONS_V1.json` permits only `backend/bootstrap.py`,
focused tests and this unique handoff for #652, using native port 55564.
Dirty primary and peer checkouts are untouched. Draft PR identity and the exact
final published head/tree are bound in this continuation's external
`DELIVERY_V1.json`; the source commit containing this handoff can also be read
with `git log -1 --format=%H -- docs/admin/implementation/BATCH_13_A_ISSUE_652_HANDOFF.md`.

## Defect and repair

On a fresh database migrated through the actual accepted Alembic chain to
`e602b11a0001`, bootstrap created its national source registration without a
URL and inherited the model's AVAILABLE default. The validated migration 3c
check `ck_source_documents_available_has_url` correctly rejected that INSERT.
The actual cold failure retained all 17 acquired claims and a FAILED bootstrap
observation; early country and fiscal-period commits survived. An exception is
not a no-effect guarantee.

Bootstrap performs no publisher acquisition. Its new registrations now start
FAILED, matching migration 3c's truthful unfetched state. A URL or a caller's
metadata digest alone cannot earn AVAILABLE here. Existing registrations keep
their ID, publisher, locator, status, digest, HTTP/verification evidence and
recorded acquisition date; refresh only merges the existing bootstrap metadata.
The old fixed-date overwrite was not evidence of another download.

The helper has one live production caller, `_seed_national_data`. Both
weekly/manual bootstrap and unchanged `main._startup_sequence` enter that
caller through `initialize_reference_data`, including the county fast path and
force refresh. Retained-owner refusal occurs before it. All those paths share
this repair; the bootstrap result, required-reference checks and ownership
acknowledgement/refusal policies are unchanged.

New FAILED source registration does not imply a FAILED ingestion job. Real
reference and budget work may complete while this unfetched source remains
unavailable. No official URL, acquisition receipt, verification classification,
figure correction or blanket historical upgrade is invented. Existing GDP,
economic indicator, poverty, debt, financial publication and other source-domain
policies remain unchanged. The fresh #137 complete body and all 26 comments were
read for this distinction; its approved bounded storage acceptance does not
certify every historical source.

## Reproduction and local acceptance

Evidence root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH12_CONTINUATION_V1/NEXT_AUTHORS_V1/A_bootstrap_outcomes/ISSUE652_CONTINUATION_V1`.

The exact prior real native cold red is reused by
`NATIVE_RED_REUSE_V1.json`: the bootstrap hash matches assigned base Git bytes,
and original packet, producer, invocation, profiles, stderr and complete census
hashes are bound. It records CheckViolation/exit 1, early committed effects,
FAILED observation and 17 retained claims. The original packet's whole source
also includes PR655 tests/docs; only its identical bootstrap/base-wrapper
execution is reused here. No new execution is claimed by this readback.

The new seven-case regression fixture was executed before repair. Its first
version produced four intended availability failures and three passes; with a
distinct stored acquisition date, all seven cases failed for the intended
availability/date defects, with zero skips. After repair, the focused selection
passed 81 cases on each supported current/minimum runtime, with zero failures,
errors or skips. SQLite tests establish helper/caller and policy behavior;
they do not install the PostgreSQL migration check.

The native generator executes the actual unchanged bootstrap, packaged
national-budget handler, unchanged startup and actual readiness response handler.
No bootstrap, domain or startup function is substituted. External Python socket
transport is refused; borrowed runtimes/native PostgreSQL are read-only. The
owned native cluster binds only 127.0.0.1:55564 and each case has a distinct
bounded nonce database name, exact creation and pre-disposition identity checks.
The baseline target is explicitly `e602b11a0001`, not audit `a611b12a0001`.

Twelve distinct scenarios are repeated across current/minimum and normal/-O
child cohorts in the final packet:

| Scenario | Actual contract |
|---|---|
| Bootstrap fresh / legacy | True; 47 counties, one FAILED/no-URL bootstrap registration, completed reference/budget observations and producer acknowledgement of all 17 claims |
| Startup fresh / legacy | The same real bootstrap effects; actual readiness handler returns 200 |
| Bootstrap replay | Two True returns, same registration, 47 counties, four completed observations and 34 producer-acknowledged claims |
| Bootstrap / startup retained owner | False, same retained claim, no new job or committed public row/sequence effect; startup without references remains 503 |
| Startup retained owner with references | False, unchanged rows/sequences and same claim; readable canonical references permit 200 without admitting startup writers |
| Bootstrap / startup incomplete budget | False after reference effects, completed reference/FAILED budget observations and one retained budget claim; startup references remain readable |
| Bootstrap / startup missing claim schema | Actual UndefinedTable with unchanged complete public rows/sequences; direct bootstrap exits 1 and startup reports reference_initialization_failed/503 |

Both before and after snapshots include all 53 public tables and all 30
sequences, including last_value/log_cnt/is_called, plus the actual validated
source-document constraint. Legacy-source controls retain the exact prior ID,
FAILED/no-URL state, date and migration history. Actual child interpreter,
optimization, SQLAlchemy, configured/resolved database URL, dotenv/storage/cache,
role/database/cluster identity and literal returns are measured. Startup invokes
its real local scheduler path; only those newly created scheduler instances are
shut down, with explicit stopped-state readback in final producer v5. The producer
and reader require one observed running/stopped scheduler for admitted startup
and zero for paths that do not enter it; an absent observer cannot certify stop.
Readiness
is the actual handler's JSONResponse; this is not deployed HTTP middleware,
browser or production acceptance.

The strict saved reader uses explicit checks that survive -O, requires the
closed twelve-case inventory and actual typed outcomes, binds all sidecars and
the complete NUL-delimited source inventory, and independently decodes effects,
claims, jobs and sequence states. Independent Spec and Standards final reviews
and their executed controls are bound by the final delivery. Controlled helper
and receipt-reader negatives are qualified separately from native integrations;
overlapping executions are not additional unique scenario coverage.

## Preserved failures and remaining boundaries

The first native continuation attempt failed before any case because its macOS
Unix socket path exceeded PostgreSQL's 103-byte bound. Version 2 corrected only
the owned temporary path, then its first child exceeded the unchanged 45-second
bound while the profiler resolved every return-frame path. That timeout remains
FAILED; its partial child stdout/stderr were not retained by that recorder, so
no complete child diagnostic or timeout-cause certification is claimed.
Version 3 restricts path resolution to the two measured function names and
passed all twelve development cases; that successful replay does not prove the
sole cause of the earlier timeout. Version 4 adds the review-requested actual
post-shutdown scheduler state; version 5 also closes the expected observer
inventory. Version 4 and reader v2 were not executed as acceptance. Prior
generators, failure packets and logs are
unchanged; development v3 is qualified as scheduler shutdown invocation plus
child exit, not post-shutdown state acceptance.

Final delivery distinguishes development runs from clean published-source
tests/native cohorts, binds the exact source/PR/remote head and independent
physical cleanup, and records current storage growth. The unchanged original
baseline, shared 10-GiB limit, 180-second deadline and corrected a23 guard apply.
Temporary clusters/databases and port use end with owned identity readbacks;
the worktree/branch remain for review.

Lane D's `BASELINE_RELEASE_CONTRACT_V3.json` and exact published source
`9cb9cfc37d7c8881e857892171eb38e8bac4ca62` were read and hash-matched. That
contract explicitly remains preparation-only: production_ready=false and
production_execution_authorized=false. #545/#583/#554/#611 release criteria,
the coordinator's combined hosted acceptance and merge/issue disposition remain
pending. No retained claim is reconciled or manually released, no Actions
activation/dispatch or paid review is requested, and no production/provider
operation or dirty-primary/peer cleanup is performed by this lane.
