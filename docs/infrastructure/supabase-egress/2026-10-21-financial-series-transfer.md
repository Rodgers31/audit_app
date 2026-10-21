# Financial-series transfer reduction

Observed 21 October 2026 UTC (20 October Chicago), against accepted main
`a62ec1d92c0fe083efff221534939a87f610399d` and existing backend `e26d142`.
Tracks #481; operating acceptance remains under #699.

## Verified overfetch and change

`entity_financial_series` joined complete BudgetLine, FiscalPeriod and
SourceDocument models for each matching budget line. Document file paths,
unconsumed metadata, row notes and other unused columns crossed the database
connection even when a caller needed only the dated financial summaries. This
function serves entity list/detail and county comprehensive history.

The replacement projects the consumed accounting, period and citation fields,
plus the three source metadata members used by the existing negative evidence
filter: `data_quality`, `dataset_id`, and `source`. JSON types are preserved.
Summary-only plain objects avoid modifying ORM relationship/identity-map state.
All matching rows and one SQL statement/snapshot are retained. Aggregation,
source/period conflicts, duplicate classification, unknown versus zero, and
modelled/projected refusals are unchanged. There is no cache, TTL, ingestion,
schema, authentication, configuration or activation change.

The regression was executed against the original query first: ten transfer
guards failed while complete output comparisons passed. Eight fixture budget
rows sharing 64 KiB unused document metadata, paths and notes select
**1,575,760 → 1,512 UTF-8 value bytes** in the official-quality case. The other
nine metadata cases preserve complete outputs and also pass the transfer bound.
These are deliberately enlarged fixtures, excluding protocol, TLS, pooler and
provider accounting; they do not establish the percentage of today's bill saved.

The affected author suite passes **271 tests**, including county HTTP/evidence,
financial accounting/adversarial and budget qualification cases. Independent
executable reviews, including PostgreSQL JSONB behavior, are recorded in the
coordinator's B31 evidence packet. Exact review results accompany the PR.

## Current production attribution boundary

Chrome's existing Supabase Query Performance page exposes a compatible legacy
joined financial-series shape at 1,759 calls / 94,386 returned rows. Those are
cumulative counters, with entry age beginning 27 September, not today's calls or
bytes and not exclusive caller attribution.

Two separately reviewed, bounded read-only metadata snapshots on the accepted
backend at **04:05:17.857615 and 04:07:03.261523 UTC** cover the 50 matching
audit/budget/document/extraction SELECT shapes with the highest historical
returned-row counts. All 50 identities and entry ages match; none increased in
that 105-second interval. Global reset remained 22 April and deallocation
counter 15. The diagnostic transfers at most 50 query prefixes of 4,096
characters, exports only shape indicators/hashes and aggregate counters, rolls
back and closes. No statistics reset or application data write occurred.

This short quiet interval cannot attribute the organization's current daily
Shared Pooler usage, prove all clients idle, or qualify the future worker and
nightly workload. The prior B30 dashboard's 41.044/250 GB current-cycle value
and rounded daily labels remain historical observations; they are not refreshed
or converted into measured savings by this patch. The existing Pro spend cap,
disabled Actions, and publishing/uploads/worker OFF settings are preserved.

## Storage accounting remains a separate measurement

The media bucket dashboard still reports 304 B. Its two retained test objects
each show 77 B; the reviewed S3 inventory accounts for 154 payload bytes and
70 custom-metadata key/value bytes. The remaining **80 B is not yet explained**.
No missing object, application ledger defect, or safe quota release follows
from that difference. Cloudflare documents separate `payloadSize` and
`metadataSize` metrics; the dashboard's combined display and S3 HEAD responses
do not establish the provider's complete metadata representation.

An unissued, account-scoped **Account Analytics: Read** token request is prepared
to obtain that breakdown through the official GraphQL Analytics API. Issuance
requires separate owner confirmation because it creates access. It adds no
resource or paid plan; any approved credential is to be revoked after the
bounded read, without changing the existing storage credential. No new token,
storage write, deletion, quota release or paid instrumentation has occurred.

## Rollout and remaining acceptance

After review/merge authorization, deploy through the existing service and verify
the accepted source, OFF flags, unchanged schema and complete representative
responses. Revert this query-only change if any output/refusal regresses.

#481 and #699 stay open for deployed verification, current workload attribution,
the storage breakdown, and the existing complete representative operating packet.
No Free downgrade or assertion of full operating acceptance is supported here.
