# Supabase egress investigation

**Investigated 2026-10-03. Recommendation: keep Supabase; reduce unnecessary database reads before considering a migration or paid cache.**

This was a read-only investigation plus documentation. No queries, cache settings, ingestion schedules, running processes, environment variables, billing settings or database objects were changed. The social publishing infrastructure is still a design.

## What the warning means

The project is exceeding its **outbound data allowance**, not running out of database storage. A 90 MB database can generate gigabytes of egress when its records are repeatedly downloaded by the backend, ingestion jobs or development tools.

| Observation | Verified value | Meaning |
|---|---:|---|
| Current billing cycle | 23 Sep–23 Oct 2026 | Monthly accumulated usage |
| Current uncached egress | 6.084 / 5 GB, 122% | Already 1.084 GB over allowance |
| Previous-cycle egress | 7.681 GB | This is not just a first isolated overage |
| Dominant current-cycle source | Shared Pooler, daily tooltips round to 100.0% | PostgreSQL query results sent through Supavisor |
| Database size, dashboard summary | 0.091 / 0.5 GB, 18% | Substantial storage headroom today |
| Object Storage / cached egress | 0 / 0 | Images/video storage is not the current cause |
| Realtime / Edge Functions | 0 / 0 | Not the current cause |
| Authentication MAU | 1 | Does not count anonymous visitors or backend jobs |
| Grace deadline | 8 Oct 2026 | Dashboard warns that restrictions may start then |

The project filter confirms that `audit_gava` accounts for the displayed egress. A very small amount of Auth/PostgREST traffic exists, so “100%” is dashboard rounding, not literally zero other traffic. See [the evidence record](EVIDENCE.md).

Supabase counts outbound query results even when the Python backend later reduces them to a tiny API response. PostgreSQL's reported 100% buffer-cache hit rate concerns memory versus disk reads, not whether results crossed the network. The separate cached-egress allowance is not a pool of free capacity that database query traffic can use. [Official egress accounting](https://supabase.com/docs/guides/platform/manage-your-usage/egress), [billing FAQ](https://supabase.com/docs/guides/platform/billing-faq).

## What is causing it

**Confirmed transfer path:** database clients using the shared pooler. **Confirmed repeated large query patterns:** the Query Performance report contains SELECTs returning hundreds of thousands of cumulative rows, including full audit/provenance and budget records. The statistics reset on 22 April 2026; these counters span much longer than the current billing cycle. They identify real workloads, not each workload's share of this month's bill.

The [source audit](CODE_AUDIT.md) traced several avoidable patterns:

1. The homepage fetches the full federal findings collection, then displays four findings. Cache misses still download the full collection from PostgreSQL.
2. County summaries load complete audit, budget and loan rows to calculate small totals. JSON provenance and other large fields travel even when the caller needs a few values.
3. Startup warms 24 endpoints. The production Docker command recycles workers after roughly 1,000–1,100 requests; each replacement loses its process-local cache. Actual deployed restart frequency still needs measurement.
4. Source-document resolvers repeat full-row lookups for the same URLs. Some county ingestion work already has batching improvements; these must be preserved.
5. Audit ingestion skips unchanged extraction but can still reload extraction JSON and existing findings. A versioned, completed-load checkpoint could avoid this repeat work safely.
6. Smaller opportunities include admin statistics computed from full job rows, freshness lookups, and a county findings route that paginates after loading records.

Existing in-memory caching **does work without Redis**. The recommendation is to improve query shape and cache reuse, not purchase Redis. Indices alone do not reduce selected bytes; response compression after the database query does not undo database egress.

The dashboard does not yet distinguish how much came from the deployed API, CI ingestion, local development, SQL tools or another client. It would be incorrect to blame one active session or claim that a particular query caused a precise percentage. No other workstream was stopped or reconfigured to investigate this.

## Can we stay on Free?

