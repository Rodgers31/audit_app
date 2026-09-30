# County stock and health-signal selection (#388, #391)

This changes evidence selection, not the site's component weights, grade bands,
absorption formula, revenue formula or numerical severity mapping. It performs
no data updates. These are site methodology choices, not an OAG rating or opinion.

## Pending balances

All public county readers select the latest declared valid CoB year-end as-at
**date across county observations**, including observations whose amount is
absent/invalid. A county with only an older observation is absent at that common
date; the older balance is never silently revived. Stored history remains intact.
A direct single-county helper without a supplied common date selects that
county's latest day; public routes first determine/filter the common date.

At that date, one county balance is a stock, not a sum. Identical evidence is
idempotent. Different amount, document, URL, fiscal year, table/page, publication
batch, currency or reader qualification is an explicit same-date conflict,
withheld rather than resolved by ID or ingestion timestamp. Lender labels alone
cannot establish non-overlapping accounting components, so separately labelled
salary and whole-county balances are not automatically additive.

A finite, non-negative KES observation can be published; a measured zero is
retained. Missing/invalid amounts and incompatible currencies remain absent.
`pending_bills_selection` states the common reporting day, reason and sources;
`pending_bills_absence` retains its existing narrower meaning: an explanation
actually supplied by the report. Selection absence is not attributed to CoB.
Source identity, page/table, batch, fiscal year and reader qualifications travel
with the selected value. Conflict citations are capped at 20 with explicit count
and truncation fields.

The pending summary/debt ranking applies this selector per county **at the
common day**, never mixes latest-per-county dates. `reported_county_sum` is an
available-observation sum. A complete county total still requires all 47 official
county identities from one document/URL/date/batch and no qualified county.
Missing latest counties, mixed editions and qualified observations withhold the
complete county and combined totals. Empty responses retain coverage/conflicts.

The pending/budget ratio and index component require a KES annual budget whose
period starts 1 July, ends 30 June, and agrees with both the stock's as-at date and
its fiscal-year declaration. Incompatible ratios are withheld; the stock stays
visible. The final `publish_county_budget` response formatter enforces this too.

## Severity-derived audit signal

The public SQL publication predicate and existing display-grade provenance gate
remain prerequisites. Selection reads metadata in batches, rather than finding
text or a source lookup for each finding. Institutional identity uses the shared
`audited_institution` resolver. Historic string-encoded extraction payloads use
the existing explicit serialized-payload fallback, so they cannot bypass a
period conflict merely because the object projection is null.

Only explicit County Executive evidence is scored. Unambiguously Assembly
findings are excluded before checking their periods; they remain displayed as
findings and their excluded count is disclosed. Missing/conflicting identity
at a dated period makes that period unavailable rather than guessing its scope.

An eligible period has an annual Kenya FY label consistent with 1 July/30 June
stored dates and any declared extraction/provenance/source fiscal year. Missing
or unparseable periods are excluded and counted because chronology cannot be
established. When a label identifies a later FY but its dates or declarations
conflict, that latest period is withheld without fallback to an older period.

Select the newest Executive FY, then the **maximum finding severity across all
eligible Executive findings and documents in that FY**. Multiple findings,
repeated identical ingestion and severity ties cannot change the signal through
insertion order. Multiple cited documents/pages are retained deterministically;
20 citations are returned at most, with source count/truncation disclosed.
No ingestion timestamp or auto-increment ID ranks evidence.

For compatibility, the component/API's legacy `audit_opinion` and
clean/qualified/adverse names remain, using the existing 100/60/20 mapping.
`audit_signal.measurement_basis = finding_severity`, `official_opinion = false`,
selection policy, institution, selected FY, citations (including withheld
period/scope conflicts), excluded counts and
absence reason make that meaning explicit. The list/detail `last_audit_date`
now uses the selected valid fiscal-year end and declares `audited_period_end`
as its basis; unavailable signals have no fabricated audit date. The methodology catalog explains the
new rule in EN/SW/plain; fluent Swahili review remains under #307.

## Execution and public evidence

Runtime tests persist synthetic evidence and call the actual list, detail,
comprehensive, county pending and pending summary endpoints. They cover old/new
stocks, duplicates/conflicts, incomplete latest coverage, zero/absence, source
qualifications, period/currency mismatches, reversed audit ingestion, older
backfill, multiple findings, Assembly/Executive conflicts, ambiguous periods,
serialized extraction parity and metadata/query/payload bounds. Map and compare
use the same `/counties` reader; no separate map/compare calculation was changed.
Writer controls still execute the existing pending-bill parser/writer and
population/edition completeness gates.

Receipts and exact commands are recorded in the Session 2 handoff. The SQLite
and disposable PostgreSQL runs are synthetic correctness controls, not evidence
that an official source figure is accurate. An isolated mutation run restoring
the old algorithms makes the stock and audit-order regressions fail.

Read-only public API snapshot (30 September 2026): 47 counties; pending summary
reports 46 counties and KES 172,526,690,000 at 30 June 2026, with the complete
county/combined total absent. These are API observations, not independent PDF
verification. Mombasa currently scores 57.5 using a FY2023/24 derived qualified
signal. Joining the complete public 61-finding audit page to the comprehensive
response by finding ID previews selection of 17 Executive findings in FY2024/25,
whose maximum severity is warning; the previewed score remains 57.5. This preview
cannot inspect stored period dates or additional extraction conflicts. It is not
a production DB re-execution or a measurement of impact across all counties.
No production snapshot-coexistence prevalence is claimed.

## Release and rollback

Before rollout, the coordinator should run a bounded metadata inventory against
live rows, compare old/new selectors and all affected county scores/absence
reasons, and review latest-date incomplete coverage and competing same-date
sources. If a live DB connection is supplied, begin `READ ONLY`, verify
`transaction_read_only = on`, set a short local statement timeout, bound output,
and roll back. Do not silently clear conflicts or modify stored evidence.

Deploy only after that inventory and normal consolidation review. Invalidate
county list/detail/comprehensive and pending summary/county/debt caches so old
and new methodology responses do not coexist. No migration or reseed is needed.
Rollback is a code revert plus the same cache invalidation. No stored balances
or audit records require restoration. Keep #388/#391 open until rollout and
public verification; committed code alone does not satisfy closure.
