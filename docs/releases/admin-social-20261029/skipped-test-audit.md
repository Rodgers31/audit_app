# Follow-up: all 708 previously skipped social tests

All **708 original skipped cases in 59 modules now execute and pass** in their explicitly assigned offline fixtures. None is excluded as irrelevant, converted to xfail, or credited without execution. The matrix includes shared release behavior and historical migration/role contracts, plus the dormant X/TikTok fake transports. Those platform tests do not establish live provider access.

| Fixture group | Original cases | Result |
|---|---:|---|
| Worker ownership, queue, permissions, recovery and platform roles | 390 | All passed, zero skips/errors/failures |
| Source qualification, generation, policy, archive and privacy | 108 | All passed, zero skips/errors/failures |
| Media, rendering, retention, cleanup and metrics | 104 | All passed, zero skips/errors/failures |
| Mounted API, connections, callback, scheduling and platform workflows | 106 | All passed, zero skips/errors/failures |

The broad native regression separately passes **4,484 cases and 84 subtests**, with zero failures/errors, in 487.34 seconds. It still reports 705 skips because that environment supplies only its current B83 and Reels fixtures. Every one of those skipped identities is exercised by the matrix. The combined receipts cover **5,189 unique social-suite cases**, including eight added controls, without counting repeated coverage twice. The original 93 failures/errors also pass again in the broad run.

See the [strict case ledger](skipped-test-audit.json) and [validation/input receipt](skipped-test-validation.json). A passing local test matrix does not authorize production publication, provider access, source acquisition or deployment.

## Repairs and release relevance

Historical migration tests retain their pinned revisions, strict loopback resources, DDL assertions, RLS checks and downgrade refusals. Current ORM/worker tests explicitly request the real generation/policy descendants, rather than querying a historical minimal schema with current models. Source-dependent workflows now use the full current application fixture and actual retained county PDFs, writers, qualified readers and saved worker witnesses. The producer remembers which owned ingestion ran but reads and qualifies the evidence afresh; mutation or missing authority remains a refusal.

Positive queue/native fixtures now carry an AuditGava URL. Four additional real-PG controls prove that self-consistent legacy targets with missing, external, lookalike or query-disguised destinations cannot obtain a dispatch permit or create a publish attempt. Existing unauthorized-target assertions continue to exercise their intended deeper guards.

The platform fixtures preserve provider-specific constraints: TikTok carries the AuditGava destination in caption text and explicitly clears the separate link field; consent remains per post. X fixtures use the configured cost for a link-bearing operation, preserve exact budget exhaustion, and reconcile the complete rendered text including the URL. These are fake transports and synthetic budgets; no paid request or connection was made. Migration-parent/head assertions now match the actual repository chain.

The mounted-app inventory explicitly checks all 100 private social routes, including the six added routes, for unauthorized/forbidden responses and private no-store headers. A credential-rotation test creates a fresh repository after the preceding worker closes its admission event. The native CLI positive fixture explicitly supplies its isolated native/read-media gates. Query-budget tests accept only the two ordered ownership/claim queries and, for the native engine, its exact transaction-local deadline setter.

Backup/recovery cases execute real cached PostgreSQL 17 dump/restore tools. Narrow socketless fixture adapters replace hardcoded executable/controller paths while refusing foreign endpoints and unsupported commands. This qualifies the backup/export/restore behavior, not native Docker CLI portability on every host. Python distributions and existing OS files were not silently replaced.

An explicit controller-owned readiness fixture lets the 13 actual role/migration tests run in a capped offline namespace without giving the test runner a Docker socket. Independent checks found and reproduced two cleanup defects in this newly added test helper: lost commit acknowledgment, and disappearance of schema ownership proof while roles remain. Setup now checks the exact identity, directory and absence of owned names, commits a UUID ownership marker atomically with schema/roles, reconciles uncertain commits, refuses unproven cleanup and always disposes its engine. Normal cleanup, pre-existing-owner preservation, changed-marker refusal and both regression cases pass.

All fixes affect tests and local preview fixtures. No backend application code, migration, dependency, deployment descriptor, workflow or activation default changes in this follow-up.

## Execution provenance and independent verification

Execution uses cached, capped offline Docker, PostgreSQL 17 and the same Python runtime/distribution versions as the prior audit. Actual FFmpeg/ffprobe/procps and PG client tools are exposed read-only. Source is read-only; fixtures use bounded tmpfs, distinct owned namespaces and exact guarded names. Credentials and owned peers are removed after execution; the existing local review server remains running.

The receipts distinguish input versions instead of claiming every case ran one hash. Source108 and worker390 execute the frozen 1,502-file input. Root106 and media104 execute the final 1,504-file input. The only differences are the readiness test helper and two read-only repository inputs needed by the broader suite. The broad run uses the preceding input; its 13 external readiness cases are covered separately after the final cleanup guard repair. Backend application bytes are unchanged throughout.

The first broad replay omitted the workflow definition and retained view-contract JSON: 12 failures and 22 setup errors were all missing-file errors. That failed replay remains retained. The corrected replay includes both exact files and passes. Independent boundary execution passes 47 source/readiness controls; four real-PG schema controls and 13 strict recovery-tool controls also pass. The aggregation utility passes 82 independent controls (eight valid positives and 74 refused invalid inputs), covering missing, skipped, duplicate, substituted and stale-success evidence, actual source-directory binding and optimized Python.

## Actual platform status and retained holds

The [read-only production account status](platform-status.json) shows Facebook and Instagram identities saved as connected, with publishing disabled and adapters unavailable. This describes stored account state, not fresh provider acceptance. Threads has no connected identity and its setup is disabled/unverified. X has no admitted product access or budget. TikTok reports product access unavailable. New connection callbacks remain held pending ingress verification. No connection flow or maintenance action was started.

All five accounts in the loopback review app are illustrative preview samples. Their rows now say **preview only**, and the banner states that no live accounts are connected there. This changes no production capability. Local TypeScript, scoped lint and browser review pass; the production frontend components remain unchanged.

Publishing, automatic approval/scheduling/publication, uploads, provider access and production social workers remain off. No production draft/control/source/environment change, ingestion, provider call, hosted run, merge or deployment occurred. The existing PRs remain drafts for owner review; rollout and eventual activation require separate approval and rechecking the retained holds.