It is plausible at AuditGava's present small data size and modest publishing volume, but **not established until optimized usage is measured**. On Sep 23–25, daily pooler transfer was around 98–110 MB. More recent days were much higher, including 1.612 GB on the partial Oct 3 chart. The current trajectory exceeds a 5 GB monthly budget by a wide margin; the full-day early values show that lower usage has occurred, not that any proposed fix has guaranteed savings.

Adopt a planning target of **120 MB/day total uncached egress**, approximately 3.6 GB over 30 days, leaving headroom within 5 GB. Use provider dashboard units and real billing-cycle duration when evaluating the quota. Diagnose spikes separately from averages. The acceptance test is a representative seven-day window under the target, including normal ingestion and a deployment—not simply a smaller browser response.

Prioritize narrow SQL projections/aggregates, bounded homepage summaries, cache single-flight, and repeated ingestion reads. Then evaluate startup/recycling changes from runtime measurements. See [the staged remediation plan](REMEDIATION_PLAN.md).

## Will social publishing make it worse?

All new work consumes some capacity. A small queue of post text, approved revisions, account IDs and delivery receipts fits PostgreSQL well. A worker that continually downloads all drafts or large media manifests would waste bandwidth; that design is explicitly rejected.

The [low-cost social profile](../../social-publishing/LOW_COST_OPERATING_PROFILE.md) requires indexed, bounded claims; only loading a target payload after it is claimed; adaptive idle polling; minimal heartbeats; paginated admin summaries; and no image/video bytes in PostgreSQL. Its provisional incremental database-egress budget is 200 MB/month, to be tested rather than promised.

**Media is the larger future risk.** For illustration, a 50 MB video downloaded once by each of three platforms for 30 posts is 4.5 GB of transfer before previews and retries. This is a workload estimate, not a forecast or a claim that every provider downloads exactly once. Keep Supabase for the database/auth. For substantial video, evaluate an S3-compatible media store such as Cloudflare R2 separately; this does not require migrating the database. R2's current Standard allowance includes 10 GB-month and free outbound transfer, with metered storage/operations beyond allowances. [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

Database size must still be monitored: immutable revisions, receipts, indexes and provenance grow. Keep facts concise, impose log retention and bound retries. Do not retain duplicated raw reports or full API responses indefinitely. Current observations support suitability for an initial small publishing workload, not a guarantee of unlimited capacity or a production load test.

## The immediate Oct 8 issue

**Reducing future traffic cannot erase the 6.084 GB already counted.** The current allowance resets on Oct 23, after the displayed Oct 8 grace deadline. Optimization alone therefore cannot guarantee uninterrupted service during that gap. Supabase documents quota-reset recovery and immediate recovery through upgrading; it does not promise a new grace period for repeat overages. Pausing or deleting a project does not remove accrued usage. [Official restriction policy](https://supabase.com/docs/guides/platform/billing-faq#fair-use-policy).

The cost-conscious next steps are to implement the narrow fixes in a separate approved coding task and seek clarification from Supabase support about the specific Oct 8 restriction. A discretionary extension is not guaranteed. If uninterrupted service becomes essential and support does not offer relief, the documented paid fallback is Pro, currently starting at $25/month for an organization with one default Micro project. No upgrade, support message or billing change was made during this investigation.

## Reading order and handoff

1. [Evidence](EVIDENCE.md): measurements, dates, scope and uncertainty.
2. [Code audit](CODE_AUDIT.md): exact implementation paths and correctness constraints.
3. [Remediation plan](REMEDIATION_PLAN.md): isolated changes and acceptance tests for a later task.
4. [Quotas and costs](QUOTAS_AND_COSTS.md): current allowances and alternatives.
5. [Social design](../../social-publishing/README.md): shared database design and low-cost amendment.

Before changing code, re-read the current tree: other agents are actively improving it. Historical query shapes can outlive the implementation that produced them. Do not reset query statistics or remove financial publication checks to make bandwidth figures look better.
