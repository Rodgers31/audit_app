# Batch 1 implementation ledger

Started 2026-10-03. This ledger supplements the [frozen contract](BATCH_1_CONTRACT.md); the engineering blueprint remains the target specification.

The reviewed foundation is now merged through PRs #485/#486. This file retains the historical batch 1 evidence; [BATCH_2_STATUS.md](BATCH_2_STATUS.md) records accepted merge identities, current PRs and next priorities.

## Tracking and ownership

| Work | Tracking | Branch | Agent settings |
|---|---|---|---|
| Roadmap | [#476](https://github.com/Rodgers31/audit_app/issues/476) | Integrator: `codex/social-publishing-core` | Parent review/consolidation |
| Domain/admin API | [#477](https://github.com/Rodgers31/audit_app/issues/477) | `codex/social-domain-api` | GPT-6.1 Sol, xhigh |
| Durable worker | [#478](https://github.com/Rodgers31/audit_app/issues/478) | `codex/social-publishing-worker` | GPT-6.1 Sol, xhigh |
| Admin composer | [#479](https://github.com/Rodgers31/audit_app/issues/479) | `codex/social-admin-composer` | GPT-6.1 Sol, xhigh |

Two implementation agents run under the parent chat. The frontend runs in a separate Codex task because this chat's accumulated sub-agent thread limit prevented a third launch. All use separate managed Git worktrees based on current main plus the documentation/contracts commit. Existing source-data review work remains untouched.

## Current scope

This batch establishes the domain/manual draft API, durable local fake-adapter pipeline, and responsive composer/results UI. It does not enable real social publishing, connect accounts, apply production migrations or start a production worker. Publishing/automatic approval remain disabled by default.

Media metadata is modeled and fixture previews can be tested. Actual upload/storage implementation follows separately. UI must report unavailable uploads/empty connections honestly. Normal tests cannot depend on real social posts or production data.

## Verification approach

- Domain/API: strict input, sparse inheritance, hashes, version/idempotency/approval/state guards, transactional audit, no-store responses.
- Worker: real local PostgreSQL claims, two-worker races, lease/recovery/fencing, pause/cancel ordering, independent failure/retry and ambiguous remote outcomes.
- UI: master/override isolation, explicit account/subset selection, draft persistence/errors, stale-version handling, previews and partial results; responsive/accessibility checks.
- Integrator: independent executed hostile-case review, combined API/worker checks, migration review and schema safety, test evidence and scoped diffs before PRs.

Local integration tests use a newly created, resource-bounded PostgreSQL 16 container and distinct test databases per workstream. No existing container is stopped/reconfigured. Only the test container created by this task is eligible for cleanup.

## Review/merge checkpoint

Open tested PRs for owner review. Address valid owner/bot comments based on reproductions and code evidence. The owner has now authorized merging after those fixes and approved the next three priorities. Close linked feature issues when accepted code merges; keep the roadmap open for later batches. Do not claim hosted CI passed while repository Actions is disabled by another workstream.

## Implemented boundaries

- Additive Alembic revision `f38c61a9d203` defines twelve social-domain tables, due-work indexes, immutable revision/authorization/payload/audit guards, and browser-role access restrictions. No production migration has been applied. Downgrade refuses to discard retained social history.
- Admin-only `/api/v1/admin/social` routes use existing Supabase authorization. Commands have strict version/UUID schemas, atomic idempotency receipts and audits. Master content and sparse per-account overrides resolve into an immutable approved revision and independent delivery targets.
- One separately invoked Python worker uses PostgreSQL as its queue. No scheduler starts in the API or ETL lifespan. Its CLI has an empty real-adapter registry and requires explicit database configuration. There are no operational account seeds, credential bundles or live provider calls.
- Worker claims are bounded and fenced; a durable operation intent precedes each external mutation. Ambiguous outcomes preserve an account hold and require reconciliation. A definitive-absence proof must identify the original mutating operation and account and affirm verified complete coverage before a resend is permitted.
- Structured logging uses an allowlist of IDs, action/error codes, operation/attempt identity, outcomes and durations. It excludes post copy, tokens, DSNs, raw provider responses and exception messages. The persistent audit table retains command, claim, delivery, retry and control history.
- Social response middleware enforces `private, no-store` for successful routes, authentication/validation errors, unmatched routes and pre-response middleware failures. Compact delivery-status responses omit full documents, evidence and resolved payloads.
- Frontend composer work is separate from the backend PR. It uses the existing authenticated API client and actor-scoped query caches, shows unavailable uploads/connections truthfully, and distinguishes queued receipts from published results.

## Executed verification

| Verification | Result | Scope |
|---|---|---|
| Combined social backend suite, Python 3.9 | **169 passed**, 4 existing configuration/deprecation warnings | Explicit disposable PostgreSQL databases for domain, worker and actual-migration integration; remaining strict-contract tests use isolated SQLite/fakes |
| Five-platform API-to-worker cascade | Passed | Four fake destinations publish; X fails, is retried alone, and the other four are not resubmitted |
| Actual migration history guards | Passed | Raw SQL cannot change approved revision, target payload, authorization or delete audit history |
| Claims, lease fencing and crash recovery | Passed | Independent workers, real lock races, expired admissions, SIGKILL after durable fake receipt, late receipt and reconciliation |
| Full application smoke, Python 3.13 | Passed | Routes mounted; unauthenticated request is 401; unmatched route is 404; both are private/no-store; sockets rejected and lifespan not executed |
| Existing targeted backend regression lane | **53 passed, 1 baseline failure** | Auth-route scan, response models, ORM models, ETL admin and health endpoints |
| Alembic head inspection | Passed | Single head `f38c61a9d203`; no production connection/migration |
| Social frontend interaction/contract suite | **87 passed across 9 suites** | Executed by UI agent and independently rerun by integrator; fake API fixtures only |
| Whole-frontend TypeScript and scoped ESLint | Passed | Integrator reproduced four untyped visual-harness arguments, UI agent corrected them, then fresh typecheck and lint passed |
| Responsive browser fixture checks | Passed | Actual rendered components at 1440/768/390/320px; blocked external requests, labelled controls, keyboard focus and mobile heading/footer clearance |

The baseline failure is [#480](https://github.com/Rodgers31/audit_app/issues/480). The existing scanner does not recognize the HMAC-authenticated `POST /api/v1/system/cache/status` route. The same failure was executed against an isolated archive of main before feature changes; the route verifies the signed body. This batch does not alter the other workstream's cache route or claim the baseline suite is entirely green.

The new backend suite ran with `--confcutdir=backend/tests/social` and explicit loopback-only test DSNs. No real OAuth, external platform posts, production database queries, dependency installation or environment/deployment changes were used. Hosted Actions remain disabled under another workstream; these are local results, not hosted CI evidence.

Independent executed review found and fixed: multiple unresolved mutation intents under one claim; target payloads not bound to the approved revision; strict-input bypasses; lock waits using stale transaction timestamps; backwards audit-FK claim deadlocks; expired account-admission reuse; unchecked absence evidence permitting an unsafe resend; outer error responses lacking no-store; and UI receipt/version/idempotency inconsistencies. Relevant regressions first reproduced the failures and then passed after the fixes.

The worker agent independently reviewed the integrator's middleware/version/integration changes read-only, executed 19 focused tests on Python 3.9, and verified additional hostile version and ASGI failure cases. It found no important integration regression or logging leakage; actual-migration cascade coverage was executed by the integrator rather than claimed as independently rerun by that reviewer.

The UI companion branch retains its detailed `UI_HANDOFF.md`, screenshot fixtures and browser measurements. Browser checks use static component exports; they are not a claim of real authenticated Next.js hydration, a production Next build or provider end-to-end verification. No existing development server was reused/restarted.

## Next priorities and operational gates

1. [#481 — Supabase egress reduction](https://github.com/Rodgers31/audit_app/issues/481): measure current shared-pooler result traffic and address overfetch before enabling more background workloads. Keep Supabase; social queue reads are already compact/adaptive but do not repair existing traffic.
2. [#482 — Inspected media uploads/library](https://github.com/Rodgers31/audit_app/issues/482): build authenticated bounded uploads, server-side byte inspection and storage access. Keep bytes outside PostgreSQL and settle video egress/hosting choices first.
3. [#483 — Meta OAuth and credentials](https://github.com/Rodgers31/audit_app/issues/483): future implementation of server-only authorization, encrypted token bundles and exact Page/Instagram asset discovery, with fake-flow tests required before completion. These components are not implemented or tested in batch 1. Live OAuth/account permission changes remain a separate operational step.
4. Add reviewed Facebook/Instagram real adapters after media and credential contracts, then Threads. Keep X API fees and TikTok app-use-case eligibility as explicit gates; no claim that browser profile setup supplies API authorization.
5. Apply the reviewed migration and provision the separate worker only after an authorized deployment/cost review. Initial real generated content still requires human approval. Generation, automatic approval, automatic scheduling and automatic publication are not activated by this batch.

Existing `.github/workflows/docker-build-deploy.yml` and `seed.yml` run `alembic upgrade head` when their workflows execute. They were not changed or enabled here. Review the new additive migration before allowing those existing deployment/seed runs; merging a migration into the deployable branch is not a promise that it will remain unapplied indefinitely. The normal backend Docker command starts only Uvicorn, not the social worker.

[#484 — Global delivery filters and schedule management](https://github.com/Rodgers31/audit_app/issues/484) retains the known first-batch browsing limitation: scheduled/history views filter the current compact page and label their counts accordingly. A later API contract adds correct global delivery pagination, exact schedule metadata and safe reschedule controls instead of fetching every document into the browser.

Feature issues #477–#479 close only when their accepted PRs merge. The epic #476 remains open for the roadmap. Review branches are `codex/social-publishing-core` (base main) and `codex/social-admin-composer` (initial base core); the PR timelines record final heads and merge state. Review the core first, then retarget/rebase the companion UI after the accepted core merges. See [the review evidence](REVIEW_485_486.md) for verified findings and current local checks.
