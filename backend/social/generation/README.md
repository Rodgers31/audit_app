# Generated drafts and shadow decisions

This package creates factual drafts and advisory decisions. It never authorizes,
schedules or publishes. Existing database constraints continue to require human
authorization and keep legacy generation/automatic approval/scheduling/publishing
flags false. Separate draft/shadow controls default false and require an audited
administrator command. No startup scan, cron, new worker, AI service or backfill runs.
An optional existing-ETL post-commit hook additionally requires the exact
SOCIAL_GENERATION_HOOK_ENABLED=true environment ceiling (default false).

## Evidence boundary

`SourceObservation` and `FactEvidence` in `contracts.py` define the v1 internal
post-commit seam. Values are exact decimal strings with explicit unit/scale,
classification, metric/entity/period/comparison basis, source document and page,
checksum, publisher publication date, retrieval/verification times, canonical
AuditGava URL and ingestion identity. Invalid, fixture, quarantined, failed,
uncommitted or nonpublishable observations are refused.

`POST /api/v1/admin/social/generation/detect` accepts at most25 county-budget
record IDs and one completed ingestion ID; it accepts no fact payload. It calls
`seeding.source_observations.read_county_budget_observation` in fresh committed
readers, then atomically creates source cursor/event/draft/revision/audit/receipt.
The adapter and existing CLI post-commit persisted-lineage selector are delivered
by the B15 ETL lane and are integration dependencies. The selector accepts no
more than1000 exact row IDs, refuses overflow, and calls integration.py after a
successful live non-dry commit. Each event/draft commits separately; partial
progress and source refusals are explicit. A30s monotonic budget and transaction-
local statement/lock limits preserve stricter inherited bounds; the native caller
also uses its existing main-thread timeout. A precommit expiry rolls the current
event back; a late confirmed commit retains its count and returns failed. Pipeline audit actors are distinct
from administrators. Hook failure never relabels committed facts as rolled back.
Without it the route explicitly returns `SOURCE_ADAPTER_UNAVAILABLE`.
Only verified actual CoB expenditure currently has a reviewed adapter. Other
source names in the typed seam are future integration capabilities, not proof of
working parsers/evidence. Missing publisher dates or qualification remains a
refusal; this package does not promote source records or invent dates.

The request's read-only receipt lookup releases its connection before borrowing
a fresh reader, preventing pool starvation. A confirmed receipt replays without
re-reading a source that may since have become unavailable. The mutation command
still serializes concurrent keys and atomically persists its receipt.

## Semantics and corrections

Detector version1 owns `(source_type, source_key, detector_version)` cursors.
The first observation establishes a baseline, producing no historic flood.
An explicit reasoned backfill may create the first event even after baseline.
Unchanged semantic evidence produces no draft. Changed evidence requires a newer
explicit evidence version; ingestion/retrieval/verification changes alone are not
semantic changes. A→B→A produces two sequential events. One event can own one
post, protected by PostgreSQL uniqueness and cursor-row locks.

Factual-v1 templates only interpolate validated supplied facts. Generated drafts
start pending_review and use the same immutable revision/approval/queue pipeline
as manual posts. Edits preserve the immutable evidence snapshot and template
identity. Placeholder checks cover master copy, destination overrides and evidence.
Human attestation remains required; exact revision hashes are enforced.

A newer event serializes against approval/dispatch using the existing global
SocialControls lock before source cursor locks. It requests cancellation of the
superseded publication through SocialService.cancel before committing the new
source event. Unsent targets stop; worker-owned/attempted targets keep their
leases/history and use existing acknowledgement/reconciliation semantics. An
operation already past its durable public permit may complete. No ownership is
force-cleared, and no worker role/read grants are expanded.

## Shadow policy

Rules are immutable append-only versions with disabled/shadow modes only. Only
neutral dataset/report categories are allowlist candidates. Account/source
allowlists, freshness, exact template/evidence/hash checks, no corrections,
platform validation and budget/access gates are evaluated centrally. X/TikTok
remain advisory-blocked pending their separate access/budget contracts.
Cadence is bounded to1–3 suggestions/account/rolling24h and60–1440min spacing.
History scans are capped; excess volume requires human review.

A shadow decision records exact revision/content/rule hashes and reasons. Current
source/freshness/control state is checked before returning a matching historical
context. Changed state creates another immutable context/decision; identical
contexts deduplicate. Cadence counts distinct other revisions, avoiding duplicate
reservations or self-blocking. All decisions remain advisory and require human
approval, including would_allow results. No live authorization path is present.

The admin Automation page exposes controls, bounded detection, immutable rule
versions and paginated history. Generated composer evidence loads separately;
post lists filter by origin/category without fetching full facts. New routes are
authenticated and private/no-store, with existing command receipts and safe errors.

## Local proof and remaining gates

Tests: test_generation.py, test_generation_api.py, test_generation_postgres.py;
frontend social-generation.test.tsx and browser-fixtures/generation/verify.mjs.
The PostgreSQL suite requires its assigned loopback b15_generation_test database
on55400 with the entire Alembic chain through a704b15a0001. It refuses redirects,
other databases/ports and missing schema. Chrome fixtures use33506 and inert auth
and HTTP data; they are not live provider acceptance.

Migration a704b15a0001 is additive from frozen main a545b14a0001. The coordinator
must serialize batch predecessor links and replay the final chain. No migration,
flags, grants or operational settings have been applied to production.

Remaining original rollout requirements: integrate the ETL lane
post-commit caller and source adapter before accepting automatic draft invocation; reviewed
evidence adapters for other source/measure classes; publisher-date/qualification
coverage in real records; accepted shadow-versus-human operating outcomes; narrow
live automation rollout and all production/provider/storage acceptance. Those
external/live stages remain off, and historical fixtures do not prove them.
