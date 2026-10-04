# Batch 2 implementation and review ledger

Updated 2026-10-03. Read alongside BATCH_2_CONTRACT.md, the engineering blueprint and low-cost profile. This ledger separates merged foundation, reviewable code and operational acceptance; an open PR is not deployment.

## Reviewed foundation accepted

The owner authorized merging after actual-code audit and review fixes. All review findings were checked against code and executed regressions rather than blindly applied. Detailed receipts remain in REVIEW_485_486.md and UI_HANDOFF.md.

- [#485 backend/domain/worker](https://github.com/Rodgers31/audit_app/pull/485) merged as `3cf15b60f00872904ac06e7302606f282e5b66c1`; final 196 social tests and 34 existing backend regression tests passed.
- [#486 admin composer](https://github.com/Rodgers31/audit_app/pull/486) merged as `bc51c8f8c872694c5e51e60572fe13c39adf09e6`; 256 UI tests, TypeScript, scoped lint and responsive fixtures passed. Only UI commits were rebased/retargeted after the backend merge.
- #477, #478 and #479 closed; roadmap #476 remains open. Existing auth-scan baseline #480 remains separate.

Hosted Actions were disabled by the existing workflow. Normal merge was blocked by unavailable required checks; head-matched squash through the repository administrator override was used under the owner's merge authorization. No rules, checks or CI status were modified or fabricated. The PR timeline records this explicitly. Vercel previews were successful. Local tests are not hosted CI.

## Reviewed batch 2 — accepted code and final media verification

All workstreams used GPT-6.1 Sol/xhigh, isolated worktrees and fake external systems. Parent reviewed actual diffs, reproduced boundary failures and integrated shared contracts/migration order. Primary dirty checkout, unrelated fiscal/public UI work, running servers, deployment and real accounts were not modified by this batch.

| Work | PR | Tracking | Review/merge order |
|---|---|---|---|
| Compact ingestion statistics and source lookup reuse | [#487](https://github.com/Rodgers31/audit_app/pull/487) | #481 stays open for measured live egress/hosting gates | Merged as `3f7347aeb436b44fa5ccd921f2a7a9b30151102c` |
| Server-only Meta account discovery and encrypted grants | [#489](https://github.com/Rodgers31/audit_app/pull/489) | Code #483; operational #488 | Merged as `9bc2133088572fb0eceab613f7dc8c3c4def2801` |
| Inspected private media intake/library/composer | [#492](https://github.com/Rodgers31/audit_app/pull/492) | Code #482; operational/maintenance #490 | Review fixes verified; only media commits rebased onto accepted #489; final head/merge identity in PR timeline |

The owner authorized fixing verified review findings and merging in dependency order. All four genuine inline findings and two additional review-body concerns were audited. Replies classify valid issues versus partially correct recommendations and cite pushed commits. Thread resolution follows reachable fixes, not assumed correctness. Closes statements complete #482/#483 when accepted code merges; they do not complete operational gates. This commit records media merge readiness; GitHub is authoritative for its eventual merge identity.

Unrelated #493 was preserved when rebasing onto current main, including its bounded manual-verification workflow and write-route auth scan. Actions remains disabled; no manual run or automatic CI/seeding/deploy workflow was enabled. Required hosted checks are therefore unavailable. The previously authorized head-matched administrator merge override is recorded in the PR timelines; executed local verification is not hosted CI.

## Verification and code evidence

Egress: initial 35 tests and final review 54 tests passed. Actual local PostgreSQL fixtures preserve null/financial/provenance behavior, metadata labeling, duplicate URL rejection and rollback after real flush failure. Caller connection queries (including dropped blank values) are rejected before engine creation; literal host/hostaddr is pinned. Selected decoded-value estimates: stats 5,253,971→356 bytes; repeated budget source lookup 1,314,200→2; revenue source lookup 1,314,274→46. The latter two baseline values use twenty records; independently executed two-record baseline receipts are 131,402/131,404. Both are correct and now explicitly labelled. These are fixture estimates, not PostgreSQL wire or Supabase billing. Worker idle/busy query/connection behavior is measured without weakening its gates. Full evidence is in [the egress review receipt](../../infrastructure/supabase-egress/batch2-egress/REVIEW_487.md).

Meta: initial 266 combined backend tests and 278 UI tests passed. Review removed obsolete Accounts navigation/copy, rejects contradictory unverified-available status, and disables Connect/Reconnect after a failed status refresh even when stale data remains cached. Actor-bound selection/disconnect recovery and unsaved-draft navigation remain intact. Final Meta-only integration: 337 social tests plus 44 existing backend regressions (381 total), 298 UI tests/18 suites, TypeScript and scoped lint passed. Shared fixture protection includes 71 tests, independent 121-case verification and an actual crash-child recovery under hostile PGHOSTADDR. The child receives the pinned engine URL rather than copying the original DSN. See META_REVIEW_ROUND_1.md and REVIEW_POSTGRES_TARGET_SAFETY.md, alongside the original handoff/acceptance records.

Media integrated with Meta/foundation: original 534 combined social tests and 373 UI tests/20 suites passed. Final review on accepted main: **693 social tests plus 44 existing backend regressions (737 total)** passed, including actual disposable PostgreSQL, native inspection and fake-provider recovery. **441 UI tests/23 suites**, TypeScript and scoped ESLint passed. DEL/C0 filenames now fail before reservations/storage; image labels follow advertised formats and lost capability disables upload. The media cleanup PostgreSQL fixture reuses the accepted pinned helper; twelve intercepted-engine safety cases ran red before alignment and green afterward. The only rebase conflict was empty-account copy; accepted #489 copy and all media busy/context controls were preserved. See REVIEW_492.md and REVIEW_492_INTEGRATION.md.

Historical pre-review receipts: final portable media fixtures passed 259 tests; absent assigned DB opt-in passed 9/skipped 3 PostgreSQL cases before connection. One Alembic head, actual sixteen-table DDL/RLS/FK/downgrade, socket-denied import and independent 6-case cleanup/storage acceptance passed. Rendered controls at 1440/768/390/320 passed layout/focus/accessibility checks with external requests blocked. These static browser fixtures were not rerun in this review round and are not live authenticated storage/CORS acceptance. See BATCH_2_MEDIA_HANDOFF.md, MEDIA_INTEGRATION_ACCEPTANCE.md and previews/batch2/.

Media review corrected hidden SDK wire retries, ambiguous finalize settlement, double release, late write fencing, candidate starvation and corrupt final samples. Root composer regressions failed before context/busy wiring and passed afterward. HTTP completion/failure events now correlate static route templates, verified UUIDs, request IDs, duration, result/error codes without query/body/secret serialization. Durable audit records preserve feature phases.

## Operational gates remain open

- #481: representative seven-day live egress attribution/budget and an accepted reliable worker host. Fixture reductions cannot reverse accrued usage or establish continuity before the existing October8 restriction date. Retain Supabase; no upgrade/migration or production query occurred in this batch.
- #488: Meta app access/registered callbacks, key backup/rotation, deployed ingress logging, provider deletion/deauthorization, reviewed DB role/migration and separately authorized owned-account validation. Browser profile setup is not API authorization.
- #490: private R2/CORS/create-only/length/host/native-tool receipts; safe maintenance activation, unresolved-write reconciliation, grant-renewal/in-flight browser PUT cleanup semantics and shared reference/retention locks. Cleanup is unwired, unknown finalization quota is retained and ready-original deletion is deferred. No recurring fee/provisioning has been accepted.

No real OAuth, account connection, bucket provisioning, post, production migration, package installation, environment/deployment/CI change or background task restart occurred. All automatic controls and actual publishing adapters remain OFF/absent. No external credentials are shipped to the frontend; authenticated temporary storage grants are narrowly scoped and excluded from post documents/logs.

## Recommended next coding batch after this review/merge

1. [#484 queue and complete schedule management](https://github.com/Rodgers31/audit_app/issues/484): server-side delivery filters/pagination and safe edit/reschedule/cancel/publish-now workflows preserving immutable authorizations and worker claims.
2. [#490 media maintenance/reconciliation](https://github.com/Rodgers31/audit_app/issues/490): implement conservative unknown-outcome recovery and grant/deletion safety before activating a bounded maintenance runner. Keep actual private bucket/host validation separately authorized.
3. [#491 first native Facebook/Instagram publishing adapters](https://github.com/Rodgers31/audit_app/issues/491): freeze credential/media access ports, implement a small truthful format slice, durable container/checkpoint/reconciliation and fake HTTP tests using the existing worker protocol. Real enablement waits for #481/#488/#490.

Freeze shared adapter/material and cleanup/retention contracts before parallel implementation. Assign only disjoint modules/tests; one integrator owns shared model/API/migrations. Threads follows with separate authorization; X charges and TikTok app-use-case restrictions remain explicit platform gates. AI copy/video generation and automatic approval come after dependable manual publishing.
