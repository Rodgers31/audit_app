# Batch 12 durable admin audit storage handoff

Updated 2026-10-12. Addresses #611, parent #545. This is an incomplete local
implementation checkpoint. Real PostgreSQL and browser acceptance remain
blocked; no push, draft PR, merge, deployment, or production certification has
occurred. The migration must not be treated as an accepted rollout target.

## Source and ownership

- Accepted base: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree
  `3a680eef19822ef0ac83aa6890c3b41deee97058`.
- Tested implementation commit: `e9c2ec91cf4ad8ae49171d59503282125214a5d2`, tree
  `53e3b0d8bc1fe5f02bcec5a4ca7faae7a48acd44`.
- Branch: `codex/batch12-durable-audit-storage`.
- Owned checkout:
  `/Users/roger/.codex/worktrees/batch12-durable-audit-storage/audit_app`.
- External evidence directory (called `EVIDENCE` below):
  `/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/AUDIT_STORAGE`.
- `EVIDENCE/MIGRATION_CONTRACT.json` records the exact source hashes and design;
  `EVIDENCE/STATUS.md` records the latest checkpoint/publication state. The later
  commit adding this handoff changes documentation only; its identity is recorded
  externally to avoid a self-referential commit hash.

The dirty primary checkout was not edited, reset, stashed, or used for installs.
Models changed only for audit storage. Existing migration ancestry, main router
registration, dispatch/reconciliation writers, dependency files, global Actions,
and historical evidence packets were preserved. No provider operation occurred.

## Implemented contract

Revision `a611b12a0001` descends directly from accepted `e602b11a0001`.
The migration adds `admin_audit_provenance` and singleton `admin_audit_storage`,
plus a validated positive audit ID check. Audit log columns and existing writer
INSERT statements retain their shape. An ALWAYS AFTER INSERT trigger atomically
captures `pg_current_xact_id()` as ordinary full-width `xid8`, with the storage
incarnation, in the writer's transaction. Savepoints therefore retain the root
transaction; rolled-back audit inserts and their provenance disappear together.
Raw SQL writes use the same seam. The historical migration freezes its function
bodies instead of importing mutable application code.

ALWAYS BEFORE UPDATE/DELETE/TRUNCATE triggers make the log and provenance append
only. `audit_log_reader` and `audit_log_writer` are restricted NOLOGIN groups.
All three tables have RLS and private ACLs. The reader receives SELECT on the
three tables and EXECUTE on the restricted identity function. The writer receives
SELECT on the log, INSERT on its seven existing input columns, and sequence
USAGE; it receives no provenance/state mutation or SELECT authority. Existing
owner writers retain their transaction ownership. PUBLIC and existing
anon/authenticated table and column ACLs are revoked; effective inherited public
authority refuses migration/admission. Reused groups must have six false role
flags, no parent memberships, and no public-schema CREATE authority.

The already-mounted production router now uses the durable service. An explicit
`ADMIN_AUDIT_DATABASE_URL` supplies a separate restricted reader engine with
REPEATABLE READ isolation; writer sessions are not switched with SET ROLE.
Admission verifies actual isolation, effective reader/public privileges, RLS,
ordinary permanent tables, validated constraints, exact policies and frozen
ALWAYS triggers, and singleton storage identity. Admission and row reads use one
repeatable-read population. Wrong or unknown evidence returns the existing
private sanitized unavailable response.

The stored incarnation alone is insufficient. Admission also requires external
`ADMIN_AUDIT_INCARNATION` and a 32-byte hex `ADMIN_AUDIT_BOOKMARK_KEY`, certified
storage, and actual system identifier/database OID/timeline outside recovery.
Migration creates a fresh incarnation with `certified=false`; it supplies no
production certification procedure or automatic legacy backfill. Any audit row
with unknown, mismatched, or invalid provenance refuses the entire dataset before
client filters. Prepared transactions in the current database also refuse.

Signed v3 bookmarks bind the requesting actor, incarnation, full `pg_snapshot`,
UTC capture time, and audit ID ceiling. Existing expiry, filter transfer, bounds,
redaction, ordering, actor authorization, and private/no-store behavior remain.
The visibility predicate uses `pg_visible_in_snapshot(root_xid, pg_snapshot)`.
The ceiling is computed over the visibility-qualified population before filters,
so an empty filter can later transfer to a filter containing visible rows.
SQLite retains its local behavior; it does not certify PostgreSQL provenance.

