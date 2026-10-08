# Supabase egress remediation plan

Status: **partially implemented; live attribution and Free-tier acceptance remain open in #481**. Updated 2026-10-08. The phases below preserve the original 2026-10-03 plan; they are not a list of entirely unfixed defects. Read [evidence](EVIDENCE.md) and [code audit](CODE_AUDIT.md) as dated records, and inspect current main before choosing work. Do not reset, overwrite or stop another workstream.

## Current implementation map — 8 October

- PR #487 merged SQL ingestion statistics and distinct-source lookup reductions for national budget/revenue writers. [Batch 2 receipts](batch2-egress/README.md).
- PR #505 merged economic source identity batching and narrow Audit comparison reads, preserving full extraction hashes and partial-load repair. [Batch 3 receipts](batch3-query-transfer.md).
- Current main already has county-list/federal projections, freshness caching, shared-cache coalescing, bounded client retries and matching SSR hydration. Their historical findings must not be implemented again from this plan alone.
- This investigation implements the remaining bounded public query reductions: money-flow accounting/context columns, county findings page hydration, basic county audit summaries, budget-only qualification context and source-vintage dates. [Current query measurements and remaining work](2026-10-08-public-query-transfer.md).
- Source-object storage has independently passed private R2/runtime acceptance (#137/#504). It does not fix database query overfetch or prove Free-tier headroom. Supabase Pro remains active.
- Actions remains OFF. Local query fixtures do not require hosted Actions. Code work proceeds now; seven representative deployed days are the final operating-profile gate, not a reason to postpone implementation.

Startup/recycle frequency, actual cache behavior across all cache instances, completed-load checkpoints, a separate compact federal homepage fill and future worker demand remain measurement or implementation candidates. The legacy cache yielding probe does not establish a current single-worker SQL stampede. Use the current evidence to select each follow-up.

## Outcome and acceptance criteria

Retain Supabase, preserve financial correctness and freshness, and aim for total uncached egress at or below **120 MB/day averaged over seven representative days**, including ordinary ingestion and a deployment. This is a budget, not a measured attainable result yet. Distinguish quieter traffic from actual efficiency improvements.

Correctness takes priority over the target. Never remove provenance/publishability checks, silently exclude inconvenient records, turn unknown amounts into zero, stop required ingestion or weaken authorization to reduce bytes. If necessary fresh workloads still exceed the allowance after optimization, report that evidence and price the smallest appropriate plan.

## Phase 0 — time-sensitive quota handling and baseline

Owner decision before Oct 8: review the exact restriction with Supabase support, or accept the documented paid continuity fallback if uninterrupted access is necessary. Optimization does not reset accrued usage. Support relief is uncertain; do not promise an extension. This investigation did not message support or change billing.

Technical baseline, in a future implementation task:

1. Record daily provider egress, deployment SHA and ingestion times. Use the existing dashboard; no need for a paid monitoring product.
2. Record query-stat snapshots with timestamps and reset boundary. Compute counter deltas; never reset global statistics to simplify attribution.
3. Confirm actual host command, replicas, worker restarts and cache behavior from existing logs. The Docker command is a risk indicator, not proof of the current deployed topology.
4. Confirm which scheduled and developer clients use production, without printing secrets or reconfiguring their environments.
5. Establish fixture responses for fiscal totals, latest audit opinions, source dates, null amounts and provenance eligibility before changing queries.

Deliverable: before-measurements, current caller map and narrowly scoped PR plan. Do not add invasive instrumentation merely to estimate a bill.

## Phase 1 — reduce result rows and selected columns

| Change | Implementation boundary | Required verification |
|---|---|---|
| Bounded homepage federal findings | Summary count/total queries plus four ordered display records; full experience remains paginated | Same visible cards, ordering and aggregate semantics; no full finding collection fetched by homepage |
| County summary queries | SQL aggregates/window or ordered latest-row queries; narrow projections for fields needed by publication rules | Golden comparisons across fiscal periods, missing values, aggregate/component budgets, audit-opinion precedence |
| National money-flow totals | Follow existing SQL aggregate patterns without double-counting budget components | Existing headline values and basis labels preserved |
| Admin statistics | SQL counts/sums instead of full job objects | Same totals, private authorization, bounded responses |
| Freshness lookups | Select dates and required metadata keys; short public cache | Publication date remains distinct from retrieval/ingestion time |
| County findings detail | SQL pagination/filtering; fail closed for unresolved entities | Limit enforced at database; correct totals and status semantics; unknown entity does not widen query |

Keep summary and detail DTOs separate. Do not introduce a small `limit` argument while still loading everything and slicing in Python. Validate row/column selection as well as API output. Reuse existing narrower work discovered in the current tree rather than rebuilding it.

## Phase 2 — prevent repeated cold reads

- Add per-key request coalescing to expensive **public** cache fills; concurrent misses should await one result. Release locks on exceptions, time out boundedly and avoid blocking unrelated keys.
- Preserve the existing memory TTL fallback. A paid Redis dependency is unnecessary for the first improvement.
- Include all meaningful filters in keys. Do not put authenticated admin/account responses in a global public cache.
- Measure warmup benefit, then make it narrower or lazy where appropriate. Do not warm large detail datasets when only compact summaries are needed.
- Review the 1,000–1,100 request worker recycle setting only after confirming runtime memory/restart behavior. Longer worker life can improve cache reuse but may mask a memory leak; it is not an automatic safe toggle.
- Review boot seeding and recurring scheduler ownership together with ingestion owners. Establish one intended source of periodic work without deleting necessary freshness/recovery behavior.

Tests: simultaneous cold callers produce one expensive read; errors release in-flight state; relevant filters are isolated; admin data is never shared; a worker restart recovers normally. Measure deployment/restart egress separately from steady state.

## Phase 3 — make repeated ingestion inexpensive

- Batch distinct source URL lookups per transaction; extend the existing county writer's improvement to remaining confirmed per-record resolvers.
- Use IDs/narrow columns where only identity is required; load mutable provenance once where updates genuinely need it.
- Add a completed-load checkpoint incorporating source fingerprint, parser version, loader version and completeness. “Extraction skipped” alone is not sufficient proof that loading succeeded before.
- When a reload is necessary, batch existing audit identities/comparison hashes instead of fetching full JSON-rich records one at a time.
- Retain partial-failure recovery and intentional reparsing. Do not skip changed or incompletely loaded evidence to hit a cost target.
- Keep normal CI and repeated local test loops on local fixtures/databases. Add explicit safety guards to new diagnostics that might accidentally connect to production. Do not change another running session's settings.

Tests: unchanged second run performs only bounded checkpoint work; changed source/parser/loader forces reload; partial earlier load is repaired; repeated source URLs do not create N queries per record; financial outputs remain identical.

## Phase 4 — add small, useful cost visibility

Use structured logs/metrics already supported by the app. Suggested fields: endpoint/job family, cache hit/miss, result row count, duration, deployment SHA and a non-sensitive client application name. Do not log SQL parameters containing private values, credentials, tokens or full evidence payloads.

Connection labels should distinguish `auditgava-api`, `auditgava-ingestion`, `auditgava-social-worker`, migrations and explicit local diagnostics. Pooler behavior may limit historical attribution; labels improve future evidence, not past reconstruction. Query result byte estimates are diagnostic estimates; reconcile against the provider's actual daily meter.

Budget alerts should be informational with projection and recent change. Do not automatically turn off the website or ingestion when a threshold is crossed. Alert delivery itself requires a separately authorized integration; none was created here.

## Phase 5 — social publishing budget gate

Before enabling a real worker, execute its fake-adapter workload against an isolated test database and characterize empty/active query traffic. Then inspect a bounded production pilot under normal low volume.

- Read [the low-cost operating profile](../../social-publishing/LOW_COST_OPERATING_PROFILE.md).
- Provisional social database-egress budget: <=200 MB/month equivalent at the chosen idle cadence, plus a documented active-volume allowance if measured usage requires it.
- Reject full-table polling, full account/credential reads on every tick and media bytes in PostgreSQL.
- Include expected retention/index growth in the capacity check.
- Delay automated video until a separate storage/download budget is accepted.

If the worker cannot meet its budget, slow idle scans, combine maintenance queries, reduce repeated data selection or add a bounded wake mechanism compatible with the deployed connection mode. Do not weaken final pause checks, approvals or durable delivery records.

## Suggested safe implementation slices

1. Public summary/projection PR with correctness fixtures and row-count evidence.
2. Public cache coalescing PR, independent of role/private-response fixes.
3. Ingestion batch/checkpoint PR, coordinated with current pipeline work.
4. Runtime startup/recycle proposal after measurement; deployment changes require their own review.
5. Bounded metrics and seven-day results report.

Coordinate shared `backend/main.py`, writer files and auth/cache layers before parallel work. They already contain unrelated changes. A future agent should own one slice at a time and keep a before/after evidence record.

## What would change the recommendation?

Consider Pro when a verified necessary workload exceeds Free after fixes, reliability/backup requirements justify it, or storage/connection/compute metrics—not just speculation—show pressure. Consider a different database only if sustained total ownership cost, required capabilities or reliability justify migration. Current data supports optimizing the existing installation first.
