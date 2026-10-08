# Queue filters and schedule management (#484)

Base: `e9da7c7e7149bddb54eb917cd391f4b67ccd827d`. This work follows the frozen
batch 3 queue/schedule contract and preserves the approved admin styling.

## Behavior and API

`GET /api/v1/admin/social/posts` now accepts
`delivery_filter=all|scheduled|history|needs_attention`, alongside the existing
editorial filter and bounded pagination. SQL membership precedes count, ordering
and offset. A single CTE statement returns both the exact filtered total and
page, including an empty late page; one database clock value determines future
membership throughout the response. Separate bounded publication/target
projections exclude documents, evidence, frozen payloads, checkpoints, attempt
receipts and credentials.

- Scheduled: active noncancelled authorization with a future-due ready/queued
  target whose submit count is zero.
- History: any published, failed, cancelled or outcome-unknown target.
- Attention: any failed, blocked, reconciling or outcome-unknown target.

Mixed posts can belong to several views. These are post counts, rather than
summed destination counts. Queue cards show account names/identities, the creator
and reviewer, requested local time/timezone, exact UTC due time and independent
confirmed target timestamps. History provides verified HTTPS publication links.
History selection uses compact receipts without loading the draft document.
Other views load the document only for the selected post.

Summary, detail and compact status share nullable `publication` metadata:
`id`, `revision_id`, `version`, `approved_at`, `approved_by`, `scheduled_for`,
`schedule_timezone`, `requested_local_time`, `cancel_requested_at`. Nullable
`created_by` remains separate from the approval admin. The strict client expects
these serialized fields, so API and client changes should ship together.

Historical visibility includes targets belonging to revoked authorizations. The
current `publication` and `targets` retain their current authorization binding;
old approvals never bind a new draft. Summary/detail/status additionally return
`historical_targets` (at most 20) and exact `historical_target_count`. These
receipts include published/failed/cancelled/outcome_unknown/blocked/reconciling
states. Each retains the compact delivery fields plus its own `publication_id`,
`revision_id`, `approved_at`, `approved_by`, `scheduled_for`,
`cancel_requested_at`, `revoked_at` and `updated_at`.

`GET /posts/{id}/history?page=1&page_size=20` returns
`{post_id,targets,total,page,page_size,has_more}`. The maximum page size is 20;
the window preview and endpoint use the same deterministic updated-time/ID
order. Window counting bounds previews in SQL and provides an exact count;
endpoint count/page share one SQL snapshot, including empty late pages. Neither
loads documents, evidence, payloads, checkpoints, attempt receipts or grants.
The readonly history section uses existing styling, preserves each receipt's
dates and safe links, and fetches further pages only when explicitly inspected.
History cache keys include actor/post/page; relevant commands invalidate them.

Post/history service pagination requires exact integer values and rejects
Boolean/floating values. Pages are bounded to 2,147,483,647 before SQL. HTTP
queries share the upper bound. Schedule validation rejects civil times that
cannot represent the existing 24-hour retry window, so malformed extremes return
atomic client errors instead of database/arithmetic failures.

`POST /posts/{id}/reschedule` returns PostDetail with HTTP 200;
`POST /posts/{id}/publish-now` returns PostDetail with HTTP 202. Both require the
existing UUID Idempotency-Key header plus:

```json
{
  "expected_version": 2,
  "publication_id": "<selected-publication-uuid>",
  "expected_publication_version": 2,
  "reason": "Move the unchanged reviewed announcement",
  "acknowledged_warning_codes": []
}
```

Reschedule additionally requires the existing `schedule` civil time, IANA zone
and explicit offset structure. Optional warning acknowledgments preserve the
fresh eligible-only validation warning gate. The interface presents returned
warnings for explicit acknowledgment. Version/identity/reason fields reject
malformed, Boolean and nonpositive versions through strict request schemas.

## Durable state and concurrency

Both actions lock controls, sorted accounts, publication, sorted targets and
post, then recheck current state. Any retained claim/lease conflicts. Eligible
targets are ready/queued, never attempted, submit-count zero and have empty
checkpoint/remote state. Successful, failed, attempted and uncertain targets
retain their independent records. At least one eligible target is required.

The entire immutable revision/authorization hash, selected account set and each
frozen target payload hash are verified. Current publishing/platform/account,
capability, media and warning gates apply only to eligible destinations, so a
previously successful account's later disconnect does not block another
untouched destination. No authorization, revision, payload, successful target,
operation intent or ambiguous target is rewritten.

