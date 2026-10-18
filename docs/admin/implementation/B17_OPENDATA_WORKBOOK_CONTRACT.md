# OpenData native workbook contract (#621/#602)

This lane adds an explicit, default-off `opendata → opendata` entrypoint for the official KNBS Economic Survey 2026 Public Finance workbook. The human selected this route on 2026-10-18 within the original scope, with no new costs. Publisher remains **Kenya National Bureau of Statistics**. Existing `knbs → population` and CRA mappings retain their contracts. This is not a claim that ICT Authority formally migrated its old portal.

## Fixed source and semantics

- Official publication: https://www.knbs.or.ke/reports/2026-economic-survey/ (April 2026).
- Runtime URL: https://www.knbs.or.ke/wp-content/uploads/2026/10/Chapter-5-Public-Finance.xlsx
- Exact reviewed edition: 224617 bytes; SHA256 `887712acdb8ec673f96d6d0fd14491a5861b0450d2ffcf49aedde093a257a5d5`. A same-URL revision refuses until separately reviewed. No arbitrary input URL, discovery, login, redirects or fallback.
- Stable extraction ID: `knbs_county_revenue_2026_table_5_13`; parser `knbs-economic-survey-2026-table-5.13-v1`; worksheet `Table 5.13`, range A1:AU57. This is a worksheet/cell locator, not an invented PDF page number.
- 47 named county rows plus a separately identified published aggregate; five metrics: equitable share, conditional grant, unconditional grant, own-source revenue and total revenue. Total revenue is non-additive with its components.
- All 2208 table positions are retained: 2125 numeric cells, 53 literal dashes and 30 blank cells. Missing observations retain their original marker and a null numeric amount; they never become zero.
- Raw OOXML numeric lexemes are preserved alongside explicit two-decimal HALF_UP comparison amounts. Arithmetic uses a local Decimal context; caller precision cannot alter it. This comparison policy is not a correction to raw publisher bytes or a claim that every General-format Excel cell displays two decimals.
- Each original period label is retained. `*` means provisional, `+` means revised, unmarked means **unspecified**, never actual/final. Preserve all five footnotes exactly, including their source spelling/spacing.
- Retain each county sum, original published total and difference only when every component is numeric. Incomplete sums stay null. FY2023/24 OSR: county sum79703.14, published total79703.15, difference−0.01 million. The cause is unestablished; never rebalance, silently tolerate away, overwrite, or describe as a pipeline defect.

## Unit and edition evidence

The official [survey PDF](https://www.knbs.or.ke/wp-content/uploads/2026/04/2026-Economic-Survey.pdf), SHA256 `8e26f32b6b7a43250b7c175f24193c00332a0c00244faf0ad050f64dfb14bafc`, printed111/112 (PDF150/151), labels Table5.13 **KSh Million** for equitable/conditional/OSR/total. All384 latest-period numeric entries match the workbook at published two-decimal precision. The PDF covers two periods; the workbook expands the historical series. The unit is attributed to that table context, not to a nonexistent workbook header.

Unconditional grants X/Y are additionally corroborated by the public KNBS SDMX series `KE1,DF_PF_CG_REV,1.0/A.KE.G1311_KE001.....`: KES, attached UNIT_MULT6, financial-year code F07, observations2024=108.66 and2025=7.43 matching X52/Y52, latter provisional. Its message still declares `Test=true`; the exact bounded Chrome DOM capture is retained. This is unit/context evidence only. No SDMX message or CSV is an ingestion input.

PDF FY2024/25 Conditional/OSR/Total have `+`; workbook V/AI/AT are unmarked. The extraction records this as a supplemental edition difference and preserves the workbook’s original labels. It does not silently assign the PDF’s markers to the workbook or promote unmarked cells to final figures.

## Effects, ownership and failure

One genuine `SourceDocument` (actual KNBS publisher, official URL/title, source MD5/SHA256/byte length, edition and status metadata) and one exact `Extraction` (page_number/confidence null, worksheet/cell provenance) are appended transactionally. No budget/revenue/fiscal fact table is written. Extraction explicitly remains `source_extracted_not_publication_qualified`; the financial/publication gate is unchanged. Dry-run validates source, semantics and owner but writes no document/extraction.

Before transport, and again on the writing transaction after transport, prove the exact RUNNING native/dispatch job, durable claim, metadata shape, timestamps, entering nonce and continuous lock backend. Lock loss/foreign ownership refuses and retains uncertainty. Replay verifies strict canonical JSON types and the full source/extraction identity; mismatch or duplicates refuse rather than repair or append. Exceptions roll back effects and produce a correlated failed terminal observation through the existing CLI/worker. Unknown/unavailable inputs produce no accepted command/success effect.

Bootstrap and legacy reference writers enroll `opendata` in their conservative effect sets before reference effects. Admission/recovery use the same existing claim protocol; no age-based release or blind retry is introduced.

Legacy scope holds all fifteen advisory keys on one physical transaction, leaving a second connection for work with pool_size2/max_overflow0. Distinct per-domain claims, entry nonces and ownership-only jobs remain. Individual member acknowledgement refuses; collective release validates every member and stored receipt, fires deferred constraints, and commits once on the lock backend. Invalid receipts roll back all releases; backend/storage uncertainty retains ownership. Known partial-admission refusal releases only the scope's own acquired claims before any loader work.

`SEED_OPENDATA_INGESTION_ENABLED` accepts only bool or literal `true`/`false`, defaults false. Builtin imports, worker readiness and the handler all enforce it. Dedicated dispatch additionally needs its existing explicit source/global gates. New migration `e621b17a0001` follows `a705b15a0001`; it changes only the exact mapping/domain check constraints after requiring a stopped worker, preserves prior mappings/ACL/RLS, and refuses downgrade with OpenData history. No migration is applied to production by this lane.

Transport: one GET, no retries/redirects/proxy inheritance, 10s per-I/O timeout, 30s elapsed acceptance budget checked between chunks and after the response, 1MiB cap. The elapsed check is not a hard wall-clock cancellation deadline. Exact artifact hash/size is checked before ZIP/XML processing; archive members/expanded bytes and static cell types are bounded; no formulas execute. No dependency, account, service, paid API or infrastructure upgrade is required.

## Acceptance and evidence

Issues #621/#602 stay open until exact-source CLI/worker/owned-PostgreSQL, replay/rollback/ownership/contention/recovery, migration, current/minimum and optimized guards, and separate executable Standards/Spec reviews pass. Production deployment/activation and public figure qualification remain outside this lane. The required deliverable is a reviewable draft PR, not a merge or rollout.

Append-only author/reviewer evidence lives outside the product checkout at `FULL_PLAN_COMPLETION_B17/opendata/workbook-implementation-20261018`; earlier research and prerequisite packets remain historical and unchanged. The retained 224KiB chapter fixture supplies exact official bytes for deterministic tests; there is no ongoing dataset crawl or copied PDF corpus.
