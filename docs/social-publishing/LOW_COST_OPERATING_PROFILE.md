# Low-cost operating profile

**Normative design amendment, 2026-10-03. No implementation was performed.** Apply this alongside the [engineering blueprint](ENGINEERING_BLUEPRINT.md). Where an earlier diagram implies constant five-second full scans or unlimited free media hosting, this document supersedes that assumption.

The [Supabase investigation](../infrastructure/supabase-egress/README.md) found current egress dominated by shared-pooler database traffic, while database storage remains small. Keep Supabase as the authoritative relational database/auth provider. Do not introduce a second database, Redis, Celery or a Node Social SDK service merely to schedule a few daily publications.

## Worker contract

| Parameter | Initial proposal | Reason |
|---|---|---|
| Processes | One dedicated worker | Predictable ownership; claiming remains safe if later scaled |
| DB pool | Two connections, bounded overflow disabled | Avoid excessive idle connections; total application pools still need sizing |
| Outbound concurrency | Two, maximum one mutating operation per account | Low-volume reliability and controllable platform limits |
| Busy scan | Up to every 5 seconds | Responsive dispatch while real work is active |
| Idle scan | Back off to 30 seconds | Reduce empty round trips |
| Known scheduled work | Wake at the earlier of next scan or known due time | Avoid unnecessary delay for a known schedule |
| Heartbeat | Every 60 seconds while idle | Minimal operational visibility; UI shows freshness threshold |
| Lease renewal | Blueprint's active lease interval, independent of idle heartbeat | Active work must not lose its lease due to backoff |
| First dispatch of newly created work | Up to 30 seconds idle wait, plus validation/provider time | An honest initial latency contract, not an instant-post promise |

This is an initial tuning profile, subject to measurements. The API commits due work atomically but cannot wake an unrelated idle process just by updating an in-memory variable. A later best-effort wake mechanism may reduce latency, but durable polling must remain the fallback. Do not assume PostgreSQL LISTEN works reliably over a transaction-pooled client connection without designing a compatible dedicated/session path.

Each claim selects only due target IDs and lease/version fields, uses a partial due-work index and an atomic lock/claim transaction, then loads that target's immutable payload. Never scan all draft bodies, evidence JSON, media manifests or credential records per tick. Use the database clock for lease/due comparisons. Keep database transactions short; never hold a row lock during an external upload/API call.

Idle maintenance combines bounded small checks. Credentials are loaded when needed and refreshed under a versioned lock; non-sensitive capability metadata can be cached. Heartbeat writes return minimal acknowledgement, not `RETURNING *` for a JSON record. Reuse connections rather than establishing one for each scan.

**Safety remains authoritative:** immediately before each new external mutation, verify global/account publishing controls, approved immutable revision, source freshness, account health, cancellation state and a current dispatch permit. Do not replace these final checks with a long-lived cached permission to publish. Pausing stops new dispatch permits; already accepted/in-flight remote requests can still complete. Reconciliation/status reads may continue while paused.

## Egress and storage budgets

- Initial planning budget for social database traffic: **<=200 MB/month equivalent** at low volume, measured before production acceptance. This is not a current benchmark.
- Overall project operating target: approximately **120 MB/day** total uncached egress, giving headroom below 5 GB over a normal cycle. Existing public/ETL traffic must be optimized first.
- Thirty days of five-second scanning produces 518,400 polls; thirty-second scanning produces 86,400. If an empty exchange hypothetically cost 1 KB, that would be about 518 MB versus 86 MB before other activity. The 1 KB value is illustrative, not measured PostgreSQL protocol traffic.
- Model metadata growth explicitly. At an assumed 100 KB per master post across its revisions, five targets, receipts and audit entries, 90 posts/month adds roughly 9 MB/month or 108 MB/year before additional index/retention effects. Actual content and revision counts may differ substantially.
- Start with bounded payload fields and sanitized error summaries. Do not persist raw API responses, tokens, prompts, full PDFs, chart binaries or videos in every attempt/event.
- Suggested retention for implementation review: verbose operational logs 30 days; sanitized failed-attempt diagnostics 90 days; temporary uploads seven days if unattached; keep compact approval/provenance/publication records according to an explicit accountability policy. Do not silently delete evidence or published media to meet storage targets.

Admin list APIs return bounded summaries, not every revision/attempt/source body. Fetch evidence and large errors on demand. Poll only active delivery views at a bounded cadence; stop when hidden. History and media libraries are paginated. Source-event generation uses changed IDs and semantic fingerprints, not a full audit/extraction scan every scheduler tick.

## Media boundary

PostgreSQL stores asset identity, object key, hash, MIME, dimensions, duration, byte size, state and accessibility metadata. Object storage holds bytes. One immutable original can have reusable derivatives, not five uploaded copies merely because five platforms are selected.

Supabase Storage can be appropriate for small initial images if its quota fits. Its currently unused bucket space is not proof that the app has a complete safe upload/permission workflow. For video, prefer evaluating an optional S3-compatible R2 bucket while retaining Supabase database/auth. Existing optional S3/boto3 document-storage code provides reusable patterns; a complete social media storage adapter is still future work.

Example: 50 MB × three provider downloads × 30 videos = **4.5 GB/month** before admin previews, processing retries and duplicate renders. Providers may download more than once. Supabase's cached allowance cannot be assumed for authenticated/signed/provider fetches. Measure the actual path. R2 currently offers free outbound transfer and a Standard free allowance; storage/operations above it and other services can still cost money. [Official pricing](https://developers.cloudflare.com/r2/pricing/).

Initially warn/block incompatible media; add deterministic Pillow/FFmpeg derivatives later. Avoid rendering video in the API request or loading entire videos into memory on the small API host. A separate bounded render job uses temporary files and object storage. Do not add a permanent renderer process until volume warrants it.

## Hosting and cost gates

A dedicated process does not necessarily require a new vendor, but it does require reliable compute. If existing hosting cannot run a separate always-on worker, a new worker service may cost money. Do not put schedulers in every web replica or rely on a sleeping/free web process for on-time publication. Validate the actual hosting plan before promising zero incremental infrastructure cost.

Free Python libraries and official APIs avoid a social scheduling SaaS subscription. They do not eliminate X's current API usage charges or TikTok/Meta app-review restrictions. Provide an explicit manual export fallback for any destination whose cost or eligibility is not accepted; do not scrape browser sessions as an API substitute.

## Acceptance before enabling publishing

1. Fake-adapter tests establish durability, independent target results, unknown-outcome reconciliation and pause behavior.
2. Empty/busy worker query traffic and metadata growth are measured on isolated fixtures.
3. A bounded pilot stays within the documented budget, or the budget/topology is openly revised.
4. Hosting ownership, token encryption/rotation, alerts, recovery and media retention are assigned.
5. Generated content still requires human approval; automatic approval/publishing policy stays off.

No cost optimization may bypass approval, replay an ambiguous remote mutation blindly, republish successful destinations after a partial failure, or disclose credentials to the browser.