Already-expired start/retry/content validity cannot be reopened. Due-relative
start/retry deadlines can move but are capped at the original content validity;
that validity never changes. Claims are never cleared by schedule management.

Cancellation records the existing publication stop intent, keeps worker-owned,
attempted and unresolved remote/checkpoint work, and reports retained IDs using
the compatible `in_flight_target_ids` field. Worker admission acknowledges a
claim with no operation intent before resume can reopen it. A durable in-flight
operation remains able to report its actual remote result. The inherited resume
race fixture now requires that acknowledgment before proving old-token fencing.

No migration, worker implementation, connection/runtime registration or media
reference-lock change is included here; those shared boundaries belong to the
integrator. No live provider, OAuth, storage, billing, deployment, process restart,
package installation or external publication was performed.

## Executed verification

The new API/domain suite failed **23 assertions** against the unchanged baseline
social modules, then passed with the implementation. The original mounted UI
fixtures failed **4 assertions** on missing filters/controls before implementation.
The actual PostgreSQL race suite failed **3 tests** with **1 positive baseline**,
then passed all **4 tests** using the foundation Alembic migration in disposable
random schemas on the assigned loopback `social_domain_test` database. No shared
worker table was truncated.

The PostgreSQL fixtures force both orderings using gated SQL cursor events:
claim update holds its target while a schedule edit waits, then the edit rejects
without changing token/epoch; a schedule edit holds its target while SKIP LOCKED
claims nothing, then the committed future due remains unclaimable. Additional
fixtures retain a claim until cancellation acknowledgment and retain a durable
intent through cancellation until confirmed success arrives.

The global fixtures cover multiple filtered pages, unrelated newer drafts,
mixed membership, attention/failure states, cancelled schedule exclusion, exact
count/page equivalence, empty late pages, compact projections, idempotent replay,
post/publication conflicts, current gates, immutable payloads and original
content-validity deadline caps. Mounted UI/parser fixtures cover global server
query parameters, exact guarded bodies, DST gaps/overlaps, wrong authorization
receipts, retained idempotent intent, successful/unsent independence, safe history
links, claim controls and strict schedule response shapes.

Final checks after the historical-delivery review fix: **684 backend social tests
passed, 71 skipped** with the explicit domain PostgreSQL lane; **474 frontend
social/connections tests passed**;
whole-frontend TypeScript and owned code/test lint passed. The skips are the
unassigned worker/connection/integration database lanes and optional platform
fixtures; the integrator owns the combined lanes. Existing SQLAlchemy and
Next lint deprecation notices remain.

The actual component export and Playwright fixture harness passed at 1440, 768,
390 and 320px: no horizontal overflow, no unlabelled fields, and no visible
button below the accepted 44px size. The mobile rendering was visually inspected.
Every external browser request was blocked. This verifies static responsive
fixtures and mounted interactions, not live auth/provider behavior or production
hydration.

The historical-delivery follow-up observed three backend failures before the
fix, eleven pagination-boundary failures and twelve mounted/parser failures.
All now pass. Three additional actual PostgreSQL fixtures verify revoked
history, separation from a replacement authorization, and 25 receipts paginated
20/5/0 with exact counts. The four original claim/action race fixtures still
pass. The expanded responsive export verifies both schedule and historical
receipt states at all four widths, and its mobile rendering was inspected.

Reproduce from this worktree with the integrator's explicitly assigned,
loopback-only `SOCIAL_TEST_DATABASE_URL` (the shared validator rejects remote
or libpq query overrides). Use an existing configured Python environment with
the repository's backend dependencies; these commands do not install packages.
From the repository root:

```sh
PYTHONPATH=backend PYTHON_DOTENV_DISABLED=1 python -m pytest backend/tests/social --confcutdir=backend/tests/social -q --tb=short
cd frontend
npm test -- --runInBand __tests__/admin/social __tests__/social-connections
./node_modules/.bin/tsc --noEmit --incremental false
SOCIAL_SCHEDULE_VISUAL_DIR=.social-schedule-preview ./node_modules/.bin/jest __tests__/admin/social/schedules.test.tsx __tests__/admin/social/delivery-history.test.tsx __tests__/admin/social/pr514-review.test.tsx --runInBand
./node_modules/.bin/tailwindcss -i app/globals.css -o .social-schedule-preview/global.css
node tests/socialSchedulesVisualCheck.mjs
```

Generated HTML/screenshots/report stay in the worktree's uncommitted
`frontend/.social-schedule-preview/`. Backend/worker/frontend integrations still
require independent integrator review and combined validation. Publishing stays
subject to the existing explicit operational gates.
