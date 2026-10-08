# Batch 3: queue management, media maintenance and native Meta adapters

Authorized 2026-10-08 (America/Chicago), continuing the reviewed development
process. Base: `e9da7c7e7149bddb54eb917cd391f4b67ccd827d`. Original social
PRs #485/#486/#487/#489/#492 and subsequent #495/#505 are accepted prerequisites.
The engineering blueprint and accepted batch invariants remain authoritative.

## Ownership

Three GPT-6.1 Sol/xhigh subagents implement separate scopes in managed worktrees:

| Scope | Worktree | Branch |
|---|---|---|
| #484 schedules/queue | social-schedules-batch3 | codex/social-schedule-management |
| #490 media maintenance | social-maintenance-batch3 | codex/social-media-maintenance |
| #491 native adapters | social-adapters-batch3 | codex/social-native-meta-adapters |

Paths are under `/Users/roger/.codex/worktrees/<name>/audit_app`. Root integrates
in `social-batch3-integration`, owns shared worker/material/reference boundaries,
Alembic ordering and independent combined verification. Agents commit scoped
changes only; root creates reviewable PRs after verification. No agent push,
merge, unrelated checkout edit, dependency installation or other-chat dispatch.

The dirty primary checkout and the active public-data/egress review remain
untouched. Existing approved admin styling and components are retained; no paid
design generation or scheduling service is introduced.

## Queue and schedule contract

- `GET /posts` adds `delivery_filter=all|scheduled|history|needs_attention`,
  default `all`, alongside existing editorial state/page/page size. Filtering
  precedes count/order/offset in SQL. `total` is the exact matching post count;
  no extra count map is required. Capture one database time per request.
- Scheduled membership requires a future-due ready/queued unsent target in an
  active noncancelled publication. History includes published/failed/cancelled/
  outcome_unknown targets. Attention includes failed/blocked/reconciling/
  outcome_unknown. Mixed posts may belong to several views. Lists remain compact:
  no document, evidence, payload, checkpoint, attempt receipt or credential reads.
- Summary/detail/status share nullable compact publication metadata: identity,
  revision/version, approval time/admin, UTC due time, timezone/requested local
  time and cancellation time. Independent target receipt times/links remain.
- History and attention membership span prior revoked authorizations. Current
  `publication` and `targets` retain only the current authorization binding.
  Separate `historical_targets` carry their publication/revision IDs, with at
  most 20 receipts per preview and exact `historical_target_count`.
  `GET /posts/{id}/history` pages compact receipts in batches of at most 20;
  no revision document, payload, checkpoint or grant is loaded. Both post and
  history pages require integers in 1..2,147,483,647. Reject civil times that
  cannot represent the full 24-hour retry window before changing anything.
- Existing-authorization `reschedule` and `publish-now` commands require strict
  post/publication expected versions, publication identity, reason, idempotency;
  reschedule also uses existing strict `ScheduleTime`. Approved revision, hash,
  selected identities and frozen target payloads never change.
- Only never-attempted ready/queued targets with empty remote/checkpoint state
  and no claim/lease can move. Any current claim conflicts. Completed, attempted,
  failed or uncertain targets remain unchanged. There must be an eligible target.
  Revalidate publishing/account/capability gates for eligible accounts while
  verifying the entire frozen authorization identity/hash.
- An already-expired authorization cannot be reopened. Recompute due-relative
  start/retry deadlines only within original content validity; content validity
  is never extended. Existing cancel preserves claims/in-flight or attempted
  work until the worker acknowledges cancellation, and reports retained IDs.
- Lock order remains controls, sorted accounts, publication, sorted targets,
  post. Actions and worker admission recheck under these locks. PostgreSQL race
  tests cover both claim/action orderings and durable intent before cancellation.

## Media maintenance contract

Add durable upload fields: `grant_renewal_deadline`, `grant_epoch`,
`grant_expires_at`, `grant_settled_epoch`, `write_quiescence_receipt_hash`, and
`pending_released`. Grant counters are nonnegative and settled epoch cannot
exceed issued epoch; pending release is an explicit once-only ledger marker.
Root owns the conservative legacy backfill and database constraints.

- Grant renewal ends after the original upload TTL window. Replay never extends
  that window. Existing orphan `expires_at` retains its separate meaning.
- Commit an uncertain grant epoch before signing. `SignedAccess` carries the
  signature's authoritative expiration; persist it after fencing before returning
  a URL. Missing expiration during signing is uncertainty, never cleanup proof.
