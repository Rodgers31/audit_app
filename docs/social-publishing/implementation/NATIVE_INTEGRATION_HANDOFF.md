# Native publishing integration handoff

2026-10-08. Coding scope: issue #491. Facebook Page text/single static JPEG or
PNG, and Instagram Facebook Login single static JPEG. Native endpoint evidence,
limits, recovery rules and remaining format/permission questions are recorded
in `backend/social/adapters/README.md`.

## Runtime assembly and admission

`create_native_registration` requires explicit verified application gates,
server application secret, async transport factory, engine, credential cipher
and private R2 storage/origin. Disabled configuration returns an empty registry.
There is no environment-driven enablement or real-transport fallback. A ready
factory rejects missing dependencies and blank/non-ASCII application material.

The API accepts an optional server-injected
`app.state.social_native_registration`. The worker receives the same registry's
`adapters`, `credential_loader` and `media_access` through its existing explicit
constructor. The caller owns closing both worker and registration. Default API
and CLI assembly continue to have no native adapters; deployment/lifespan
configuration is a later operational step.

Provider-verified connection selection/reconnection persists the native
capability snapshot. Approval requires the stored eligibility, version, rules,
formats, scopes and limits to match current native admission, with supported
publishing and free price class. Legacy unavailable snapshots require a verified
reconnect. Reads never upgrade stored capabilities or clear restrictions. The
account projection includes only compact metadata, without credential bundles.

## Ephemeral material and recovery

After a durable intent commits, credential loading rechecks claim token/epoch,
target/publication/account binding, approved payload hash, intent identity,
account admission, credential ID/version, revocation, expiry and parent refresh
state under the established lock order. The short transaction closes before
provider calls. Malformed material produces sanitized local error codes.
Reconciliation also obtains fresh material under its new read-only intent.

Media access is scoped to the frozen payload. It verifies the ready/nondeleted
original's immutable identity and storage snapshot, reads bounded bytes into a
private temporary directory, and checks byte count/checksum plus HEAD before
and after access. Fresh GET URLs bind the exact origin, bucket, key, version,
signature expiry, asset and checksum. Tokens and fetch URLs remain ephemeral;
adapter checkpoints and browser receipts contain neither.

Real PostgreSQL worker fixtures reconstruct registration at each native step,
exercise successful Facebook text/image and Instagram JPEG publication, and
retain uncertain accepted mutations after lost responses or database receipts.
A separate random-schema proof rotates credentials after intent commit: HTTP
is blocked, the durable intent remains, and recovery receives the new credential
version through a read-only intent without a resend.

## Review and validation

Independent review observed and repaired malformed material, foreign object
versions, missing runtime dependencies, the compact account projection and
persisted capability restrictions being relaxed by registry presence. Each
retained negative fixture has a working positive baseline. Final independent
SQLite/fake-provider review passed 240 tests, with its PostgreSQL case explicitly
excluded because root owns that lane. Root executed the actual PostgreSQL cases.
The separated native branch, including its media prerequisite and all four
explicit local PostgreSQL lanes, passed **1,016 backend tests with zero skips**.

The native PR is stacked on `codex/social-media-maintenance`: material access
depends on its authoritative signed-expiry contract. Queue UI remains a separate
PR. After the media prerequisite merges, retarget/recheck the native PR against
main before merge. No branch is merged by this batch.

## Remaining operational work

Live publishing remains off. #481 hosting/egress, #488 Meta app/account
authorization and #490 private storage/CORS/write-quiescence acceptance remain
open. Fake transports and local PostgreSQL prove code behavior; they do not prove
real endpoint permissions, media color-space/JPEG subtype acceptance, provider
fetch reachability or public readback. The production write-quiescence verifier
is still unsupported, and ready-original deletion remains deferred.
