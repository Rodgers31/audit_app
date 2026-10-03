# Round19 consolidated verification

Four completed sessions are consolidated into backend recovery/refresh/OAG work
and county-tab recovery. GitHub Actions remains disabled. No paid bot review was
requested. No production data, signing secret, service configuration, cache or
scheduled job was changed by this review.

## What was verified

- Recovery acquisition requires a fresh reviewed request, verified TLS, a
  consistent read-only inventory/database snapshot and separately frozen globals.
  Inventory coverage includes supported custom types, extension configuration,
  collations, default privileges and publications. Acquisition never certifies
  itself as a verified backup; actual compatible restore and completeness remain
  separate requirements.
- Cache workers acknowledge a generation only after successful local clearing.
  Signed status exposes observed/adopted generation, worker PID and loaded commit.
  The refresh verifier requires an explicit `--execute`, the complete approved
  worker census and exact frontend path acknowledgement.
- Explicit `--audits-observe-listing` validates fresh publisher listings and
  already adopted editions before the five selected editions can be ingested.
  The ordinary seeding path is unchanged. Partial commits and job side effects
  must still be included in any production recovery plan.
- A rejected county-tab chunk produces a scoped recoverable error. Reloading
  preserves the selected tab, fiscal year, query parameters and anchor on mobile
  and desktop. Existing financial/source notes remain visible after recovery.

## Independently confirmed corrections made during consolidation

1. A coherent publisher listing could omit an entire reviewed year and produce
   an apparent OK result against only 282 coverage cells. Both listing collection
   and receipt consumption now require every reviewed edition. Three regression
   tests failed before the fix and passed afterward; the actual handler refuses
   before selected source writes. Full eight-edition coverage remains376 cells.
   This finding belongs to existing issue #234.
2. Recovery guards accepted missing/duplicate extension configuration relations,
   nonexistent publication columns and invalid default-privilege/catalog
   references. Empty role-dump output could publish an unverified acquisition
   bundle. All 13 independently reproduced false-success outcomes now refuse;
   positive quoted-identifier/system-namespace cases remain supported. These
   findings belong to existing recovery obligations in #231/#319.

## Executed verification and limits

Final focused executions: **334 backend/tool tests and 8 browser tests passed**,
with no failures, skips or retry-derived flaky results. The backend total is
289 isolated cache/OAG tests, 32 backup tests (including real isolated
PostgreSQL 17.11 dump/restore controls) and 13 acquisition tests. The frontend
production build passed lint and type checks; expected API connection failures
during fixture build-time static calls are retained in the log. The 8 browser
checks used a synthetic FastAPI/SQLite source, at 375px and 1280px.

Separate independent controls passed 62 OAG cases and 53 recovery cases. A local
actual FastAPI/typed frontend refresh command passed 11 contract checks; the
frontend cache calls were spies, so this does not certify live ISR. These controls
are not added to the 342 focused-test total. Initial intentional red regressions
and harness collection failures are retained separately from final outcomes.

The compatible Supabase PostgreSQL 17.6 rehearsal evidence is inherited from the
recovery session, not a fresh production restore. The sampled transport abort is
not a hard provider-accounting ceiling: the final local small-threshold control
overshot by 4,766,801 bytes. Actual production acquisition remains unobtained;
`backup_verified=false` and `hard_provider_ceiling=false` remain truthful.

The coordinator evidence bank uses immutable `ROUND19_ROOT_*` logs/receipts and
records actual shipping source hashes. Author receipts and readiness markers
precede the coordinator fixes and cannot approve the changed helper hashes.
Any operational request must be regenerated against final merged sources.

## Shipping and recovery

No production configuration is enabled by these commits. The acquisition and
refresh commands refuse without their explicit execution arguments; signed
endpoints refuse without valid credentials. Deliberate live adoption follows
the exact operation documents below, including freeze, recovery and readback.
First acceptance requires loaded commit/path/PID, every worker's adoption, exact
frontend acknowledgement, then changed source/API/rendered values with fixed
serving processes. Refuse missing authority, mismatched identity, incomplete
backup scope, failed restore, unknown writers or incomplete acknowledgement.

If the merged code itself must be rolled back, use reviewed revert PRs for the
two Round19 squash commits, frontend first and backend second. A code revert
does not undo later database changes: those require the separately reviewed
source-bound inverse/recovery plan. Do not start live acquisition or ingestion
to test a rollback.

- [Recovery operation and unresolved prerequisites](../operations/2026-10-02-round19-production-recovery.md)
- [Runtime and refresh adoption](../operations/2026-10-02-round19-runtime-adoption.md)
- [Qualified OAG observation](../operations/2026-10-02-round19-qualified-oag-observation.md)
- [County-tab recovery and unresolved stall](2026-10-02-round19-county-tab-recovery.md)

## Issue closure accounting

**No entire existing issue is closed by this round.** Engineering progress is
not production correction, human review or a demonstrated causal fix. All 15
existing open issues retain these specific acceptance requirements:

| Issues | Remaining requirement |
| --- | --- |
| #273 | Correct stored/public Treasury publisher attribution; preserve loan relationships. |
| #379 | Apply and publish the reviewed three stored OAG text-boundary corrections. |
| #234 | Actually adopt five selected volumes, validate all 376 cells, refresh and verify publication. |
| #231/#319 | Verified production backup/restore, runtime adoption, exact stored corrections, safe fixture cleanup and source/API/browser acceptance. |
| #450 | Diagnose and fix the separate intermittent resolved-module/no-request stall. Rejected-chunk recovery alone is insufficient. |
| #298/#299 | Authoritative disputed tax-head/county-cash sources and actual publication acceptance. |
| #137/#230/#347 | Remaining provenance/source decisions, cleanup/publication and actual pipeline recovery evidence. |
| #307/#372 | Competent Swahili meaning/fluency review; include the two new county error/reload keys. |
| #291/#343 | Final authorized hosted browser/coverage acceptance. Actions stays off until explicitly approved. |

Next priority is an actual coordinated production correction/acceptance release,
starting with verified recovery and runtime prerequisites. Independent work can
continue on the reproducible tab stall and source/human-review decisions. The
release's dependent data writes must be serialized; adding concurrent writers
does not help close these tickets safely.
