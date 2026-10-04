# Batch 2: egress, inspected media and Meta connections

Authorized by the owner after the foundation review on 2026-10-03. This batch implements [#481](https://github.com/Rodgers31/audit_app/issues/481), [#482](https://github.com/Rodgers31/audit_app/issues/482) and [#483](https://github.com/Rodgers31/audit_app/issues/483) in separate isolated worktrees. The foundation contract, engineering blueprint and low-cost profile remain authoritative. All three implementation workstreams use GPT-6.1 Sol with xhigh reasoning.

## Ownership and review sequence

| Workstream | Owned changes | Integration owner |
|---|---|---|
| Egress | Ingestion admin-statistics SQL aggregation; national-budget/revenue source lookup batching; new equivalence/query-volume tests and bounded benchmarks | Agent commits only scoped routers/writers/tests/evidence; no main/cache/fiscal changes |
| Media | New `backend/social/media/`; existing media asset model contract; new upload/library clients/hooks/components/routes; existing SocialMedia/SocialPreview integration and new feature tests | Parent owns shared API/status DTO, requirements, model/route registration and any migration |
| Meta | New `backend/social/connections/` models, OAuth/credential/provider/API services; new account-connection frontend clients/hooks/components/routes/tests | Parent owns migration chain, shared API/model registration, requirements and navigation |

Agents do not push, merge, change another agent's branch, install into shared environments, run production database queries, change account permissions or start existing servers. The integrator independently reviews and tests, then opens scoped PRs. New batch PRs remain for owner review. Existing unrelated issue-review work continues untouched.

No application code is changed in the primary dirty checkout. No agent owns `backend/main.py`, the shared cache layer, current fiscal-summary/source-registry work or public frontend data pages in this batch. If a necessary change crosses those boundaries, report it rather than making a speculative fix.

## Shared invariants

- Supabase remains the database/auth source. No Redis, second database or paid scheduling service.
- Global/automatic publishing stays OFF. Real publishing adapters remain absent. Account connection and media readiness never imply a successful social publication.
- Existing master content, sparse overrides, media references, immutable revisions and resolved payload hashes do not change.
- Media bytes remain in object storage. PostgreSQL holds bounded state and inspected metadata, never base64 or files.
- Access/refresh tokens, encrypted credential bundles and secret URLs never enter permanent browser DTOs, post documents or logs. Temporary scoped upload/preview grants are issued only to authenticated admins for known asset identities.
- Every new endpoint reuses Supabase admin authorization, structured safe errors and private/no-store responses. Mutations have replay/version protection and durable audit records; provider/storage calls do not hold SQL row locks.
- Existing allowlisted social logging is extended narrowly with identity, phase, operation, duration and stable error code. Never log raw exceptions, codes, tokens, provider responses, DSNs or file contents.
- One integrator owns additive Alembic ordering and RLS/browser-role restrictions. New ORM modules reuse the same Base; no competing metadata registries or migration heads.

## Egress acceptance

Preserve financial/null/provenance semantics, metadata relabeling, transaction rollback and publication checks. Replace full job hydration with SQL aggregates and repeated per-record source lookups with transaction-local batched/reused identities. Record before/after selected rows, columns, calls and result-byte estimates on equivalent fixtures. A fixture estimate is not a Supabase billing meter.

Use isolated loopback databases with random schemas. Do not reset production query statistics or dump data. Capture worker empty/busy query shape, cadence and connection bounds without removing final publishing gates. Keep #481 open until its live attribution, representative seven-day budget and reliable worker-hosting capacity gates are established; a verified code reduction is still useful independently.

## Media contract

The feature service proposes explicit upload initiation, completion/inspection, compact paginated library/detail and short-lived preview operations before shared wiring. Client names/types/byte counts are upload intent, never evidence of readiness. Runtime storage and inspector configuration is explicit and unavailable by default when absent or invalid.

Uploads are scoped to one admin-owned quarantine object, fixed limits and expiry. Completion inspects actual bounded bytes/type/dimensions/duration/codec/checksum using maintained local tools. Failed/incomplete uploads remain unusable. Inspection/cleanup ownership is fenced; final ready object identity and inspected properties are immutable. The service must prevent a remaining upload grant from overwriting the finalized object.

Initial storage should favor a single complete optional S3-compatible backend suitable for R2/video egress, reusing existing boto3 where possible. Supabase images are an alternative only after a bounded budget decision. No bucket, billing account, credentials or deployment is provisioned by this code task. File formats/size/duration and dependency/ffprobe availability must be truthful. No arbitrary URL downloads, request-time rendering or unbounded video memory reads.

Library selection preserves media order, alt text and exact per-account override isolation. Temporary preview access is separate from immutable post content. References/approval retention prevent accidental asset deletion. Generated graphics/video and automatic transformations remain deferred.

## Meta connection contract

Choose Facebook Login for Page and linked professional Instagram discovery. Threads remains separate later. Provider transport/app configuration uses an explicit API version and exact HTTPS redirect allowlist. The browser may relay a short-lived authorization code in an authenticated completion command; permanent tokens are exchanged, encrypted and retained only server-side.

OAuth state is unpredictable, expiring, single-use and bound to the verified admin session, provider and exact redirect. An unverified JWT claim cannot establish session binding. Replayed, wrong-session, missing-scope and mismatched-redirect flows fail closed. Discovery is bounded/paginated; an admin explicitly chooses owned eligible assets. Browser consumer-profile linking is not API authorization.

Use established authenticated encryption with versioned key rings; bind the encrypted envelope to credential identity/provider/kind and verify it after decryption. Parent Facebook user grant and derived Page grant remain distinct. Persist actual expiry/scopes/access method, refresh leases/version and revocation. Do not invent a universal Meta refresh token. Reconnection preserves account identity/history; unverified new credentials never overwrite a working grant silently. Rotation and disconnect are audited and gated against active publishing/admission.

Existing Account DTOs contain identity and effective capabilities, never credential material. A separate connection-health DTO may add scope/expiry/last-success information. Without publishing adapters, adapter availability stays false; new accounts remain publishing-disabled until explicit operational approval. Standard/Advanced Access requirements follow current official endpoint documentation and actual owned-account roles, not an arbitrary blanket business-verification gate.

## Operational boundaries and completion

Tests use explicit fake storage/OAuth/Graph providers and local real byte inspection, with hostile input, replay/lease races, output equivalence, redacted logs and UI interactions. No fake provider is auto-enabled in runtime. Existing dependencies may be reused read-only; direct cryptography/Pillow declarations are reviewed by the parent. A missing video inspector is reported, not replaced with browser claims.

Live storage provisioning, actual Meta app permissions/OAuth validation, worker deployment and seven-day egress measurement remain separate operational steps. No paid upgrade, production migration, environment/deployment change, security-setting change, real account connection or social post occurs here. Definition of done is tested reviewable code plus precise deployment/validation gates; it is not a claim that live accounts are already connected.
