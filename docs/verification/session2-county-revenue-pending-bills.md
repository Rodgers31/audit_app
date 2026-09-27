# County revenue basis and pending-bills editions — Session 2

Dependency base: #327 at `3ee591107535280839ff0763b3cf10ddf69ff876` (`consolidate/audits-pending-bills-and-guards`). This work does not import #327 into main. No production writes, seeding, merging or deployment occurred.

## #299: what the Mombasa report actually says

Source: [Controller of Budget, County Governments Budget Implementation Review Report FY2025/26](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482), 935 PDF pages. SHA-256: `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`. The cached original's checksum was checked; PDF 37 and565 were rendered and inspected against extracted text.

Table 2.1, printed page 3/PDF 37, labels its summary “Actual Realised (Kshs. Million)”. Table 3.426, printed pages 530–531/PDF 564–565, separately labels actual cash receipts, receivables, and accrual revenue, with formula `D=B+C`. The chapter narrative also states KSh 6.21B own-source revenue including FIF and KSh 15.79B total receipts.

| Measure, KES | Ordinary OSR | FIF | Sum |
|---|---:|---:|---:|
| Actual receipts |3, 799, 700, 513|2, 414, 889, 970|6, 214, 590, 483|
| Receivables |11, 818, 407, 252|3, 093, 226, 161|14, 911, 633, 413|
| Accrual |15, 618, 107, 765|5, 508, 116, 131|21, 126, 223, 896|

The summary's components are15, 618.11M and5, 508.12M. Its printed formula `F=D+E` produces 21, 126.23M. These are the chapter's **accrual components rounded separately** to 0.01M. The KES6, 104 difference from exact summed accrual is explained by that component rounding; it is not another defect.

This is a **source-supported reconciliation**, not a publisher admission that the summary label means accrual. It is not a period/unit mismatch or evidence that county data crossed. The explanation must not be generalized to other counties whose measures differ.

`backend/tests/fixtures/mombasa_revenue_basis.json` pins both sets of labels, units, pages, checksum and exact values. `test_mombasa_revenue_source_reconciliation.py` executes the arithmetic with Decimal.

## Publication behavior

Reconciled chapter cash streams and their total remain visible even when the summary measure differs. Total is explicitly cash receipts **including the opening balance**. Own-source cash and its target both include OSR/FIF/AiA where printed. The summary's “Actual Realised” amount/target remain separately labelled; material disagreement remains exposed. Without cash rows, the summary measure is labelled as such rather than called cash.

List/map, plain detail and comprehensive share the block; overview/report cards retain period, basis and disagreement. Duplicate streams, mixed source/period/entity/currency, malformed/nonfinite/negative/bool values and nonreconciling totals cannot publish a plausible cash total. Bad summaries do not erase independently valid cash. Missing target withholds the ratio denominator. Explicit reconciled 0 remains0; the pending-bills parser's printed-zero/dash controls remain intact. No automatic “all-zero means absent” rule was introduced. This does not expand extraction coverage for the 25 counties lacking usable chapter tables.

The new source-basis prose is English; multilingual editorial review remains under #307.

## #321 items 2–3: writer guards

Discovery ranks named fiscal editions before upload IDs, case-insensitively; a late upload of an old report cannot become newest solely through its upload number. The writer independently requires one canonical ISO 30 June as-at date, agreement with the report table, and no rollback behind any published county row. Same-date corrections and newer editions remain allowed.

County publication requires county entity types and resolves **all** identities before touching documents/loans. Unknown or duplicate identities fail the whole edition; fallback matching is county-only and exact rather than substring matching assemblies/agencies. A savepoint prevents a malformed later record leaving earlier updates dirty when the domain catches the exception. PostgreSQL county-entity row locks serialize edition checks through the caller's transaction; concurrency execution still needs PostgreSQL CI because local tests use SQLite.

## Evidence and integration order

- Original edition guards: 5 failed/2 passed; upload ordering1 failed.
- Independent attacks reproduced incorrect national/agency writes, valid-row retirement after unresolved counties, late-record partial writes, case fallback and upper-case fiscal slugs. Final guard-only run 51 passed.
- Revenue basis adversarial run initially 14 failed/22 passed; all 36 now pass, including the public mixed-source route and50% OSR+FIF+AiA target control.
- Combined focused backend run 304 passed/1 skipped (optional live PDF test); frontend29 passed and TypeScript no-emit passed. Formatting/whitespace checks passed.

Session 4 #330 changes only the shared download call/imports in `fetch_county_payables_payload`; this branch changes discovery ordering in `year_end_cbirr_links` and writer guards. These hunks are disjoint and complementary. Apply both after #327, resolve by function rather than taking a whole fetcher/main file, then run the download interruption/resume tests and edition tests together. This draft's non-main base is excluded by the current backend CI base filter; fresh main-targeted CI after transplant is required. The separate Session 2 identity/accounting PR and Session 1 metadata changes also touch main.py and must be combined by function.

Keep #299 and the production-dependent acceptance conditions of #321 open until the backend is deployed, caches advanced, ingestion succeeds, and the public API is checked. #321 item1 is already in #327; unrelated dead-code/migration-log items remain outside this patch.

Combined rehearsal: applied Session4's `09dcc9194a4d713fc03c3fb91d22816c7980ad48` patch without conflicts onto this branch in a separate temporary checkout. `test_pending_bills_shared_download.py`, `test_cbirr_download.py`, and both edition-guard test files passed together (67 tests). This verifies the shared resume/fingerprint call and edition guards together; it does not replace PostgreSQL or main-targeted CI.
