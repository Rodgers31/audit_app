# Batch 1: implementation scope and frozen contracts

Authorized 2026-10-03. Base: `origin/main` at `15cc5e3b3c89c2527e7c9303000da7bfbd03461c`. Follow the [engineering blueprint](../ENGINEERING_BLUEPRINT.md) and [low-cost profile](../LOW_COST_OPERATING_PROFILE.md). This document selects the first safe implementation slice; it does not change the target architecture.

## Deliverable and exclusions

Build the reusable domain, manual draft/admin API, durable PostgreSQL dispatcher and admin draft/composer/results interface. Prove queue behavior with fake adapters on local test databases. No production migrations, account connections, live API calls, real publications, deployment changes or automatic content approval are part of this batch. Real OAuth adapters, media storage/uploads, source-event generation and policy automation follow in later batches.

The composer must represent media and per-platform variants, but actual upload controls show a truthful unavailable state until a storage/upload service is implemented. Tests may use ready fixture media. Do not create a pretend successful upload or seed fake connected accounts into production. Empty connected-account lists mean no account is connected; do not silently fabricate destinations.

Normal server operation has publishing OFF. Worker startup is explicit and separate from the web lifespan. CLI must use an explicitly supplied database configuration and must not auto-load a production `.env` or import `backend.main`. Fake adapters are only available by explicit test construction, never enabled automatically in deployed runtime.

## Workstream ownership

| Agent | Owned code | Constraints |
|---|---|---|
| Domain/API | `backend/social/__init__.py`, `contracts.py`, `models.py`, `service.py`, `validation.py`, `api.py`, `telemetry.py`; one migration; `backend/tests/social/test_domain*`, `test_api*`, `test_validation*`; minimal model/Alembic registration | No `backend/main.py`, deployment or worker code; create stable contracts/models first |
| Worker | `backend/social/worker/`; `backend/tests/social/test_worker*`, `test_queue*`; local PostgreSQL test harness docs/script if needed | Use frozen table/contract names; no competing domain models or HTTP API; no changes to existing ETL schedulers |
| Admin UI | `frontend/app/admin/social/`; `frontend/components/admin/social/`; `frontend/lib/api/social.ts`; `frontend/lib/hooks/useSocial*`; corresponding tests | Existing admin auth/shell; no new auth; parent integrates nav; no mock production API success |
| Integrator | Router/nav registration, shared integration checks, documentation status, independent review, PRs/issues | Preserve unrelated current work and all declared contracts |

Each agent uses its assigned isolated worktree, commits only its owned files and does not push/create PRs/merge. The integrator combines compatible commits, reviews and tests, then opens PRs. Migrations have one owner. Report discovered blockers before changing an interface.

## Domain/serialization contract v1

All timestamps are UTC ISO 8601 with timezone. IDs are UUID strings, external IDs opaque strings. Versions are positive integers, booleans are not accepted as integers. JSON inputs reject unknown fields. `origin_type` is server assigned `manual` for external create commands. Generated creation stays internal-only for a later phase.

Platforms: `facebook | instagram | threads | x | tiktok`.

Editorial states: `draft | pending_review | approved | rejected | archived`.

Target states: `ready | queued | claimed | dispatching | processing | retry_wait | reconciling | blocked | published | failed | outcome_unknown | cancelled`.

Formats: `text | image | carousel | video | reel` (supported subset depends on effective account capabilities).

Document:

```json
{
  "schema_version": 1,
  "master": {"text": "Example text", "link": null, "hashtags": [], "media": []},
  "targets": [
    {"account_id": "UUID", "format": "text", "overrides": {}}
  ]
}
```

Media references: `{ "asset_id": "UUID", "alt_text": "optional", "caption_asset_id": null }`. Server resolves checksum/type/dimensions from a ready immutable asset; browser values never certify readiness. No base64, file bytes or secret URLs in documents.

Overrides are sparse per-field objects: `text`, `link`, `hashtags`, `media`, each `{ "mode": "replace", "value": ... }`. Absence means inherit. Remove a key to reset to master. Intentional empty string/list and null link differ from inheritance. Unsupported null text/media are invalid. Selection and overrides belong to the immutable revision. No accounts is allowed in a draft; publication requires at least one distinct valid account. Selecting a platform is selection of a connected account, not a handle supplied by the browser.

`ResolvedPostPayload` freezes schema version, account/platform/API product, format, text/link/hashtags, inspected ordered assets/checksums, accessibility metadata and canonical content hash. Payload canonicalization is deterministic, rejects NaN/Infinity and incorporates exact selected content/media and account identity. It does not include changing worker state or signed URLs.

