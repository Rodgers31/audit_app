# County revenue basis and pending-bills editions — Session 2

Dependency base: #327 at `3ee591107535280839ff0763b3cf10ddf69ff876` (`consolidate/audits-pending-bills-and-guards`). This work does not import #327 into main. No production writes, seeding, merging or deployment occurred.

## #299: what the Mombasa report actually says

Source: [Controller of Budget, County Governments Budget Implementation Review Report FY2025/26](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482), 935 PDF pages. SHA-256: `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`. The cached original's checksum was checked; PDF 37 and 565 were rendered and inspected against extracted text.

Table 2.1, printed page 3/PDF 37, labels its summary “Actual Realised (Kshs. Million)”. Table 3.426, printed pages 530–531/PDF 564–565, separately labels actual cash receipts, receivables, and accrual revenue, with formula `D=B+C`. The chapter narrative also states KSh 6.21B own-source revenue including FIF and KSh 15.79B total receipts.

| Measure, KES | Ordinary OSR | FIF | Sum |
|---|---:|---:|---:|
| Actual receipts |3,799,700,513|2,414,889,970|6,214,590,483|
| Receivables |11,818,407,252|3,093,226,161|14,911,633,413|
| Accrual |15,618,107,765|5,508,116,131|21,126,223,896|

The summary's components are 15,618.11M and 5,508.12M. Its printed formula `F=D+E` produces 21,126.23M. These are the chapter's **accrual components rounded separately** to 0.01M. The KES 6,104 difference from exact summed accrual is explained by that component rounding; it is not another defect.

This is a **source-supported reconciliation**, not a publisher admission that the summary label means accrual. It is not a period/unit mismatch or evidence that county data crossed. The explanation must not be generalized to other counties whose measures differ.

`backend/tests/fixtures/mombasa_revenue_basis.json` pins both sets of labels, units, pages, checksum and exact values. `test_mombasa_revenue_source_reconciliation.py` executes the arithmetic with Decimal.

## Publication behavior

Reconciled chapter cash streams and their total remain visible even when the summary measure differs. Total is explicitly cash receipts **including the opening balance**. Own-source cash and its target both include OSR/FIF/AiA where printed. The summary's “Actual Realised” amount/target remain separately labelled; material disagreement remains exposed. Without cash rows, the summary measure is labelled as such rather than called cash.

List/map, plain detail and comprehensive share the block; overview/report cards retain period, basis and disagreement. Duplicate streams, mixed source/period/entity/currency, malformed/nonfinite/negative/bool values and nonreconciling totals cannot publish a plausible cash total. Bad summaries do not erase independently valid cash. Missing target withholds the ratio denominator. Explicit reconciled 0 remains 0; the pending-bills parser's printed-zero/dash controls remain intact. No automatic “all-zero means absent” rule was introduced. This does not expand extraction coverage for the 25 counties lacking usable chapter tables.

The new source-basis prose is English; multilingual editorial review remains under #307.

## #321 items 2–3: writer guards

Discovery ranks named fiscal editions before upload IDs, case-insensitively; a late upload of an old report cannot become newest solely through its upload number. The writer independently requires one canonical ISO 30 June as-at date, agreement with the report table, and no rollback behind any published county row. Same-date corrections and newer editions remain allowed.

County publication requires county entity types and resolves **all** identities before touching documents/loans. Unknown or duplicate identities fail the whole edition; fallback matching is county-only and exact rather than substring matching assemblies/agencies. A savepoint prevents a malformed later record leaving earlier updates dirty when the domain catches the exception. PostgreSQL county-entity row locks serialize edition checks through the caller's transaction. The focused PostgreSQL follow-up below executed competing sessions and rollback; main-targeted CI is still required after transplant.

## Evidence and integration order

- Original edition guards: 5 failed/2 passed; upload ordering 1 failed.
- Independent attacks reproduced incorrect national/agency writes, valid-row retirement after unresolved counties, late-record partial writes, case fallback and upper-case fiscal slugs. Final guard-only run 51 passed.
- Revenue basis adversarial run initially 14 failed/22 passed; all 36 now pass, including the public mixed-source route and 50% OSR+FIF+AiA target control.
- Combined focused backend run 304 passed/1 skipped (optional live PDF test); frontend 29 passed and TypeScript no-emit passed. Formatting/whitespace checks passed.