## Recovery, maintenance, and rollback limits

- Ordinary VACUUM FREEZE and VACUUM FULL are intended to preserve stored root
  provenance and issued populations. Their real SQL controls have not executed.
- Trigger bypass, logical import/rewrite changing values, historical backfill,
  retention, and prepared-transaction use are unsupported for admission.
- Restore/PITR/clone/promotion/import must revoke the external incarnation before
  service startup. Storage stays unavailable pending a separate reviewed
  provenance/custody design. Do not certify restored history.
- Actual system/database/timeline checks reject distinguishable clones. A
  byte-identical physical clone with copied external custody authority cannot be
  distinguished by this design and is explicitly outside the supported contract.
  Catalog damage and an unexecuted TEMPLATE-clone test are not real restore proof.
- Migration requires the dedicated worker stopped, with lock/statement timeouts
  of 2/30 seconds. Partial/preexisting audit objects, ambiguous worker evidence,
  unsafe roles, recovery, and nonpositive existing IDs abort transactional DDL.
- Downgrade refuses any audit history or certified state. Only an empty,
  uncertified database may remove the new objects. It retains private audit RLS
  and global group roles, which can serve another database. It does not erase
  history or restore public access. Repeat Alembic upgrade is intended as a no-op.

These are implemented design semantics awaiting actual PostgreSQL acceptance,
not verified production operating procedures.

## Actual verification

All final cohorts below ran against the clean implementation commit above, with
unchanged before/after source inventories and terminal absent child groups.
Counts overlap and must not be added as independent coverage.

| Receipt under EVIDENCE | Runtime | Actual result |
|---|---|---|
| `FINAL_CONTRACT_CURRENT_NORMAL` | Python 3.13.9 / SQLAlchemy 2.0.54 | 96 passed, no failures/errors/skips |
| `FINAL_CONTRACT_MINIMUM_NORMAL` | Python 3.12.15 / SQLAlchemy 2.0.23 | 96 passed, no failures/errors/skips |
| `FINAL_CONTRACT_CURRENT_OPTIMIZED` | Current, actual optimize flag 1 | Same 96 passed, no failures/errors/skips |
| `FINAL_CONTRACT_MINIMUM_OPTIMIZED` | Minimum, actual optimize flag 1 | Same 96 passed, no failures/errors/skips |
| `FINAL_PG_SETUP_CURRENT` | Current | 1 pure body-equality pass; 44 database setup errors; exit 1, NOT_ACCEPTED |
| `FINAL_PG_SETUP_MINIMUM` | Minimum | Same 1 pass / 44 setup errors; exit 1, NOT_ACCEPTED |
| `FINAL_ALEMBIC_HEADS.json` and raw streams | Both runtimes | CLI exit 0; single `a611b12a0001 (head)`; no SQL DDL executed |
| `FINAL_CANONICAL_INVENTORY.json` | Unchanged canonical launcher | Both new tests and both changed migration modules selected by default core inventory |

The 96-case cohort includes actual SQLite/FastAPI privacy and writer controls,
strict issuer/catalog transport controls, and a filter-transfer regression test.
The optimized invocations explicitly use `EVIDENCE/record_optimized.py` to set
PYTHONOPTIMIZE=1 and include the actual flag in the runtime probe. They are not
unmodified canonical producer invocations. Its identity and the unchanged
`record_v2.py` producer identity are printed in each retained invocation log.
Each receipt retains stdout/XML, exact source inventory, runtime, command,
allowlisted inert environment, exit states, and process cleanup.

`filter-transfer-current.json` and `filter-transfer-minimum.json` retain a real
SQLite red/green reproduction of a regression introduced in this lane's earlier
candidate: an empty filter issued ceiling 0 and hid rows on transfer; the final
route issues ceiling 1 and returns the visible row. This does not explain the
original #611 epoch defect. Earlier exploratory setup failures are not behavioral
red evidence, and incomplete original tool output is not claimed as preserved.