Create request: `{ "title": "...", "content_type": "announcement", "document": {...}, "references": [] }`. Reference objects: `{ "url": "https://...", "label": "optional" }`. Absolute HTTPS references only; no arbitrary fetch of reference URLs during validation.

Patch request: same editable fields plus required `expected_version`. New revision, optimistic version check, immutable old revision. Reject content editing after any publication-capable dispatch starts. Approved unsent edits revoke old authorization/targets and return to draft.

Detail DTO:

```text
id, title, content_type, origin_type, editorial_state, delivery_status,
version, revision_id, document, references, created_at, updated_at,
publication (null or id/revision_id/scheduled_for/version/approved_at),
targets [{id,account_id,platform,state,remote_url,safe_error_message,next_action_at,published_at}]
```

List: `{ "posts": [compact summary DTO], "total": n, "page": 1, "page_size": 20, "has_more": false }`. Summary contains id/title/content_type/origin/editorial/delivery/version/revision/timestamps and compact targets, **not document/evidence/attempt bodies**.

Account DTO: `{id,platform,display_name,handle,profile_url,connection_state,publishing_enabled,capabilities}`. No token/ciphertext/credential bundle. Capabilities have rule version, eligible status, supported formats and explicit known limits/feature states; unknown facts do not become permissive defaults.

Validation DTO: `{ "valid": bool, "rules_version": "social-v1", "targets": [{"account_id": "UUID", "platform": "...", "valid": bool, "errors": [], "warnings": [], "resolved_preview": {...}}], "errors": [], "warnings": [] }`. Each issue: `{ "code": "...", "field": "...", "message": "..." }`. Zero targets is invalid for publication. UI hints are provisional; backend validation is authoritative.

## Batch 1 API surface

Base `/api/v1/admin/social`. Existing `require_admin` identities/roles, UUID actor IDs. Sync routes for synchronous SQLAlchemy. All responses, including authorization/validation/server errors, get `Cache-Control: private, no-store`.

| Method/path | Request | Result |
|---|---|---|
| GET `/posts` | page/page_size<=100, optional editorial_state | Compact list |
| POST `/posts` | Create + `Idempotency-Key` UUID | 201 detail |
| GET `/posts/{id}` | — | Detail or 404 |
| GET `/posts/{id}/status` | — | Compact summary/target status; no document/evidence/media payload |
| PATCH `/posts/{id}` | Patch + key | Detail/new revision |
| POST `/posts/{id}/validate` | optional expected_version | Validation without state mutation |
| POST `/posts/{id}/submit` | expected_version + key | Pending-review detail |
| POST `/posts/{id}/approve` | expected_version, revision_id, optional attestation + key | Exact-revision authorization/ready targets |
| POST `/posts/{id}/reject` | expected_version, reason + key | Rejected detail |
| POST `/posts/{id}/publish` | expected_version, revision_id, acknowledged_warning_codes, optional attestation + key | 202 publication/target IDs |
| POST `/posts/{id}/schedule` | publish fields + schedule `{local_time,timezone,utc_offset}` + key | 202 publication/target IDs |
| POST `/posts/{id}/cancel` | expected_version + key | Detail and in-flight limitation |
| POST `/posts/{id}/duplicate` | expected_version + key | 201 new manual draft; no authorization/results |
| POST `/targets/{id}/retry` | reason + key | Only known-safe failed destination; no replay of success/unknown |
| GET `/accounts` | — | `{ "accounts": [] }` or actual identities |
| GET `/platforms` | — | `{ "platforms": [capability records] }` |
| GET `/system/status` | — | publishing_enabled, worker health, bounded queue counts; no fabricated healthy worker |
| PATCH `/controls` | expected_version, publishing_enabled, reason + key | Versioned controls; no automatic approval enablement in this batch |

`delivery_status` is derived; it is not an independent contradictory post field. Publication accepts all selected valid accounts atomically or none. Default global pause yields 409 `PUBLISHING_PAUSED`, preserves drafts. Scheduled dispatch only executes if the global/account gate is enabled when due.

During active delivery, the UI polls the compact status endpoint while visible. It fetches full detail initially, on explicit refresh, or once when the revision version changes; repeated status polls do not resend the document/evidence. Read-only provider polling can continue during a publishing pause so accepted remote work can be reconciled. A paused unsent target retains its queue intent with a delayed database due time; resume rechecks authorization and freshness instead of blindly sending an overdue post.

Publication receipts point `status_url` to `/api/v1/admin/social/posts/{id}/status`; this is the compact polling resource, while the post-detail endpoint remains the explicit full-document read.

