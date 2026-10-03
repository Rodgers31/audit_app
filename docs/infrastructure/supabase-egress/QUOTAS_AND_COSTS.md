# Quotas, cost boundaries and alternatives

Checked against official documentation on **2026-10-03**. These are planning inputs, not a purchase quote. Recheck prices and region/account eligibility before enabling new services.

## Current Supabase allowance

| Resource | Free allowance | AuditGava observation | Design implication |
|---|---:|---:|---|
| Uncached egress | 5 GB per organization/cycle | 6.084 GB | Immediate limiting meter |
| Cached egress | Separate 5 GB allowance | 0 | Not interchangeable with database traffic |
| Database size | 500 MB per project | 0.091 GB summary | Keep concise metadata; monitor growth |
| Object storage | 1 GB | 0 | Video originals can quickly consume this |
| Authentication MAU | 50,000 | 1 | Not the count of anonymous site users |
| Storage upload file size | Free maximum 50 MB | No current uploads | Some videos need smaller exports or another store |

Sources: [Supabase pricing](https://supabase.com/pricing), [billing resources](https://supabase.com/docs/guides/platform/billing-on-supabase), [Storage file limits](https://supabase.com/docs/guides/storage/uploads/file-limits).

Outbound database results count even if they go to AuditGava's backend rather than a browser. Moving the backend to another external host or changing pooled connections to direct connections does not make the results exempt. A closer region can reduce latency; it is not an egress allowance. [Egress troubleshooting](https://supabase.com/docs/guides/troubleshooting/all-about-supabase-egress-a_Sg_e).

Free overages do not automatically become a small per-GB invoice; restrictions are the concern. Pro currently starts at $25/month, with $10 of compute credit covering one default Micro project. Extra projects, larger compute, optional services, taxes and overage can add cost. Do not assume several projects cost the same as one. [Billing FAQ](https://supabase.com/docs/guides/platform/billing-faq).

Supabase Free also has operational limits beyond bandwidth: low-activity projects can be paused, and free backup capabilities differ from paid automatic backups. A reliable always-on publishing service cannot be advertised solely from a free-tier price. Review [project pausing](https://supabase.com/docs/guides/platform/free-project-pausing) and [backups](https://supabase.com/docs/guides/platform/backups) before production commitments. Do not create artificial traffic to evade inactivity policies.

## Proposed incremental cost profile

| Component | Reuse / proposal | Additional recurring cost | Qualification |
|---|---|---:|---|
| Database and admin auth | Existing Supabase | $0 while within allowance | Optimize existing reads first; social data consumes headroom |
| FastAPI / frontend | Existing deployment | Potentially $0 | Capacity and actual hosting allowance must support added work |
| Social worker | Small dedicated Python process | $0 only on already paid, adequate always-on compute | A new hosted worker may have a charge; do not assume an existing web plan includes it |
| Queue | Existing PostgreSQL | No separate queue bill | Compact indexed claims; no Redis requirement |
| Media, initial images | Existing object-store abstraction; choose actual backend before implementation | May fit free allowances | The observed Supabase Storage is unused, so a bucket/permission model is not already proven |
| Video media | Optional Cloudflare R2 Standard | Can fit free tier; usage beyond it is metered | Separate object store, not a database migration |
| AI copy/video voices | Templates first; optional provider later | $0 for deterministic copy; provider usage varies | “Open source orchestration” does not make model generation free |
| Facebook / Instagram / Threads | Official eligible APIs | No publishing subscription assumed | App access/review, account permissions and operation are still work |
| X | Official paid usage | Separate mandatory API budget for enabled use | See current platform pricing in social blueprint; zero-cost fallback is manual export |
| TikTok | Eligible approved API route | No blanket fee assumption | Approval/owned-account eligibility is the main unresolved gate; review current terms |

The worker's hosting and X fees are separate from Supabase capacity. The objective is minimal incremental cost, not a promise that a reliable five-platform service will have no bill under every hosting arrangement.

## Media-only alternative: R2

R2 Standard currently includes **10 GB-month storage, one million Class A operations and ten million Class B operations monthly**, with internet egress free. Beyond allowance, Standard storage is $0.015/GB-month, Class A $4.50/million and Class B $0.36/million. Other Cloudflare services and account requirements are separate. [Official R2 pricing](https://developers.cloudflare.com/r2/pricing/).

Use the existing S3-compatible storage boundary rather than migrating application data. Keep social assets private; issue scoped, sufficiently long-lived HTTPS delivery URLs compatible with each provider's processing window and TikTok domain requirements. Preview access, deletion, checksums and retention still need implementation. Confirm account activation/payment requirements and cost controls before creating resources. Nothing was provisioned in this task.

## Database alternatives

| Option | Benefit | Why it is not the present recommendation |
|---|---|---|
| Keep Supabase Free and optimize | No migration; auth/database remain integrated | Requires real usage to return within quotas; no guaranteed Oct 8 relief |
| Supabase Pro | Same application architecture, larger allowances, paid operational capabilities | Recurring base cost; unnecessary solely for current 91 MB storage |
| Move to another hosted PostgreSQL free tier | Potentially different quotas | Migration plus auth/storage integration and another provider's limits; overfetch remains |
| Self-host PostgreSQL on existing server | Control over database and network budget | Backups, patching, recovery, monitoring and resource contention become ours; not operationally free |
| SQLite | Simple for some local/small applications | Poor fit for the current distributed PostgreSQL/Supabase app and multi-worker design |
| Add paid Redis to avoid reads | Shared cache across replicas | Existing memory cache works; broad result selection and repeated ingestion should be fixed first |

No new database vendor comparison is needed to justify an immediate migration: the measured bottleneck is avoidable repeated outbound query data. Revisit alternatives only after a measured optimized baseline, hosting review and total ownership comparison.
