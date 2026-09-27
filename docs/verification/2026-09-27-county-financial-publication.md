# County financial publication — 27 September 2026

Implementation is prepared for review; production publication is **not complete**. No production seed, migration, cleanup, cache mutation or credential change ran in this session. This receipt addresses #238, #273, #299, the CoB portion of #230 and publication acceptance in #321. It does not repeat the completed #318 migration.

## Selected evidence

The official [CoB consolidated reports listing](https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/) and [Treasury BROP listing](https://www.treasury.go.ke/budget-review-and-outlook-paper/) were checked on 27 September. The selected editions are the annual FY2025/26 CBIRR and final 2026 BROP, not the draft BROP or nine-month CBIRR.

| Artifact | Evidence |
|---|---|
| [CoB annual FY2025/26 CBIRR](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482) | August 2026; 935 PDF pages; SHA-256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3` |
| [Treasury final BROP 2026](https://www.treasury.go.ke/sites/default/files/BROP%20-%20Budget%20Review%20Outlook%20Paper/2026%20Budget%20Review%20and%20Outlook%20Paper....pdf) | 76 PDF pages; SHA-256 `39c2e290ecdb6be0d8768344514711a5b0c6a350f0416ed81e529cded60def24` |

These are retained local artifacts, checksum-verified before and after a fresh extraction. A current listing or HTTP HEAD response alone does not establish that the retained bytes equal a later reissue at the same URL. Re-fetch/version verification is a release prerequisite. The offline receipt deliberately says `production_published: false` and cannot certify API or browser publication.

Live HEAD at 20:22 UTC identifies the CoB filename as `CGBIRR FY 2025_26 August 2026 Final 5.pdf`; Treasury reports ETag `6a9fd8ce-3520a5`, last-modified 8 September 2026, length 3,481,765 bytes. These metadata are preserved in the receipt, with their limited scope stated explicitly.

The machine-readable [source receipt](2026-09-27-county-source-receipt.json) retains all 47 counties, extraction refusals, source pages, pending-bill amounts and project reconciliation. The [coverage CSV](2026-09-27-county-coverage.csv) provides one row per county and period. Monetary columns name their units; empty values mean unavailable.

## Revenue and budgets

Fresh extraction on base `dc58685` reconciled **26/47** cash-receipts tables, not the older issue's 22/47. Both the baseline and changed parser read the same annual artifact with SHA-256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`. This change reconciles **37/47**, recovering Baringo, Elgeyo Marakwet, Garissa, Isiolo, Kajiado, Kakamega, Marsabit, Meru, Murang'a, Nairobi and Trans Nzoia. No previously reconciled county is lost. The annual output contains 428 budget/revenue records. All 47 budget totals remain present: KES 648,234.41 million allocated and 496,578.36 million expenditure.

The fixes distinguish lettered grant items from aggregate section headings, handle a split `Grand | Total` cell, preserve explicit publisher zero, and reject zero totals built from unobserved sections. Missing or malformed amounts remain absent through fetch, normalization and persistence. Official replacements withdraw omitted amounts, page references, notes and artifact assertions instead of inheriting stale current evidence; historical provenance remains available.

Visually checked source samples:

| Source page | Check |
|---|---|
| CoB PDF 129, printed 95 | Elgeyo Marakwet: lettered DANIDA KES 6,222,000 belongs inside grants, not a second aggregate section. Printed grants subtotal KES 654,611,899; cash grand total KES 8,129,336,090. |
| CoB PDF 600 rendered; 601 extracted, printed 566–567 | Nairobi: lettered grant items must not be counted beside the published grant subtotal. Grand total KES 37,917,986,931. Reconciliation uses the publisher's section subtotal; it does not certify every grant item independently. |
| CoB PDF 564–565, including printed 531 | Mombasa: ordinary OSR cash KES 3,799,700,513 plus FIF cash KES 2,414,889,970 = cash OSR KES 6,214,590,483. Receivables of KES 11,818,407,252 and KES 3,093,226,161 are separate. Cash total including opening balance is KES 15,790,774,484. Summary-table OSR KES 21,126.23 million follows the rounded accrual values, not cash. The existing disagreement/basis display remains appropriate. |

Ten county cash totals remain withheld. These are **parser/extraction reconciliation reasons**, not blanket findings that a publisher's accounts are wrong:

| County | PDF pages inspected/extracted | Remaining reason |
|---|---|---|
| Bungoma | 94–96 | Header says Actual Revenues; unsupported cash-table shape. |
| Busia | 112–113 | Actual Revenue/arrears/accrual shape; unsupported cash-table extraction. |
| Kilifi | 312–314 | Extracted continuation does not yield a usable grand total. |
| Kisii | 330–332 | Unreadable receipts cells, including underscore grant cells. |
| Kisumu | 349–351 | Fragmented total/target cells do not yield a usable grand total. |
| Kitui | 367–369 | Extracted streams differ from grand total by KES 1,286,750,892.25. |
| Kwale | 385–387 | Extracted streams differ by KES 59,814,318. |
| Migori | 546–549 | Nested allocation subtotals are not supported safely. |
| Nyeri | 712–713 | Extracted streams differ by KES 746,508,377; blank subtotal requires further work. |
| Samburu | 729–730 | Repeated equitable-share subtotal is ambiguous to the parser. |

## Pending bills and projects

BROP PDF/printed page 18, paragraph 20, states national pending bills at **30 June 2026**: KES 475.5 billion = KES 365.6 billion State Corporations + KES 109.9 billion MDAs. No eligibility split is supplied.

CoB Table 2.10, PDF pages 51–53, states county trade payables at the same date. **46 counties report an amount; Nandi has dashes**, not an explicit monetary zero (visually checked PDF 52, printed 18). The reported rows sum to KES 172,526,690,000, equal to the printed aggregate. This sum is not a complete 47-county observation. Therefore county total and combined national/county total remain null; the separately labelled `reported_county_sum` and coverage describe what is available. Individual reported counties remain publishable.

PDF 53, printed 19, was also visually checked: the table's total is KES 172,526.69 million, attributed to County Treasuries. The following text explicitly says Nandi's Executive and Assembly did not report; it also names nine non-reporting county assemblies (Elgeyo Marakwet, Kirinyaga, Kisumu, Lamu, Nyamira, Samburu, Tana River, Uasin Gishu and West Pokot) and flags inconsistent submissions in several counties. Thus even the 46 county amounts must keep their reader notes and assembly/reporting qualifications. The printed aggregate remains source evidence in every extracted row's `printed_total_millions`; it is not erased or silently promoted to a complete app-computed total.

The API now requires both national components or all 47 distinct counties, with one source document, URL, as-at date and writer batch per side. A content fingerprint of the entire batch prevents partial same-URL corrections from combining with older retained rows. Different dates, missing components, duplicate counties and malformed/missing batch metadata cannot publish full totals. Eligible/ineligible aggregates require complete supplied coverage; unavailable splits stay null.

The shared CoB artifact also yields 47 county project records and 20 cited table captions. Table 2.6 (PDF 44–45) prints 189 stalled projects, KES 10,508.01 million value and KES 4,206.15 million paid; the narrative rounds these to 10.51/4.21 billion. County reconciliation and gaps remain explicit.

Visually checked Baringo Table 3.11, PDF 70, printed 36: Sugut Dispensary staff house value KES 1,999,849, paid KES 698,146, balance KES 1,301,703, 50% complete, insecurity; Marigut Community Social Hall value KES 3 million, paid dash (null), balance KES 2.5 million, 5% complete, contractor delay. Across PDF 70–71 the parser keeps 23 rows, KES 163,319,185 value and KES 83,693,748.60 known paid, reconciling with gaps and printed rounding. These are source-reported stalled projects, not an OAG conclusion about every row. Session 4 found no named Sugut/Marigut match in its FY2024/25 Baringo volume; no automatic cross-year linkage is justified. No Projects tab was enabled or project data written.

## Production baseline and remaining release work

Read-only PostgreSQL observation at **2026-09-27 20:12:14 UTC**, enforced with `transaction_read_only=on` and rolled back:

- Document **2383** still has publisher `OCOB`, the 2025 Treasury BROP URL/title, and **48 loan references**. A 2026 seed may create another document; it cannot be described as repairing 2383. #273 remains open.
- The 188 county financial records remain on **FY2025/26 9M**, document **2388**, 47 each of Total, Recurrent, Development and Own Source Revenue. Total allocations/spend are KES 633,303,870,000 / 331,647,720,000. No Revenue Receipts records are present in this baseline.
- There are 48 legacy pending-bill rows, withheld by current publication guards. No seed ran here.

Public API checks returned HTTP 200 for county 47 (database ID 47 = **Migori**), fiscal-year menu, pending bills and pending-bills summary. Migori's budget remains FY2025/26 9M, allocation KES 11,777,350,000 and expenditure KES 5,605,820,000; total revenue and pending bills are null. The pending-bills endpoint has zero published records and null totals. A background browser observation at `https://www.auditgava.com/counties/47` confirms the same period, KES 11.78B budget, 47.6% execution and dashes for revenue/pending bills.

`/api/v1/provenance/verify/budget_lines?entity_id=47&year=2025` resolves to document 2388 and its nine-month URL. Its `publishable` verdict explicitly does **not** fetch or validate document bytes. It is source linkage evidence, not annual-source validation. An earlier probe used unsupported `record_id=1`; that response is not record-specific evidence and is excluded from acceptance.

Release sequence, coordinated by Session 5:

1. Review, merge and deploy the parser/writer/API corrections and Session 5's refresh mechanism. Confirm the deployed SHA. At this receipt's baseline `REVALIDATE_SECRET` is absent; Session 5 must establish refresh or record an explicit release fallback.
2. Pin both selected artifact versions and re-run the offline preflight. Any changed checksum, edition, candidate count or coverage requires reviewing the new receipt before writing. Pin the annual CBIRR URL for both county budgets and pending bills; do not let independently changing discovery choose different editions.
3. Prepare a fresh exact-key database manifest and recovery snapshot for `counties_budget` and `pending_bills` only. Candidate scope is 428 annual budget/revenue rows and 48 pending-bill amounts (46 county, two national), plus their fiscal-period/source/provenance/ingestion metadata. The pending writer's existing obsolete-county-row handling can also retire superseded county values; enumerate those exact IDs and dependencies from the fresh state before execution. Counts above describe parsed candidates, not promised INSERT/UPDATE/DELETE counts.
4. Preserve and compare all 188 historical 9M rows byte-for-byte. Inventory matching annual budget keys, pending lender/entity keys, affected source documents, source references, and any obsolete county rows. Test recovery in a disposable database: restore changed/deleted rows and remove only newly inserted IDs while preserving foreign keys. A previous release's backup is not a recovery receipt for this future seed.
5. Repair document 2383's publisher as a separate bounded part of that manifest: verify its ID, exact 2025 Treasury URL, existing publisher and current reference set under lock; change only publisher to `National Treasury`; require exactly one affected row; retain the old value for recovery. Abort on drift. Do not rewrite its title/URL/year to the new edition or delete its references. This correction has not run.
6. Run one serialized, bounded domain job, recording actual touched keys and transaction outcomes. Refuse a fixture fallback or a supposedly successful run with absent source evidence. Compare annual budgets, 37 cash totals and all 47 coverage statuses against the receipt. Confirm national KES 475.5B, 46 county amounts, Nandi absence, null full county/combined totals and null eligibility splits.
7. Refresh the backend and frontend through Session 5's verified mechanism. Capture API plus rendered browser observations for Mombasa (cash/accrual distinction), a recovered county, an unresolved revenue county, Nandi and the debt pending-bills totals. Check fiscal-period menu/default and page/source provenance. Only this closes production acceptance; local green tests do not.

Projects remain a separate source-reviewed rollout and product decision. Session 2 receives any now-unreferenced cleanup candidates only after financial refresh and a fresh dependency manifest; this session grants no additional deletion scope.

## Reproduction and tests

From the repository root, with backend dependencies installed:

```sh
PYTHONPATH=backend python backend/scripts/inspect_county_finance_publication.py \
  --cbirr-pdf /path/to/cbirr-2025-26.pdf \
  --brop-pdf /path/to/brop-2026.pdf \
  --cbirr-sha256 5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3 \
  --brop-sha256 39c2e290ecdb6be0d8768344514711a5b0c6a350f0416ed81e529cded60def24 \
  --output /tmp/county-source-receipt.json
cd backend
PYTHONPATH=. TESTING=true python -m pytest tests/ \
  --ignore=tests/integration -q -m 'not slow'
```

The regression fixtures include real extracted county tables and valid complete-population controls. Initial parent boundary tests reproduced eleven failures; the separate split-grand-total case also failed before correction. Independent adversarial probes reproduced lettered-item/zero defects, blank annual targets, stale official replacement metadata, partial and mixed pending editions, malformed batch fingerprints and incomplete eligibility splits. Preflight probes execute absent, empty, corrupted, truncated, checksum-mismatched and mid-extraction-mutated files; none may certify production publication. A final dot-as-grand-total probe reproduced another false zero before correction, and a valid thousands-separator control protects the monetary conversion boundary.

Final local validation on Python 3.13: **5,436 core backend tests passed, 24 skipped** (132.89 seconds); **149 focused publication/adversarial tests passed**; critical flake8 and `git diff --check` passed. The final parser also matched every cash total and all 47 coverage statuses against the full-PDF receipt using the retained raw extraction from the same checksummed artifact. No PostgreSQL production write or post-seed browser test is included in these results. CI is followed separately on the draft PR.
