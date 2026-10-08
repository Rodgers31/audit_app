# Batch 3 status and next work

2026-10-08. Baseline main: `e9da7c7e7149bddb54eb917cd391f4b67ccd827d`.
The three implementation agents and root's integration/review work are complete.
No unfinished or interrupted coding assignment remains in this batch. Branches
are prepared for draft PR review; this batch does not merge them or enable live
publishing/storage.

## Where the work is

All managed worktrees live under `/Users/roger/.codex/worktrees`, with repository
directory `audit_app` inside each. The dirty primary checkout was not used for
product edits. The public-data/egress PR #510 remains outside this batch.

| Owner | Worktree | Branch | Delivered work |
| --- | --- | --- | --- |
| Schedule agent | `social-schedules-batch3` | `codex/social-schedule-management` | Global filters/counts/pages, guarded schedule actions, preserved history across revisions, compact paginated history UI |
| Media agent | `social-maintenance-batch3` | `codex/social-media-maintenance` | Conservative grant/settlement ledger, reconciliation port, bounded maintenance, historical reference locking and migration |
| Native agent | `social-adapters-batch3` | `codex/social-native-meta-adapters` | Native Facebook Page and Instagram image slice, durable provider checkpoints and official capability evidence |
| Root | `social-batch3-integration` | `codex/social-batch3-integration` | Shared material/runtime/approval boundaries, migration/reference integration, independent regressions and combined verification |

Detailed briefs:

- Schedule: `SCHEDULE_MANAGEMENT_HANDOFF.md`.
- Media: `backend/social/media/README.md`.
- Native adapters: `backend/social/adapters/README.md`.
- Native integration: `NATIVE_INTEGRATION_HANDOFF.md`.
- Accepted shared contracts and ownership: `BATCH_3_CONTRACT.md`.

Schedule and media PRs target main independently. Native publishing is stacked
on the media branch because exact provider fetch access requires its signed
expiry contract. Its PR diff contains only native/material integration changes.
After media merges, retarget native against main and verify that final base.

## Executed evidence

- Combined backend social suite: **1,095 passed, zero skipped**. All four
  explicit local PostgreSQL lanes were configured, including the migrated
  API/worker cascade and immutable-history tests. The only warnings were the
  two existing SQLAlchemy declarative-base deprecations.
- The native branch with its media prerequisite independently passed **1,016
  backend tests, zero skipped** after branch separation. The schedule branch's
  independent history/boundary lane passed 52 tests; its migrated cascade and
  immutable-history lane passed two more.
- Frontend social/composer suites: **432 passed**; connection suites:
  **42 passed** (474 total across 26 suites).
- Whole frontend TypeScript check and owned social lint passed.
- Actual component exports and browser fixtures passed at 1440, 768, 390 and
  320 pixels, including scheduled controls and revised-post history.
- Independent native review passed **240** bounded SQLite/fake-provider tests;
  root separately executed the PostgreSQL lane. Media review exercised exact
  signed version/expiry/HEAD checks and after-intent credential rotation.
- Alembic has one head, `b73e19a4f602`; media settlement/backfill, historical
  references, maintenance ordering, schedule claims and native restart/recovery
  were executed on PostgreSQL.

The database was a privately unpacked disposable PostgreSQL 18.6 instance,
bound only to 127.0.0.1:62124. Test fixtures reject other hosts/ports/databases
and isolate domain/integration schemas; truncating worker tests ran serially.
No existing service was restarted, shared package installed, production
migration run, or live provider/storage operation performed.

Observed regressions were retained before fixes: hidden historical receipts,
pagination/deadline overflows, malformed credential admission and signed URLs,
foreign object versions, missing runtime dependencies, compact account metadata
and persisted capability restrictions being silently relaxed. Positive native
and material baselines remain in the same test lanes.

## What should happen next

1. Review and merge the schedule and media PRs; then retarget/review native on
   main. Keep each scope's validation and handoff with its PR.
2. Complete #490's separately authorized private social R2/CORS/host acceptance,
   storage inventory and independently reviewed write-quiescence evidence.
   Production verification remains unsupported; uncertain reservations remain
   visible and retained, and ready-original deletion stays deferred.
3. Complete #488's Meta app/account permissions, reconnect material, role and
   public-readback acceptance for the exact supported native slice.
4. Complete #481's representative hosting/egress, backup, retention and quota
   receipts. Source-evidence R2 acceptance does not prove social media acceptance.
5. Only after those receipts and an explicit enablement decision, assemble the
   real runtime and run the separately authorized bounded live acceptance.

Broader formats, Threads, X and TikTok stay behind their own complete connection,
capability and recovery workstreams. The next priority is completing the current
slice's review and operational evidence.