Independent read-only adversarial replays are retained in
`ADVERSARIAL_BOOKMARKS/FROZEN_FINAL_REPORT.md` (246 cases per normal/-O run,
including 57 HTTP controls using explicit database/capability doubles) and
`ADVERSARIAL_STORAGE/frozen-replay-ecca1e31/REPORT.md` (182 capability, two engine
argument, and 57 migration transport controls per mode). Both bind exact final
source hashes. They verify Python boundaries only, not SQL behavior or actual
visibility populations. Earlier failures and predecessor reports remain intact.

## Blocker, resources, and unfinished acceptance

Docker Desktop's startup log reports no space left on device. The latest bounded
observation in `FINAL_RESOURCE_OBSERVATION.json` had 800,727,040 bytes free;
Docker info timed out at 10 seconds. Its owned command group was terminated and
proved absent. PG55545/API18045/UI13045 were bindable with no fixture listeners.
The original `epoch-prepare.log`/`epoch-state.json` remain preserved (`ready=false`,
no reset container ID). The absent base state plus helper source ordering show
that attempt did not reach its resource-creation calls; they do not prove global
Docker resource absence while the daemon is unavailable.

Only this lane's enumerated disposable runtime bytecode was removed:
`owned-bytecode-cleanup.json` records 239,974,527 bytes, hashes, and absence.
Owned current/minimum runtimes and all evidence remain available. No broad
process killing, Docker prune/reset, or peer artifact deletion occurred. No
owned database/browser resource was successfully provisioned. Managed worktree
and evidence are retained for continuation.

Required next steps, in order:

1. Restore host disk capacity and Docker readiness. Use fresh helper state/log
   paths with the unchanged canonical pinned epoch fixture and owned prefix
   `batch12-audit-storage-`, strict PG55545, explicit inert environment, verified
   image/nonce/database/owner/resource identities, and terminal cleanup receipts.
2. Execute the original actual epoch-zero positive and epoch-one intended-failure
   route controls, then retain the same symptom's post-migration pass. The old
   route archive and literal historical launch test functions are preserved.
3. Run all 44 mandatory real SQL cases on current/minimum runtimes, plus the
   existing retained prototype/privacy controls and both changed migration
   cohorts. They cover late lower-ID root commits, epoch visibility, concurrent
   state changes, both filter-transfer directions, actor/MAC modification,
   raw/ORM/savepoints, effective ACLs, rollback/uncertain commits, legacy/partial
   schemas, historical upgrades, repeat preparation, freeze/rewrite, clone/
   incarnation, retention refusal, and downgrade limits. Resolve actual SQL
   findings with retained predecessor failures; these cases are unaccepted now.
4. Execute `frontend/browser-fixtures/admin-audit-epoch/durable.config.ts` against
   the new `browser_api.py` migrated production route. It reuses unchanged browser
   controls, selectors, assertions, retries, and deadlines with actual inert JWT
   authentication. Frontend installation and browser run have not occurred.
5. Resolve coordinator-owned full-head fixture reset compatibility. See
   `FIXTURE_COORDINATION_REQUEST.json`: six older fixture paths TRUNCATE the audit
   log after upgrade head. The new immutability trigger will refuse that pattern;
   actual default-gate reproduction is pending. Use isolated disposable databases
   or coordinated historical targets with independent new-head writer controls.
   Do not weaken the production trigger. No unowned fixture files were edited.
6. Coordinator must validate default prepared-fixture execution and hosted browser
   wiring on an immutable combined source. No global Actions change/dispatch is
   authorized in this lane. Inventory inclusion alone is not hosted acceptance.
7. After meaningful local acceptance, review the final diff, push the finished
   round once, create/attach a scoped draft PR, and read back remote head/body.
   No publication has occurred. #611/#545 and deployed acceptance stay open.

No new defect issue was filed: the shared-fixture dependency is a source census
awaiting runtime confirmation, and the original #611 remains the tracked defect.
No authenticated production/provider state was checked or changed. Rollout
#583/#554 must independently review an exact accepted audit revision as a separate
release step; this checkpoint supplies no production authority.

## Proposed skill improvement

Recommend a narrow update to verify-boundary-shapes/adversarial-verify: require
native boolean identity and exact catalog row arity in authorization evidence,
and label transport-double results separately from actual database acceptance.
For example, the earlier candidate accepted numeric 0/1 catalog flags because
Python equality treats them as False/True; the final guard uses `is` and strict
six-field role evidence. The retained predecessor/final transport reports show
the correction. Global skill files were not edited.
