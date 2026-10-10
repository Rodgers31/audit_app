# Batch 11 — issue 611 handoff

Status: bounded design proof and compatible client bookmark parsing; full #611
acceptance remains unmet. #583 remains open. This draft preserves production's
correct epoch-zero xmin guard and publishes no production schema migration.

## Source and coordination

- Launch main: `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`; tree
  `9d0061928c16d173859f98cb6daa5f2f591b257c`.
- Frozen SPEC SHA256:
  `80c2fb7c6741d43798f49555733655330f412d368e16d3c3983c8f4e0abbcd42`.
- Managed worktree: `/Users/roger/.codex/worktrees/batch11-audit-pagination/audit_app`;
  branch `codex/batch11-audit-pagination`. Primary remained read-only.
- Measured independent review predecessor: `dce199116052356851e99620553914ffa7b25efa`;
  tree `161a96984077c0aaf95569c5baaa3a3a1b0fcd62`. Later author receipts preserve
  their actual dirty source inventories; none is labeled final-tree acceptance.
- Schema request appended on 2026-10-10T14:11:48.476549Z to the assigned
  `ISSUE_611_REQUESTS.jsonl`, proposing owned root-xid storage/capability and asking
  for actual accepted #602 ancestry or explicit reservation release. Approval
  has not been received. A request is not approval. No sibling import/rebase,
  dangling down_revision or guessed migration was authored.
- Exact final remote HEAD/tree and matching tested bytes belong in the separate
  append-only external postcommit binder under the lane artifact directory;
  this handoff names measured predecessors and does not chase its own hash.

## Delivered behavior

The only product change is the scoped `visibilitySnapshot()` hunk in
`frontend/lib/admin/audit.ts`: atomically preserve canonical versioned UUID/xid8
bookmarks using exact uint64 arithmetic while keeping the existing unversioned
parser's uint32 limit. No lock, dependency, shared launcher, router or model edit.

The owned-only executable prototype stores nullable ordinary root_xid as actual
PostgreSQL xid8, assigned by an ALWAYS database insertion trigger from the
writer's top-level transaction. Raw/ORM/savepoint writes share that provenance.
It combines captured transaction visibility with the existing timestamp/ID
ceiling, filters/order/page bounds and private responses. Old, expired,
wrong-scope and future-horizon bookmarks require Refresh. Unknown legacy rows,
missing/unsafe capability, altered RLS/trigger or unsafe reader authority refuse
with sanitized private503. Caller-supplied provenance and UPDATE/DELETE/TRUNCATE
are denied by actual grants and triggers.

The prototype is disconnected from production and restricted to the owned
loopback fixture. Every preexisting row keeps NULL provenance; the dataset refuses
rather than fabricating a backfill. A stored readiness/UUID can be copied by a
restore and cannot certify transaction origin. Restore/PITR/clone/promotion,
prepared transactions, production poolers/roles and retention recertification
remain unsupported. Do not activate this proof on a restored/deployed dataset.
See [DESIGN.md](batch11-issue-611-evidence/DESIGN.md).

## Measured evidence and review

| Evidence | Actual result and limits |
| --- | --- |
| Unchanged launch HTTP/root-writer fixture | Epoch-zero2pass; epoch-one expected200 got sanitized503. Original test bytes retained unchanged; earliest unformatted recorder implementation was not preserved, so those receipts have an explicit origin limitation |
| Owned PostgreSQL17.11 epoch fixture | Clean offline counter adjustment to epoch1/xid1000; real root/savepoint transactions and late lower-ID commits. No natural four-billion-transaction wrap or production reset claim |
| Author complete cohort | Current71pass and minimum71pass, no skips/failures/errors, unchanged inventories. 38prototype +14existing guard +19existing SQLite caller/router cases; scoped compile setup matches the repository fixture |
| Independent Spec at measured predecessor | Current52pass and minimum52pass; normal/optimized verification, unchanged source/status; empty owned tables/roles readback |
| Frontend cohort/gates | 65pass; actual types, scoped lint and npm build pass. Build used inert loopback API while unavailable; public SSR fetch failures are a fixture limitation |
| Actual Chromium/API journey | Epoch-one200/private header, redacted payload, Next/Back URL transfer, new population on filters, expired422/Refresh/unavailable state, anonymous401; explicit cleanup response tables0/roles0, separate empty database and API/UI port readback |
| Artifact regression controls | Original destination/receipt false passes reproduced by author; repaired63controls pass. Later selector/JUnit contradictions reproduced and repaired normally and optimized |
| Standards | No hard violation; one nonblocking possible cleanup duplication smell; all12Fowler heuristics evaluated, actual parser/client/destination checks retained |

Current runtime: Python3.13.9/SQLAlchemy2.0.54. Minimum runtime:
Python3.12.15/SQLAlchemy2.0.23. SQLAlchemy2.0.23/Python3.13 import failure is setup
failure, not a behavioral red. PostgreSQL image identity:
`sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.

The published historical bundle contains exact original receipts, raw XML/logs,
fixture generators, source hashes, report bodies and review dispositions.
[history-index.json](batch11-issue-611-evidence/history-index.json) is a superseding
index; old run.json fields/generator identities were never rewritten. Diagnostic
errors, source-changing attempts and browser lifecycle failures stay unaccepted.
Normal/optimized [verify_packet.py](batch11-issue-611-evidence/verify_packet.py)
checks actual bundle bytes and producer inventory, reporting historical integrity
with current_acceptance=false. The live recorder/verifier replay into fresh
external outputs supplies final local acceptance after commit. Local consistency
cannot authenticate a party able to rewrite all artifacts/hashes together.

Review classifications and concrete repairs are retained in
[REVIEW_DISPOSITIONS.md](batch11-issue-611-evidence/REVIEW_DISPOSITIONS.md).
[README.md](batch11-issue-611-evidence/README.md) provides replay commands.
[LESSONS.md](batch11-issue-611-evidence/LESSONS.md) proposes coordinator-reviewed
lessons only; shared skills and SPEC were read-only. Internal prototype/fixture
failures were repaired here; no independent production defect was asserted and
no new issue was created. Conditional all-state defect census was therefore not
needed for issue creation. Full backend core, real Alembic upgrade, hosted gate
and production/deployment acceptance are not claimed.

## Resource closure and remaining integration

Owned resources use only PG55534/API18034/UI13034. PostgreSQL container
`89a5fe37407e7321d70c91fc15c2bff75fd734afecbe5b67e4af7f2b4b193345`, counter helper
`90812973aac7`, and volume `batch11-issue611-data` have lane/owner labels. After final
replays, remove only those exact owned resources and read back disappearance and
free ports in the external binder. Worktree/branch stay available for review.

Next integration requires coordinator-approved accepted #602 ancestry or explicit
reservation release, an ordered migration preserving unknown history, a truthful
legacy admission/visibility-seal decision, trusted restore/incarnation and
maintenance authority, production model/router integration and actual roles,
full applicable backend/SQLAlchemy and hosted acceptance. Root owns shared
integration, issue disposition and merge. No ready transition, merge, deployment,
paid review request or workflow enable/dispatch is part of this delivery.