Session 4 #330 changes only the shared download call/imports in `fetch_county_payables_payload`; this branch changes discovery ordering in `year_end_cbirr_links` and writer guards. These hunks are disjoint and complementary. Apply both after #327, resolve by function rather than taking a whole fetcher/main file, then run the download interruption/resume tests and edition tests together. This draft's non-main base is excluded by the current backend CI base filter; fresh main-targeted CI after transplant is required. The separate Session 2 identity/accounting PR and Session 1 metadata changes also touch main.py and must be combined by function.

Keep #299 and the production-dependent acceptance conditions of #321 open until the backend is deployed, caches advanced, ingestion succeeds, and the public API is checked. #321 item 1 is already in #327; unrelated dead-code/migration-log items remain outside this patch.

Combined rehearsal: applied Session 4's `09dcc9194a4d713fc03c3fb91d22816c7980ad48` patch without conflicts onto dependent runtime head `f7f55b655b4eed6bfa5b73e5ffc917698c3672ff` in a separate temporary checkout. Its runtime matches published `c7819b243225b8065fa79414c1965bba4fefeb22`; the amendment changed documentation only. Exact staged combined tree: **`0402668484bac9951dff325a74a6677f060dffa8`**. `test_pending_bills_shared_download.py`, `test_cbirr_download.py`, `test_pending_bills_edition_guard.py` and `test_pending_bills_edition_adversarial.py` passed together (**67 tests**), recorded in `session2-shared-download-combined.txt`. This verifies the shared resume/fingerprint call and edition guards together, not the separate evidence-preservation changes or a full integration of all sessions.

## PostgreSQL concurrency follow-up

Application code tested: `c7819b243225b8065fa79414c1965bba4fefeb22`. `backend/scripts/verify_county_editions_postgres.py` ran against a fresh disposable PostgreSQL 17 database, on loopback port 53333 with no persistent volumes. All identities, amounts and source documents were synthetic. It refuses non-loopback URLs, databases without the `audit_app_session2` prefix, nonempty databases and Python optimization that disables assertions.

Two separate SQLAlchemy sessions competed for county locks. An independent connection observed `pg_stat_activity.wait_event_type='Lock'` before releasing the first transaction. All five scenarios passed:

1. A newer 2027 edition held the lock; an older 2026 writer waited, then rejected after the newer transaction committed. Both county balances remained 700 dated 2027-06-30.
2. A newer 2028 transaction rolled back; the waiting same-date 2027 correction then succeeded. Both balances became 750 dated 2027-06-30.
3. Two 2027 corrections serialized; the later correction persisted as 770.
4. A 2028 writer waited behind a 2027 correction, then succeeded with 800 dated 2028-06-30.
5. A malformed later record raised after an earlier county update. The caller caught the error and committed its outer transaction; the writer's savepoint restored both balances to 800 dated 2028-06-30.

Result: **5 scenarios passed; 4 observed lock waits**. Raw output: `session2-postgres-editions.txt`. The harness closes the lock-owning session before waiting for its worker when an assertion fails, and sets bounded PostgreSQL statement/lock timeouts.

Reproduce against a newly created empty local PostgreSQL database:

```sh
SESSION2_POSTGRES_URL=postgresql://postgres:LOCAL_PASSWORD@127.0.0.1:LOCAL_PORT/audit_app_session2_writer python backend/scripts/verify_county_editions_postgres.py
```

Independent harness checks also passed 34 URL/database guard cases across both scripts using stubs without connections (`session2-postgres-guards-final.txt`). Four forced race failures exited promptly and released the owning session before waiting for the worker; these cleanup checks used real threads and fake database locks. They supplement the five real PostgreSQL scenarios above.

No production write or seed run occurred. This focused concurrency result does not replace fresh main-targeted CI after #327 and the other session changes are combined.
