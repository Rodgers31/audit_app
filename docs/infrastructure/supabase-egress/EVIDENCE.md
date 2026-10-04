# Egress evidence record

Investigation date: **2026-10-03**, approximately 18:00–19:05 UTC. Dashboard counters may lag and were observed at different moments. This is a record of observations, not continuous monitoring.

## Sources and method

- User-provided Supabase Usage screenshot, showing the Auditors Free organization and current-cycle warning.
- Logged-in Chrome dashboard, read-only navigation in separate research tabs: [organization usage](https://supabase.com/dashboard/org/hdyktpafltykrgpkcvgt/usage) and [project Query Performance](https://supabase.com/dashboard/project/xznjxwrkbkahwtnbstbj/observability/query-performance). These links require appropriate access. Project identifiers are not credentials.
- Small server-side read-only PostgreSQL metadata/aggregate SELECTs through the already configured project connection. Connection target was checked against the dashboard project before connecting; credentials were never printed or copied into documentation.
- Current working-tree code inspection, baseline HEAD `629a5bdac87e75d00b5132957a389e966045e6fa`, branch `feat/external-debt-by-creditor`, with pre-existing unrelated modifications. This is not a guarantee of the production deployment's commit.

The SQL session used `default_transaction_read_only=on`, a 5-second statement timeout and 1-second lock timeout. No application imports, data export, schema changes, writes, `EXPLAIN ANALYZE`, statistics reset or vacuum were performed. Samples returned only aggregate lengths, never row contents. The diagnostic connection itself generated a small amount of normal egress; no claim of zero-cost measurement is made.

## Usage summary

| Meter | Displayed value |
|---|---|
| Organization | Auditors, Free |
| Project | audit_gava |
| Current billing interval | 23 Sep 2026–23 Oct 2026 |
| Uncached egress | 6.084 / 5 GB, 122% |
| Previous billing cycle, filter selected | 7.681 GB |
| Cached egress | 0 / 5 GB |
| Database size, summary | 0.091 / 0.5 GB, 18% |
| Database size, detail chart | 86.47 MB |
| Storage | 0 / 1 GB |
| Authentication MAU | 1 / 50,000 |
| Third-party MAU | 0 / 50,000 |
| Realtime peak connections / messages | 0 / 0 |
| Edge Function invocations | 0 |
| Log ingestion, labelled upcoming | 0.008 / 1 GB |
| Log query, labelled upcoming | 0.419 / 100 GB |
| Grace deadline | 8 Oct 2026 |

The previous-cycle filter changed the egress total but the page header continued to show the current billing dates. Consequently this record calls it “previous cycle” without asserting unverified start/end dates. Current-project filtering retained 6.084 GB, locating the displayed organization usage in AuditGava.

The database summary/detail and SQL database-size readings are different observations and potentially different scopes/units. Do not add them or treat their difference as unexplained data growth. Each shows storage far below the displayed 0.5 GB quota.

## Daily egress tooltip observations

All eleven daily tooltips showed Shared Pooler as **100.0% when rounded**. Values below preserve the dashboard's MB/GB formatting; do not sum rounded mixed-unit labels to reconcile the precise total.

| Day | Shared Pooler | Other visible traffic |
|---|---:|---|
| Sep 23 | 107.040 MB | None shown |
| Sep 24 | 109.788 MB | None shown |
| Sep 25 | 97.511 MB | None shown |
| Sep 26 | 269.407 MB | None shown |
| Sep 27 | 480.410 MB | None shown |
| Sep 28 | 452.635 MB | Auth 137.112 KB; PostgREST 79.991 KB |
| Sep 29 | 428.109 MB | PostgREST 199.659 KB |
| Sep 30 | 260.979 MB | None shown |
| Oct 1 | 1.107 GB | None shown |
| Oct 2 | 811.946 MB | None shown |
| Oct 3 | 1.612 GB | Partial day |

These values establish the outgoing database-client path and recent acceleration. They do not identify a particular API instance, person, development agent or scheduled run. Supabase's official definition identifies Shared Pooler as Supavisor traffic and says the database-to-pooler leg is not counted again as duplicate database egress. [Egress guide](https://supabase.com/docs/guides/platform/manage-your-usage/egress).

## Query Performance observations

The report displayed 317 slow-query entries, 100% database cache hit rate and an average 74.4 rows per call. These are database execution metrics, not HTTP traffic counts or transfer bytes.

**Verified `pg_stat_statements_info.stats_reset`: 2026-04-22 20:29:28.245625 UTC.** Statistics can also be affected by entry eviction and individual resets; no claim is made that every entry covers every query since that instant. They are not limited to Sep 23–Oct 3. The following SELECT shapes were visible in the report:

| Normalized query description | Calls | Rows returned | Approx. mean execution |
|---|---:|---:|---:|
| Full BudgetLine rows for 47 entities and selected period | 1,918 | 1,052,350 | 32 ms |
| Full county Audit rows, one publishability-filter variant | 1,227 | 870,067 | 27 ms |
| Full county Audit rows, variant with page-reference gate | 336 | 503,328 | 169 ms |
| Narrower county Audit projection still containing provenance | 69 | 332,996 | 910 ms |
| Full federal Audit + Entity join | 334 | 271,542 | 198 ms |
| Latest budget-period aggregate for county entities | 906 | 172,772 | Not recorded |
| Full SourceDocument WHERE URL equals parameter | 109,449 | 109,438 | 1 ms |
| Narrower federal Audit + entity-name/type projection | 69 | 56,097 | Not recorded |

The presence of narrower and older full-row shapes together is consistent with code evolving over the cumulative measurement period. Their exact deployment dates were not verified. Query normalization does not reveal which of several callers emitted an identical SELECT. The application column was not useful for per-client attribution.

The high `pgbouncer.get_auth` count (approximately 899,000) is internal pooler authentication work. It must not be reported as website users, application publications, or that many complete dataset downloads. Queries with high execution time but few returned bytes can be CPU concerns without being egress priorities.

## Read-only SQL metadata

At **2026-10-03 18:59:37 UTC**, `pg_database_size(current_database())` returned **75,394,195 bytes**. Server postmaster start time was **2026-04-22 20:30:55 UTC**. These do not measure peak load or establish an SLA.

Largest observed public relations, using `pg_total_relation_size` and approximate live/dead tuple statistics:

| Relation | Approx. live rows | Approx. dead rows | Total relation bytes |
|---|---:|---:|---:|
| audits | 8,920 | 1,667 | 24,330,240 |
| extractions | 8,949 | 4 | 18,063,360 |
| imf_weo_observations | 34,780 | 0 | 6,725,632 |
| budget_lines | 2,605 | 121 | 4,743,168 |
| source_documents | 2,442 | 472 | 2,359,296 |
| ingestion_jobs | 3,202 | 74 | 1,359,872 |
| entities | 125 | 0 | 507,904 |
| economic_indicators | 325 | 3 | 458,752 |
| parliament_source_documents | 497 | 0 | 442,368 |
| loans | 100 | 47 | 360,448 |
| population_data | 64 | 0 | 237,568 |
| fiscal_summaries | 29 | 0 | 229,376 |

Dead-row estimates do not justify manual `VACUUM FULL` or other disruptive maintenance. This task performed none. Large JSON-heavy audit/extraction tables reinforce the value of selecting only required columns.

### Bounded row-width samples

Each sample selected the first 200 rows ordered by ID and aggregated JSON serialization length inside PostgreSQL. This is a deliberately bounded, **non-random sample**. JSON serialization length is a rough payload indicator, not PostgreSQL wire size, compressed storage size or a historical billing meter.

| Sample | Rows | Mean full-row JSON bytes | Max full-row JSON bytes | Mean provenance/metadata bytes |
|---|---:|---:|---:|---:|
| audits | 200 | 2,255 | 16,560 | 627 provenance |
| budget_lines | 200 | 1,754 | 1,765 | 1,140 provenance |
| source_documents | 200 | 821 | 1,137 | 214 metadata |

Sample form, for future reproducibility after explicit target verification:

```sql
SELECT count(*),
       round(avg(octet_length(row_to_json(s)::text))),
       max(octet_length(row_to_json(s)::text)),
       round(avg(octet_length(coalesce(s.provenance::text, ''))))
FROM (SELECT * FROM public.audits ORDER BY id LIMIT 200) AS s;
```

Do not multiply these biased current samples by six months of counters and call the result this month's actual egress. They show why selecting provenance unnecessarily can be expensive.

A one-time grouped `pg_stat_activity` snapshot showed seven current-database entries, principally Supabase services and one idle unset application. Pooler backend entries are not a count of every connected pooler client or historical consumer. This snapshot cannot identify the source of the spike or prove resource headroom under load.

## Evidence still needed for exact attribution

- Deployed backend command/replica count, deployment/recycle timestamps and cache hit/miss rates.
- Bounded query-counter deltas around routine ingestion versus ordinary API traffic.
- Client-specific `application_name` in a future controlled instrumentation change.
- Before/after daily Shared Pooler transfer for each isolated optimization.
- A representative load check for new social work after implementation; this investigation did not benchmark production.

Record these gaps explicitly rather than inventing a percentage split between users, robots, development and ETL.
