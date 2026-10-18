# Issue 727 — audited soft archive

Implementation commit: `0bad426a9f924c2e7d5bc3e3aca6ba8029766a00`.
Pinned baseline: `5189675364648113c92b46b54d8f6a30b1bf00e2` (schema `a705b15a0001`).
Branch: `codex/b16-727-soft-archive`.
Worktree: `/Users/roger/.codex/worktrees/b16-727-soft-archive/audit_app`.
This handoff is a documentation-only follow-up to that tested implementation; the PR and external final manifest identify the branch's final head.

## Behavior and retention decision

`POST /api/v1/admin/social/posts/{id}/archive` uses the existing administrator boundary, strict positive expected version, UUID idempotency key and private/no-store response. The command locks and checks every publication/target, including superseded revisions. It atomically writes `editorial_state=archived`, `archived_at`, the incremented row version, an actor/request-bound `post.archived` audit, and the command receipt. Audit/post/receipt rows are read from the database rather than trusted from the ORM cache; suppressed/altered and deferred receipt effects cannot certify success. Existing receipts without additive archive metadata remain replayable.

Eligible editorial states: draft, pending review, approved and rejected. Eligible delivery state: no authorization, independently cancelled empty authorization, or exclusively terminal published/failed/cancelled targets with no queued action, due action, lease or unfinished attempt. Ready approval, scheduled/queued/claimed/processing/retry/reconciliation/blocked/ambiguous work refuses clearly. Archive never requests cancellation, changes publication/target/attempt records, or implies remote deletion. Cancellation and reconciliation remain independent workflows.

The original stays read-only and discoverable in the Archived queue, including delivery history and links. No in-place restore is promised. **Duplicate as new manual draft** recovers retained content/references into a separate post, with no copied authorization or deliveries and with fresh validation/review required. Asset admission still applies. The original and its references, revisions, approvals, source events, audit and delivery evidence remain retained; archive does not free asset bytes, expire business history or impose a new deletion policy. Compact command receipts retain their existing 30-day policy; replay after receipt retirement cannot archive an already archived post again. Later retention/privacy decisions remain independently authorized operations.

Archived edit/review/authorization/schedule/cancel/resume/retry commands fail closed. Worker claim and final operation admission also exclude archived state/timestamp. Generated policy commands use the same command guard. Later source observations can create a new draft while retaining the archived predecessor without trying to cancel it again.

## Executed validation

- Owned PostgreSQL17, complete pinned migration chain through `a705b15a0001`: 14 focused cases cover forced archive/approval/queue orderings, worker claims and final admission, concurrent replay/restart, audit failure, suppressed/altered evidence, deferred receipt removal and rollback. The database URL is guarded to this issue's disposable loopback database.
- Selected backend scope: 150 tests on cached Linux Python3.12.15 in normal and optimized modes, and 150 in local Python3.13.9 optimized mode. Local normal runs cover the same 136 non-PG +14 PG selection. SQLAlchemy2.0.54 / Pydantic2.14.1. These are overlapping runs, not additive coverage counts.
- Node22.19.0, owned `npm ci` with unchanged exact lock: 554 social UI tests, full TypeScript check, and a production Next15.5.27 fixture build passed. Earlier borrowed dependency runs were preliminary and are superseded by matching-lock receipts.
- Real extension-controlled Chrome: create v1 → edit v2 → archive v3 → recover separate manual draft v1 → open original from Archived queue. Actual local API/PostgreSQL readback: 2 posts, 3 revisions, 4 audits/receipts; zero publications, targets, attempts and media assets, publishing false. Identity is explicitly inert; this is local product-flow evidence, not production/provider acceptance. The retained production verification draft was untouched.

## Independent reviews and red/green findings

Standards and Spec agents reviewed the pinned baseline candidate independently before the implementation commit and executed hostile shapes/failure paths. Final implementation diff SHA256: `9d004c451bd735bb3dc513cf44d20cfa869ee6fee273746b4970279476a8a053`. No unresolved confirmed finding remained; final committed-head readback is retained externally.

Valid findings reproduced before correction: pending archive could overwrite edits; source supersession tried cancelling archived predecessors; suppressed/altered audits and suppressed/deferred receipts could claim success without durable evidence. Each has retained red/green execution. The baseline archived-row edit regression was observed failing with `DID NOT RAISE` on the pinned source, then passing after the guard. A suggested deferred audit-delete gap was refuted by actual migrated immutable-history triggers; no trigger/deferral safeguard was weakened.

## Integration and remaining checklist

Shared edits: `backend/social/api.py`, `service.py`, `generation/service.py`, `worker/repository.py`; frontend API decoder, Composer, Results and Workspace. New archive domain/UI modules are scoped; Studio and provider adapters are untouched. Siblings editing these shared files need ordinary integration review. No dependency, schema, grants, role contract, feature flag, resource or deployment changes. Existing publishing/uploads/native processing/supervisor activation remains unchanged; no production or remote action was used.

Evidence root: `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B16/ISSUE-727/`. It includes review reports/scripts, source manifests, genuine Chrome screenshots/AX text/SQL counters, runtime parity, red/green logs and cleanup. No bulky logs or screenshots are committed.

Remaining: coordinator integration/acceptance, authorized merge/release and fresh review-state check at that boundary. GitHub Actions stays disabled; no hosted CI or formal GitHub approval is claimed. Issue727 and parent476/545 remain open until accepted merge. Separate worker/provider/storage/recovery operating qualification remains outside this capability. No known unresolved engineering blocker for this draft.