- Clock expiry, positive HEAD, DELETE, DB lease expiry and a matching final
  object alone cannot prove all outstanding browser/server writes stopped.
  Unknown browser/finalization writes retain pending and both-copy quota.
- An injected `WriteQuiescenceVerifier` accepts an internal receipt and returns
  affirmative evidence bound to asset/provider/bucket/grant and finalization
  epochs. Default runtime verification is unsupported. An untrusted browser
  Boolean or arbitrary object metadata is not settlement evidence.
- Reconciliation freezes renewal, verifies outside SQL locks, then rechecks
  version/epochs/state/references under budget→asset locks. Conservative abandon
  recovery archives nonready unreferenced rows. Ready reconciliation may settle
  quarantine hazards, but cannot archive/delete the original. Quota release
  follows confirmed deletes, never reconciliation acknowledgement alone.
- Bounded maintenance reports compact backlog and runs only through an explicit
  separate entrypoint with a supplied DB URL and cleanup opt-in. No API lifespan
  scheduler, implicit provider, production DSN or enabled recurring job.
- Cleanup filters unsettled writes/live leases before LIMIT and rechecks after
  locking. R2 delete acknowledgement must be an actual successful response with
  SDK wire retries disabled. Failures remain reserved and visible.
- Root changes revision reference insertion to lock sorted asset IDs and require
  ready/nondeleted originals in the same transaction. Maintenance checks all
  historical references under the same asset lock. Original retention/deletion
  remains deferred in this batch; no referenced original is deleted.

## Native publishing and material contract

Exact account products are `facebook_pages` and
`instagram_graph_facebook_login`. Native modules are explicitly constructed and
injected; no fake or real adapter is registered by default.

Root provides `backend/social/worker/materials.py`:

- `WorkerCredentialMaterial`: account/credential IDs and credential version,
  platform/product/external identity, Page ID, scopes and access/data expiry;
  Page access token is repr-hidden. Loading verifies current account admission,
  credential identity/version/revocation, related refresh state and material
  purpose. No credentials enter persistent DTOs/checkpoints/logs.
- `ProviderFetchURL`: repr-hidden URL, expires-at, asset ID and checksum.
- `InspectedMediaAccess`: async `read_bytes(asset, maximum_bytes)` and
  `provider_fetch_url(asset, minimum_ttl_seconds)`. Root validates the exact
  ready final object's immutable size/type/checksum/dimensions, bounded bytes
  and storage snapshot; fresh scoped access is minted at use, never persisted.
- Adapter `reconcile` receives credential/media access alongside payload,
  checkpoint and original attempt, just as execute does. Root updates the
  worker protocol/caller and explicit test fakes together.

Facebook supports text and one inspected static JPEG/PNG; Instagram supports
one inspected JPEG. Other formats/caption assets are explicitly unsupported.
Endpoint-specific official evidence pins version/scopes/limits; stricter app
ceilings are identified as app policy. Runtime eligibility remains gated.

Provider-verified connection selection/reconnection must persist the native
capability snapshot. Registry presence cannot upgrade a legacy snapshot or
relax recorded eligibility, publishing, cost, scopes, formats or limits. Changed
admission fields require verification before approval and dispatch. The account
list reads only compact capability metadata; credential bundles remain private.

All mutating upload/container/publish operations require reconciliation after
an uncertain outcome. Persist provider IDs before the next step. Polling and
reconciliation are bounded reads within existing budgets/deadlines. Success
requires exact ownership/publication evidence and a real remote identity/link.
A returned ID alone, a FINISHED container, an empty/ranked list scan or timeout
never proves publication or definitive absence. A PUBLISHED IG container without
a retained final media identity remains uncertain; it cannot be resent.

## Verification and operational boundaries

Require observed regressions, positive baselines, hostile input/response cases,
actual isolated PostgreSQL lock/claim tests, fake HTTP/storage restart/recovery,
safe logging, strict client decoding, mounted interactions, TypeScript/lint and
responsive fixture checks. Root coordinates PostgreSQL runs; agents do not
truncate shared fixture databases concurrently or start test infrastructure.

No live OAuth/social mutation/storage call, billing/bucket/app provisioning,
production migration, deployment/environment/CI change, existing-process restart
or automatic control enablement is part of this batch. #481/#488/#490 retain
operational acceptance; source-evidence R2 does not establish social signed-PUT
or browser CORS acceptance. Real publishing stays off until those gates pass.

Finish code and evidence before opening scoped PRs. Report unresolved scope as
an explicit issue/gate; never turn missing evidence into a success verdict.