Errors: `{ "detail": { "code", "message", "field_errors": [], "target_errors": [], "retryable": false, "request_id": "UUID" } }`. Codes include NOT_FOUND, VERSION_CONFLICT, IDEMPOTENCY_CONFLICT, TARGET_VALIDATION_FAILED, PUBLISHING_PAUSED, RECONCILIATION_REQUIRED, INVALID_SCHEDULE_TIME, ACCOUNT_UNAVAILABLE, ADAPTER_NOT_AVAILABLE, SOCIAL_SCHEMA_UNAVAILABLE. Unexpected DB failure is 503/500 with safe actionable error, never an empty successful list.

Command receipt, mutation, revision/publication/targets and audit record commit atomically. Same actor/route/key and body returns original resource IDs; changed body conflicts. Domain uniqueness prevents repeated publication even with a new HTTP key. Use one active publication/post and one publication/revision. Financial review attestation required for generated/sensitive categories, not every manual ordinary announcement. Initial external create cannot set generated origin.

## Worker integration

Follow blueprint tables/columns, FK/check invariants, UTC DB clock, `SKIP LOCKED` minimal-ID claim, lease token/epoch, dispatch permits and consistent controls/account/publication/target lock order. Account admission is persisted. No SQL locks while awaiting HTTP. Store operation intent before a publication-capable call. Unknown acceptance is reconciling/outcome_unknown, never a transport-only retry decision.

Worker can use SQLAlchemy Core SQL against the frozen table names until ORM code lands. It must consume the domain contract types instead of defining duplicate payload/result models. Adapter operation/result protocol follows blueprint section 10. If that contract needs refinement, coordinate before committing it.

One worker, two external slots, one mutating operation/account, two DB connections, no overflow. Active scan 5s/idle30s, heartbeat active15s/idle60s, lease120s renewed20s. Five max submissions, bounded24h retry lifetime, content-validity and late-start deadlines authoritative. Status polls do not count as another public submission. Empty queues, expired leases and malformed checkpoints must be executed in tests.

No operational data is seeded automatically. Tests explicitly insert fake accounts/assets/controls. CLI runtime has no real provider adapters in batch1, reports that truthfully, and must not mark a target published without a positive adapter result/receipt.

Adapter execution is stateless: `execute(payload, operation, credential, media_access)` receives the immutable resolved payload explicitly. A mutating permit rehashes and binds the revision/evidence, selected account and exact resolved target content; a target's self-consistent hash alone is insufficient. One unresolved mutating intent per lease prevents a second permit before completion.

Reconciliation never interprets a nonempty evidence dictionary as proof of absence. `DefinitiveAbsenceProof` requires `kind=provider_definitive_status|confirmed_not_sent`, strict `verified=true`, strict `coverage_complete=true`, the exact account UUID and the original mutating operation UUID. A missing, contradictory, incomplete or differently bound proof leaves the outcome unknown and the account held. Generic evidence is audit context only. Published proof requires a nonblank remote identity and confirmation kind, public visibility and a confirmed-success result.

Claim-only audit records avoid backward foreign-key locks on accounts/posts: they retain the already-locked target reference and place account/publication identities in compact event details. Other mutation audits retain ordinary foreign keys after the controls/account/publication/target locks. Lease and claim audit still commit atomically.

## Logging and verification

Use structured, safely serialized event logging with request/post/publication/target/account/operation/worker IDs, lease epoch, attempt, duration, result and stable error type/code. Never log content bodies, raw responses, media fetch URLs, authorization headers, credential material or connection strings. Each mutation and attempt has transactional audit history in addition to logs. Unknown or missing worker heartbeat is unavailable/stale, not healthy.

Run meaningful unit/API tests, PostgreSQL concurrency/restart/crash tests and frontend interaction tests with fake adapters. No normal test needs a live social account or production database. Explicitly restrict integration DSNs to an isolated local test target. Do not print secrets. The integrator independently attacks malformed values, empty target selection, stale versions, pauses, ambiguous sends and partial failures before PR creation.

UI retains forest/cream/gold and the approved queue/editor/preview direction. Preserve existing shell/auth. Responsive composer includes master text, account chips, sparse overrides, limits/issues, preview tabs, Save Draft, Publish/Schedule controls and independent results. No automatic truncation or silent removal of invalid destinations. Backend rejection shows actionable errors; the user can explicitly remove an invalid target. Unavailable media/accounts features must be visible as unavailable, not simulated successes.

## Done and next batch

This batch is complete when code is reviewed/tested and PRs are open for owner review. No merge before the user's review checkpoint. Next priorities: production egress remediation/hosting gate, actual safe media uploads, Meta OAuth/account discovery and Facebook/Instagram adapters, review/scheduling refinements, Threads, explicitly budgeted X, eligible TikTok, generated drafts, then shadow-mode automation. Close tracking issues after accepted implementations merge, not when a branch merely exists.
