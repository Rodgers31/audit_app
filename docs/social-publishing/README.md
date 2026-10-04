# AuditGava social publishing — durable design record

Consolidated **2026-10-03**. This directory preserves the account work, product decisions, approved visual direction, SDK research and engineering design previously held in the conversation and local task artifacts.

**Status: foundation PRs #485/#486 and reviewed egress/Meta PRs #487/#489 are merged; #492's media review fixes passed combined verification.** The [current batch ledger](implementation/BATCH_2_STATUS.md) records accepted commits, review dispositions and remaining operational gates; the linked PR timelines are authoritative for the final media merge identity. Read the historical [batch 1 ledger](implementation/BATCH_1_STATUS.md) for its original slice. Live storage/OAuth, real publishing adapters, deployment and automatic approval remain gated.

## Read in this order

1. [Engineering blueprint](ENGINEERING_BLUEPRINT.md) — current architecture, repository audit, schema, adapter/API contracts, OAuth, all platform constraints, state machines, scheduling, failure handling, UI wireframes, tests and phased agent handoff.
2. [Low-cost operating profile](LOW_COST_OPERATING_PROFILE.md) — authoritative cost/egress amendment: retain Supabase, compact queue reads, adaptive polling, bounded media and explicit hosting assumptions.
3. [Supabase investigation](../infrastructure/supabase-egress/README.md) — measured current quota problem and separate proposed remediation work.
4. [Account setup and branding](ACCOUNT_SETUP_AND_BRANDING.md) — what was actually configured and what remains unverified.
5. [Content and video strategy](CONTENT_AND_VIDEO_STRATEGY.md) — fact provenance, recurring formats, platform variants and lightweight video direction.
6. [Approved admin concept](design-reference/README.md) — preserved visual artifact; detailed current behavior is specified in the blueprint.
7. [Current implementation/review ledger](implementation/BATCH_2_STATUS.md) and [batch 2 ownership contract](implementation/BATCH_2_CONTRACT.md).
8. [Batch 1 contract](implementation/BATCH_1_CONTRACT.md) and [verification/review ledger](implementation/BATCH_1_STATUS.md) — exact implementation slice, APIs, defaults, tests and remaining gates.

## Decisions to retain

- Manual posting is first-class. Manual and generated posts converge on the same revisions, targets, validation, scheduling and delivery pipeline.
- AuditGava owns approval, scheduling, audit history and per-destination results. Keep the existing Python/FastAPI/PostgreSQL architecture; use narrow official API adapters and mature libraries where useful.
- The supplied TypeScript Social SDK is **not** the selected foundation. Importing it would not supply the missing application workflows, eliminate platform approvals, or make X free; its inspected direct support also lacks Facebook. Do not add a Node service by default.
- Redis/Celery and paid scheduling SaaS are not initial requirements. PostgreSQL is the authoritative durable queue; one separate worker claims due work safely.
- Generated content requires human approval initially. Future selective automatic approval is disabled by default and shares the same downstream checks.
- Selected platforms get independent targets. A failure on X does not republish successful Facebook/Instagram/Threads targets. Ambiguous remote outcomes require reconciliation, not blind retries.
- Credentials stay server-side, encrypted at rest with a managed server key and rotation plan. Browser login/profile linking is not developer API authorization.
- TikTok eligibility and API-route suitability remain gates; an internal-only utility cannot assume approval under the standard Content Posting API. Evaluate the separate authorized owned-business-account route.
- X API cost is an external platform constraint, separate from our infrastructure. A zero-API-spend policy requires keeping X publishing manual unless current access terms change.
- Keep Supabase. Optimize existing database-result egress and budget new queue traffic. Store media outside PostgreSQL; substantial video may justify a separate object store without migrating the database.

## Historical research, preserved with context

These documents record how decisions were reached. **They are not competing current implementation specifications.** Earlier managed-service suggestions were superseded by the user's preference to avoid recurring SaaS fees; the initial TikTok assessment was expanded to distinguish Business Accounts APIs.

| Record | Purpose |
|---|---|
| [Initial account audit](research-history/account-audit-before.md) | Before-state observations |
| [Original consolidated setup report](research-history/account-setup-report.md) | Detailed account verification and initial research; later technical decisions supersede it |
| [Social SDK source audit](research-history/social-sdk-audit.md) | Inspected npm 0.5.0 and source commit `a76fb612c8abd5926fbfa40c9a3f556a523531ea` |
| [Original architecture research](research-history/architecture-research.md) | Detailed repository seams and content opportunities |
| [Publishing option comparison](research-history/social-planning-options.md) | Earlier architecture/provider tradeoffs |
| [Earlier integration plan](research-history/social-integration-plan.md) | Managed/native exploration before final free-first direction |
| [Free repository comparison](research-history/free-social-repos.md) | Postiz and other open-source alternatives; license/hosting tradeoffs |
| [Website footer PR record](research-history/social-footer-pr.md) | Earlier social-link PR, not created by this documentation task |

The current source/application can change independently of these records. Recheck exact line numbers, dependencies and official platform docs at implementation time. Do not interpret historical source snippets as application code installed in this repository.

## Next-agent instructions

Read the blueprint, low-cost profile and current egress evidence before implementing. Establish the domain/state/adapter/API contracts before parallel work. Inspect dirty files and recent commits; use an isolated branch/worktree for separately authorized code changes and coordinate shared auth/cache/main-module ownership. Never reset another agent's work.

Check the batch ledger and Git/PR state before recreating the shared domain or worker. The reviewed batch supplies egress reduction, inspected media and Meta connection code with executed regression receipts. Next coding priorities are queue/schedule completion (#484), safe media maintenance (#490) and native Meta publishing adapters (#491); live egress/hosting and account/storage gates remain separate. Do not begin with all five real integrations, automated copy generation or video rendering. Use the blueprint's phase definitions and acceptance tests.

When this design changes, update the authoritative blueprint and decision log, date the change, and preserve the reason. Keep historical reports clearly labelled. Documentation being present in the working tree is not proof it has been committed, pushed or merged; check Git before handing work to a different checkout.
