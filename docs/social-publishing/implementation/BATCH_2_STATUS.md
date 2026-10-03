# Batch 2 implementation and review ledger

Updated2026-10-03. Read alongside BATCH_2_CONTRACT.md, the engineering blueprint and low-cost profile. This ledger separates merged foundation, reviewable code and operational acceptance; an open PR is not deployment.

## Reviewed foundation accepted

The owner authorized merging after actual-code audit and review fixes. All review findings were checked against code and executed regressions rather than blindly applied. Detailed receipts remain in REVIEW_485_486.md and UI_HANDOFF.md.

- [#485 backend/domain/worker](https://github.com/Rodgers31/audit_app/pull/485) merged as `3cf15b60f00872904ac06e7302606f282e5b66c1`; final196 social tests and34 existing backend regression tests passed.
- [#486 admin composer](https://github.com/Rodgers31/audit_app/pull/486) merged as `bc51c8f8c872694c5e51e60572fe13c39adf09e6`;256 UI tests, TypeScript, scoped lint and responsive fixtures passed. Only UI commits were rebased/retargeted after the backend merge.
- #477/#478/#479 closed; roadmap #476 remains open. Existing auth-scan baseline #480 remains separate.

Hosted Actions were disabled by the existing workflow. Normal merge was blocked by unavailable required checks; head-matched squash through the repository administrator override was used under the owner's merge authorization. No rules, checks or CI status were modified or fabricated. The PR timeline records this explicitly. Vercel previews were successful. Local tests are not hosted CI.

## New approved priorities — code ready for owner review

All workstreams used GPT-6.1 Sol/xhigh, isolated worktrees and fake external systems. Parent reviewed actual diffs, reproduced boundary failures and integrated shared contracts/migration order. Primary dirty checkout, unrelated fiscal/public UI work, running servers, deployment and real accounts were not modified by this batch.

| Work | PR | Tracking | Review/merge order |
|---|---|---|---|
| Compact ingestion statistics and source lookup reuse | [#487](https://github.com/Rodgers31/audit_app/pull/487) | #481 stays open for measured live egress/hosting gates | Independent main-base PR |
| Server-only Meta account discovery and encrypted grants | [#489](https://github.com/Rodgers31/audit_app/pull/489) | Code #483; operational #488 | Review/merge before media |
| Inspected private media intake/library/composer | [#492](https://github.com/Rodgers31/audit_app/pull/492) | Code #482; operational/maintenance #490 | Stacked on489; after its merge rebase only media commits and retarget main |

New PRs remain open for owner/Copilot review. Re-fetch genuine inline and review-body comments, verify each against the current head, reproduce real failures and fix the safest implementation. Do not resolve a thread merely because code changed. Recheck required-check availability and exact merge head without touching other workstreams. Closes statements complete #482/#483 only when accepted code merges; they do not mark operational gates complete.

## Verification and code evidence

Egress:35 tests passed after rebasing onto accepted main. Actual local PostgreSQL fixtures preserve null/financial/provenance behavior, metadata labeling, duplicate URL rejection and rollback after real flush failure. Selected decoded-value estimates: stats5,253,971→356 bytes; repeated budget source lookup1,314,200→2; revenue source lookup1,314,274→46. These are fixture estimates, not PostgreSQL wire or Supabase billing. Worker idle/busy query/connection behavior is measured without weakening its gates. Full evidence is in the egress PR's docs/infrastructure/supabase-egress/batch2-egress/.

Meta:266 combined backend tests and278 UI tests passed; TypeScript/lint, actual DDL/RLS/FK/history retention, verified actor/session binding, provider/tracing redaction, reconnection/disconnection races and standalone callback middleware passed. An additional independent read-only18-test review found no parent integration defect. See META_CONNECTIONS_HANDOFF.md and META_INTEGRATION_ACCEPTANCE.md.

Media integrated with Meta/foundation:534 combined backend tests and373 UI tests across20 suites passed. Final portable media test-fixture change passed259 media tests; absence of assigned database opt-in passed9 tests/skipped3 PostgreSQL cases before any connection. Native tools are discovered read-only and their acceptance lane skips explicitly if absent. TypeScript/lint, one Alembic head, actual sixteen-table DDL/RLS/FK/downgrade, socket-denied app import and independent6-case cleanup/storage acceptance passed. Actual rendered controls at1440/768/390/320 passed layout/focus/accessibility checks with external requests blocked. See BATCH_2_MEDIA_HANDOFF.md and MEDIA_INTEGRATION_ACCEPTANCE.md; selected screenshots and browser report are in previews/batch2/.

Media review corrected hidden SDK wire retries, ambiguous finalize settlement, double release, late write fencing, candidate starvation and corrupt final samples. Root composer regressions failed before context/busy wiring and passed afterward. HTTP completion/failure events now correlate static route templates, verified UUIDs, request IDs, duration, result/error codes without query/body/secret serialization. Durable audit records preserve feature phases.

## Operational gates remain open

- #481: representative seven-day live egress attribution/budget and an accepted reliable worker host. Fixture reductions cannot reverse accrued usage or establish continuity before the existing October8 restriction date. Retain Supabase; no upgrade/migration or production query occurred in this batch.
- #488: Meta app access/registered callbacks, key backup/rotation, deployed ingress logging, provider deletion/deauthorization, reviewed DB role/migration and separately authorized owned-account validation. Browser profile setup is not API authorization.
- #490: private R2/CORS/create-only/length/host/native-tool receipts; safe maintenance activation, unresolved-write reconciliation, grant-renewal/in-flight browser PUT cleanup semantics and shared reference/retention locks. Cleanup is unwired, unknown finalization quota is retained and ready-original deletion is deferred. No recurring fee/provisioning has been accepted.

No real OAuth, account connection, bucket provisioning, post, production migration, package installation, environment/deployment/CI change or background task restart occurred. All automatic controls and actual publishing adapters remain OFF/absent. No external credentials are shipped to the frontend; authenticated temporary storage grants are narrowly scoped and excluded from post documents/logs.

## Recommended next coding batch after owner review

1. [#484 queue and complete schedule management](https://github.com/Rodgers31/audit_app/issues/484): server-side delivery filters/pagination and safe edit/reschedule/cancel/publish-now workflows preserving immutable authorizations and worker claims.
2. [#490 media maintenance/reconciliation](https://github.com/Rodgers31/audit_app/issues/490): implement conservative unknown-outcome recovery and grant/deletion safety before activating a bounded maintenance runner. Keep actual private bucket/host validation separately authorized.
3. [#491 first native Facebook/Instagram publishing adapters](https://github.com/Rodgers31/audit_app/issues/491): freeze credential/media access ports, implement a small truthful format slice, durable container/checkpoint/reconciliation and fake HTTP tests using the existing worker protocol. Real enablement waits for #481/#488/#490.

Freeze shared adapter/material and cleanup/retention contracts before parallel implementation. Assign only disjoint modules/tests; one integrator owns shared model/API/migrations. Threads follows with separate authorization; X charges and TikTok app-use-case restrictions remain explicit platform gates. AI copy/video generation and automatic approval come after dependable manual publishing.
