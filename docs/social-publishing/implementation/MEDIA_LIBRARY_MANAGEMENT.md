# Media usage and metadata archive (#754)

The media library at `/admin/social/media` lists inspected ready assets and opens
bounded historical revision usage. The composer picker exposes the same detail;
an asset selected in its current unsaved document cannot be archived there.
References include superseded and archived posts. Each entry names its post,
revision number and immutable revision ID; its link opens the post editor.

The authenticated, private/no-store HTTP surface adds:

- `GET /api/v1/admin/social/media/assets/{asset_id}/usage?page=1&page_size=20`
  returns asset/version, up to 50 historical references, total, pagination and
  an advisory archive eligibility/reason. Page is bounded to 1,000,000.
- `POST /api/v1/admin/social/media/assets/{asset_id}/archive` requires the
  existing Idempotency-Key header, strict positive expected_version and a
  nonblank plain-text reason of at most 500 characters.

Archive is a metadata operation and remains available without enabling uploads,
native publishing, storage clients or supervision. It never calls object
storage, grants write-drain/deletion authority, releases a pending slot or
changes reserved-byte accounting. Success sets ready to archived and increments
the existing upload version; objects and history remain retained. It hides the
asset from ready selection, and does not create an automatic unarchive path.

The command uses the existing durable command receipt transaction. It locks the
asset and upload using the same asset lock as revision-reference creation,
rechecks version and all historical references, and refuses dependent child
assets, leases, unsettled browser/server writes, absent existing trusted
quiescence evidence, unsettled owned writers and unfinished privacy retirement.
A timestamp or HEAD is never substituted for that evidence. Missing upload or
object identity refuses. Unknown histories without existing positive settlement
stay protected; this command does not backfill their conditional-write protocol.

State/version, exact audit fields/details and the existing command receipt are
read back before success. A suppressed or altered write rolls back. Concurrent
reference creation either commits its reference and blocks archive, or sees the
archived asset and refuses; both cannot succeed. The frontend preserves the
command key after an ambiguous reply, checks unchanged asset metadata and the
next version, and refuses regressing usage versions across pages. Server checks
remain authoritative when advisory reads become stale.

## Cleanup and rollback

Archived assets with an inspection checksum are excluded from legacy orphan
cleanup both before LIMIT and after acquiring row locks. Operator observations
label them ARCHIVED_ORIGINAL_RETAINED. This deliberately errs toward retaining
ambiguous old archived originals too; it does not infer permission to delete
anything. Explicit separately authorized privacy retirement remains separate.

No migration, grant, new dependency, flag, scheduler or paid resource is added.
Publishing/uploads/native/supervision remain off. Rollback must leave maintenance
and activation off and retain all archive state, audit rows, receipts, objects
and quota. Do not resume a pre-change orphan cleaner against archived inspected
originals; preserve/backport these guards before any later cleanup activation.

## Validation boundaries

New formal SQLite/HTTP tests cover authorization, strict inputs, bounded usage,
historical references, stale versions, same-key replay, no object/accounting
changes and audit rollback. Real migrated PostgreSQL checks cover exact
persistence failures and the reference/archive race. The original cleanup
without both guards was executed against the new archive fixture and deleted
its fake original; the guarded path preserves it. Independent review reproduced
a regressive usage response; its formal failing test now passes.

Both supported Python versions, normal/optimized runs, current PostgreSQL,
frontend tests, TypeScript and a production build were checked. The local build
uses inert/unreachable backend/auth values and is compilation evidence, not data
or production acceptance. Python 3.12 uses cached SQLAlchemy 2.0.54, not a minimum
dependency-floor proof; absent PostgreSQL/FFmpeg prerequisites are explicit skips.
Chrome exercises production components/hooks/parsers with labelled synthetic
assets and inert API responses; it performs no real upload/archive/provider
operation. Real worker/storage/provider activation and lifecycle acceptance stay
in #699/#490/#488.
## Reverse lookup indexes

Migration `a756b20a0001` follows `e621b17a0001` and adds nonunique Btree
indexes on `social_revision_assets(asset_id, revision_id)` and
`social_media_assets(parent_asset_id)`. The existing revision-first primary key
continues to serve revision lookups. Full indexes keep PostgreSQL and SQLite ORM
fixtures aligned; no new partial-index predicate becomes a query requirement.
These paths are shared by library usage/archive, reference refusal, maintenance
candidate selection and reconciliation. They change lookup cost, not eligibility,
locking, object retention, quota or permissions.

Both upgrade and downgrade set PostgreSQL transaction-local `lock_timeout=2s`
and `statement_timeout=30s` before DDL; these settings expire at transaction end.
Apply within a transaction while existing publishing/uploads/native/supervision
switches remain off. Both indexes commit
together; name collisions or lock failures must abort rather than be ignored.
Use the existing Alembic chain, verify both column orders and validity afterward,
and preserve the prior table data, ACL/RLS and trigger contracts. Downgrading to
`e621b17a0001` removes only these two indexes and retains media history; it does
not authorize any older data-destructive downgrade. Index creation uses existing
database storage and build resources; no new service or paid plan is required.

Local populated fixtures measure ordinary PostgreSQL plans after committed DDL
and fresh transactions, with statistics refreshed and no planner-forcing flags.
Those selective-query observations do not establish sustained production capacity.
