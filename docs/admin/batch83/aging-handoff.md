# B83 pending-bills aging handoff

Base: `7c7b309158480e61206a453e7d844fcf5075b3b9`. Branch: `codex/b83-aging`.
This author change is draft-only. No production configuration, financial rows,
workflow, migration, admission SHA, publication or provider setting was changed.

## Supported source and limits

The official [CoB full-year 2025/26 report](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482)
was freshly downloaded on 25 October 2026: HTTP 200, no redirect,
53,561,130 bytes, 935 PDF pages, SHA-256
`919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20`.
The cover identifies the Office of the Controller of Budget, the financial year
2025/26 and August 2026. The landing page reports creation 25 September and
update 7 October 2026; these are distinct from the 30 June 2026 stock date.

This artifact differs from the retained fixture's
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
All five retained raw table extractions on PDF pp.51–53 match the fresh bytes'
extractions exactly. The previous full PDF was unavailable, so the complete
byte-level cause of the reissue is not established. The adapter admits only the
newly inspected digest; another artifact at the same URL is refused.

Table 2.11 spans PDF pp.53–54 (printed pp.19–20), KES millions, county executives
only. Its publisher bands are Under one year / 1–2 years / 2–3 years / Over 3
years. The reported source summary is KES 44,208,110,000 / 28,834,120,000 /
22,241,100,000 / 70,235,180,000, totalling KES 165,518,510,000. These are reported
executive observations, not a complete or combined government liability total.
The independently read Table 2.10 executive amount is KES 166,151,340,000;
that discrepancy remains explicit. Row arithmetic, asterisks, missing bands and
cross-table differences remain qualified rather than rebalanced.

Nandi's Table 2.11 row prints zeros, but the note explicitly says it supplied no
aging analysis. Those raw zeros are retained and the usable amounts remain null.
An ordinary printed zero, such as Lamu's older bands, remains zero. Dashes remain
missing. The 46/47 availability count therefore describes usable observations,
not the number of nonblank printed rows.

Table 2.12 (PDF pp.54–55) separately reports assembly aging, including missing
band cells and inconsistent rows. This executive adapter does not ingest it.
Assembly, national and combined populations return structured absence, never an
executive substitute. National BROP balances and Table 2.10 all-obligation totals
do not supply their ages. Broader assembly qualification is a separate adapter
extension; this UI does not claim that the publisher has no assembly table.

## Storage, API and rollout

No migration or new model is required. A version-1 cohort uses existing immutable
`Extraction` JSON and `SourceDocument.metadata.pending_bills_aging_v1`, with a
source URL, digest, stock date, normalized cohort fingerprint and the associated
pending-bills publication batch. Individual numeric cells retain the existing
PDF acquisition/extraction/qualification chain and precise page/table/column
locators. Missing values retain raw cells and reader qualifications.

The county writer's existing savepoint and county-row locks cover stock writes,
aging evidence, extraction insertion and the active pointer. Caller commit owns
the transaction; the adapter never commits. Replays validate incoming evidence
before deduplication. Fresh parse and full-envelope attestation reject serialized
or altered observations, including removed qualifications. Same-date corrections
update the active cohort atomically; older stock dates, changed artifacts, mixed
populations and incomplete continuations are refused. History is not deleted.
A subsequent ordinary stock write clears the active aging pointer, so an old
aging cohort cannot survive an unqualified replacement edition.

`SEED_PENDING_BILLS_AGING_ENABLED` must be exactly `true` to enable acquisition in
the existing county pending-bills fetch path. It defaults off and is not added to
workflow, registry, source plan or production configuration. The existing bounded
shared download and receipt-store policies are unchanged. With the opt-in on,
both payables and aging are freshly parsed from that same download; a cached
positive payables comparison cannot acquire authority through fresh aging. The
default-off path keeps its existing parse-cache behavior. A current genuine
acquisition and retention receipt remains required; a cached file or a local
fixture does not gain publisher transport authority. Future rollout belongs to
the coordinator after source/cache/runtime review; the observed external download
needed 514 seconds on its successful bounded retry, so existing production fetch
deadlines may still refuse it. Do not silently raise them or backfill production.

The summary and county endpoints add `aging_observations` keyed by population.
Legacy unscoped `aging_buckets` stays null and existing absence codes remain for
compatibility. Existing county/combined complete-total withholding and separately
labelled reported sums remain intact. Reads use three bounded database queries
for the one current cohort and perform no PDF, receipt-object or HTTP reads.
No new schema is needed: missing v1 metadata returns structured absence.

The debt page's population selector presents executive source bands, availability,
qualifications, source discrepancy, numeric table and conditional chart. National,
assembly and combined selections show app-observation absence. Missing bands do
not become zero bars, malformed money is refused, and the numeric table remains
accessible without the chart. The older county-panel absence copy now describes
missing app observations instead of asserting publisher-wide absence.

Rollback/disable: keep the producer opt-in off; an ordinary later county stock
write clears its active pointer. Reverting this additive code restores the legacy
reader without deleting stored extraction history. No production rollback or
activation was performed by this author.

## Verification and acceptance boundaries

Evidence root (outside Git):
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_83_BUILD/aging`.
The small committed JSON fixture contains genuine extracted source cells plus
hash, title, unit, date and page attribution; the full PDF stays outside Git.

The unchanged-base API regression was observed red (`KeyError: aging_observations`)
and green after implementation. Independent Spec and Standards reviewers executed
hostile inputs. Confirmed replay, qualifier mutation, fresh-parse binding,
empty-input and UI comparison-amount findings were independently reproduced,
fixed and retained as red/green receipts. No paid bot review was requested.

Final counts, Chrome receipts, commit/PR binding and cleanup are recorded in the
external STATUS/evidence manifest at handoff completion. The final verification
uses Python 3.13 plus an owned requirements-resolved overlay and the exact frozen
frontend lockfile with its canonical tooling repairs. Earlier shared-runtime
setup failures and preliminary passes are retained, not counted as final parity.
The preliminary StyledGeography TypeScript error disappeared with the correct
lockfile dependencies; no unrelated product fix or issue is needed.

Owned PostgreSQL fixtures exercise JSONB persistence, commit/reopen, rollback,
replay, concurrent writers and real HTTP handlers. Browser verification uses the
actual debt client fed by real fixture database/API output and genuine report
cells with an explicitly synthetic acquisition. This is local source/contract
verification, not production ingestion or live financial acceptance. No hosted
Actions were run. The first full nightly and later rollout/deployed acceptance
remain coordinator responsibilities, distinct from this draft PR.

Final author gates: **237 affected backend tests passed** (including actual
PostgreSQL), **110 frontend tests passed**, TypeScript and the two new frontend
files' ESLint checks passed. Source identity/current-page extraction and the
reported API/UI values were checked separately from these fixture counts.
Chrome retained full executive text, three unsupported selections, the visible
chart screenshot and DOM bar geometry. Four forest-colored bars share a
1166-pixel track and match the four observed source proportions. The initial
undefined color token and guarded null-coalescing lint failures were corrected;
original failures remain in external receipts. CUA synthetic key probes did not
visibly operate the native popup, so full keyboard/screen-reader/narrow-viewport
conformance is not certified by this pass. The labelled native control, table
headers and polite status region are present.
