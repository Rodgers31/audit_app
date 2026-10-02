# County cash source decisions — 1 October 2026

**Retain all four refusals under [#299](https://github.com/Rodgers31/audit_app/issues/299).**
New county records explain specific differences for Kwale, Migori and Nyeri,
but none is an explicit correction of the accepted CoB edition. No parser,
fixture, amount, tolerance, budget or project record changed. This document
records the new evidence delta; the [Round11 reconciliation](2026-10-01-round11-county-source-reconciliation.md)
retains the existing annual-source ledger and release requirements.

## New source identities and chronology

All sources were captured by public GET on 1 October 2026 in America/Chicago
(2 October UTC). Original bytes, response headers, SHA-256, exact URLs,
relevant rendered pages and executed arithmetic are retained externally under
`ROUND12_SESSION_4_` beside the session brief. PDF page references are one-based.

| Source | Identity and chronology | SHA-256 |
|---|---|---|
| [Kwale Q4 county schedule](https://kwale.go.ke/wp-content/uploads/2026/09/COUNTY-BUDGET-IMPLEMENTATION-REPORT-QUATER-IV-FY2025-2026.pdf) | 1,972,715 bytes; 63 pages. [Download page](https://kwale.go.ke/download/12063/) created/updated 13 September 2026. Revenue schedule E, PDF 31–32, says all departments, 30 June 2026; expenditure schedule PDF 1 states 1 July 2025–30 June 2026. | `f1fa3758288f23aa29816d70ce9b5bfbd60b5354765ea95e330c5ce9471cf18a` |
| [Nyeri Q4 submitted report](https://www.nyeri.go.ke/wp-content/uploads/2026/07/Draft-Fourth-Quarter-Budget-Implementation-and-Project-Status-Report-2025-2026.pdf) | 4,930,878 bytes; 98 pages. [County listing](https://www.nyeri.go.ke/bud/) upload 28 July 2026. PDF 1 is a signed county transmittal dated 28 July, stamped CoB registry 29 July; body is watermarked SUBMITTED. PDF 7 / printed 6 expressly covers 1 July 2025–30 June 2026. Filename “Draft” does not override observed submitted status. | `1016e176a9ce749a8e0640b91b8973b0e833092ff990c4fb0980f3a3a1cb26bb` |
| [Migori September CBROP](https://www.migori.go.ke/storage/downloads/QzCWRssCldyL5PGJ0dpoWxSFXqIg0Hz22VFAOFAB.doc) | Original Word DOC, 2,330,624 bytes; [county listing](https://www.migori.go.ke/downloads) upload 25 September 2026. Cover says FY2025/2026 and DRAFT; foreword says September 2026. Source rendered read-only with bundled LibreOffice to a 116-page derivative; references below identify derivative page and observed printed footer, not an official PDF edition. | `828aa6504c615faa5b874bce6077be0a61d4ca778cce41184e4a218bd50759ab` |
| [Migori OSR upload](https://www.migori.go.ke/storage/downloads/Fg2Pov74fxvt82xr0jn4wqaYQ64fglt2EaZBlxGt.pdf) | 2,057,817 bytes; 2 scanned pages. Listing calls it OSR FY2025/2026, uploaded 23 September 2026. Actual PDF 1 says performance as at June 30, 2025, dated 15 July 2026; PDF 2 signed/stamped 23 September 2026. Period identity is contradictory, so refuse annual substitution. | `83b98a0a9c5dabc464798ae573b674eed7281cd3277c9413f89eec9fc58010e6` |
| [Samburu revenue statements](https://www.samburu.go.ke/download/revenue-statements/) | 10,177,074 bytes; 49 pages; public download ID 4471. Download page created/updated 6 October 2025. Rendered PDF 1 says financial year ended 30 June 2025 and transitional IPSAS accrual basis. Wrong period and measure for annual FY2025/26 cash. | `ceec1617061507858ed78b8286f88bd86f940cbb6083623f1d60bb03dafd6de0` |

The fresh [CoB annual download page](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/)
still reports created/updated 25 September 2026. Fresh county-report listing
still presents that annual report followed by the nine-month/half-year/quarter
reports. Neither page supplies a correction. Retained annual bytes were
checksum-verified as `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`;
the 51 MB annual PDF was not downloaded or reparsed again. Website metadata
does not prove that future or current download bytes cannot change.

## Kwale: exact receivables clue, incompatible replacement schedule

County schedule E, PDF 31, labels actual receipts C separately from
receivables D and accrual E, all Kshs. Its FIF/SHIF row prints cash
**423,580,188**, receivables **59,814,318**, and accrual **408,163,499**.
CoB Table 3.285 PDF 387 / printed 353 instead prints FIF cash **483,394,506**,
a dash in receivables, and accrual also **483,394,506**. Executed arithmetic gives:

`423,580,188 + 59,814,318 = 483,394,506`.

The receivables exactly equal the existing stream/grand residual. Replacing
only the CoB FIF cash cell with the county cash cell would make the annual
stream sum equal its printed total **14,808,402,850**. This is a specific
**cash-versus-receivables hypothesis**, not a publisher-authorized correction.

| Observed cash stream | County Q4 PDF 31 | CoB PDF 385–387 |
|---|---:|---:|
| Unspent balance | 11,118,366 | 1,770,505,972 |
| Equitable share | 9,078,699,643 | 9,078,699,643 |
| Additional allocations | 3,221,690,264 | 3,167,878,534 |
| Ordinary OSR | 367,738,513 | 367,738,513 |
| FIF | 423,580,188 | 483,394,506 |
| Sum of observed subtotals | 13,102,826,974 | 14,868,217,168 |
| Printed cash total | 13,102,826,973 | 14,808,402,850 |

The county unspent section says “from FY2025/26”; the CoB section says
FY2024/25. Its much smaller balance is not silently treated as the annual
opening measure. Grants differ by **53,811,730**. The county's own FIF
cash plus receivables exceeds its printed accrual E by **75,231,007**.
Its ordinary OSR cash **367,738,513** plus receivables **33,742,595** also
exceeds printed accrual **372,412,223** by **29,068,885**.
The cash stream/grand difference is KES 1, but that does not cure scope or
accrual inconsistencies. Keep withholding; obtain an explicit correction
identifying FIF, opening/refund coverage, grant totals and edition.

## Migori: later draft explains the chart, with changed grant cells

The new CBROP DRAFT Table 1 spans rendered/printed pages 10–11; Table 2 is
rendered/printed 12. The actual-receipts column is Kshs. Known numeric grant
rows independently sum to **1,075,926,029**, equal to the printed subtotal.
This rounds to the CoB Figure 3.154 **1,075.93 million**. It is
**441,272,782** above the CoB table's known numeric nested subtotal sum
**634,653,247**; this differs from the old rounded-chart delta because the
new draft supplies exact precision.

The draft does not merely permit nested-layout parsing. It prints materially
different receipts and groups balances differently. The following comparison
accounts for the entire exact grants delta without filling a dash as zero:

| Receipt group | CoB PDF 546–548 known numeric cells | CBROP Table 1 actual cells | Difference between known numeric sums |
|---|---:|---:|---:|
| IDA FLLoCA | 132,681,904 | 190,095,093 | +57,413,189 |
| Four municipal development grants | Dash-marked; no known numeric receipts | 69,349,665 + 3 × 20,920,611 | +132,111,498 in newly numeric cells |
| NAVCDP plus named balances | 74,981,206 + 80,484,828 | 231,062,914 | +75,596,880 |
| KDSP II plus named balances | 35,253,471 + 35,250,118 | 255,307,630 | +184,804,041 |
| Livestock value chain | 8,652,826 | Blank actual cell | −8,652,826 removed from known numeric sum |

Remaining known amounts sum equally when the differently labelled PHCD/
DANIDA and KfW/FLLoCA balance lines are grouped; labels remain different
observations. Dash/blank cells above stay unobserved. The comparison measures
numeric evidence sets, not verified zero receipts or official reclassification.

The draft's Table 2 stream sum is coherent:
**104,964,463** carried forward + **8,883,939,720** equitable share +
**1,075,926,029** grants + **849,931,699** OSR/FIF/AIA + **59,562,562**
separate Equalization Fund = printed **10,974,324,473**. CoB PDF 549 instead
prints grand total **10,473,489,128**, lacks that separate Equalization Fund
stream, and its known numeric streams sum to **10,473,489,129**. The
unchanged OSR/FIF/AIA components are **301,042,055 / 542,211,636 / 6,678,008**.

The county draft is evidence supporting the chart's amount at printed
precision, but cannot certify the old conflicting table. Its later upload
does not establish adoption, a revised CoB edition, or authority to select
one receipt set. Keep the existing `a_section_has_two_subtotals` refusal.
The scanned OSR upload does not resolve grants or its own contradictory
period label.

## Nyeri: submitted receipts corroborate the lower equitable share

New Annex 1, PDF 38–39 / printed 37–38, reports equitable-share **disbursed**
**6,896,132,673**, also stated as received in PDF 7. This independently
supports the lower figure seen in the CoB target column/chart; it is
**89,000,000** below CoB Table 3.546 cash **6,985,132,673**. The ten numeric
county grant entries sum to **935,332,347**, matching CoB's grants subtotal;
equitable share plus those grants equals the county Annex 1 transfer total
**7,831,465,020**.

Annex 8 closes at PDF 48 / printed 47 with ordinary OSR **746,508,444**.
Its four quarterly totals **135,406,778 + 101,217,243 + 293,405,102 +
216,479,321** sum exactly to that amount. It is **67** above CoB's heading
**746,508,377**. This is a separately observed closing total, not authority
to fill the CoB closing subtotal, which remains blank.

The same page's Annex 9 separately reports Health Services Fund collections
**1,120,608,372.55** and unpaid claims **549,558,160.00**. Its four quarterly
collection totals reconcile; claims remain distinct from collected cash.
CoB's Nyeri narrative expressly describes ordinary OSR; its cash table does
not contain a matching Health Services Fund stream. Do not add the health
fund, copy its claims into cash, or splice county and CoB measures. County
PDF 7 mentions an expected budget balance **86,537,604**, while CoB's opening
cash is **285,064,165**; that forecast is not a substitute actual opening.
An exact corrected annual table/coverage statement is still required.

## Bounded search and verification limits

The fresh search used 12 official-domain queries: CoB FY2025/26 erratum,
corrigendum/revised/correction and named-county clarification; Kwale domains
with annual revenue/implementation/CBROP; Migori annual revenue/June/Q4;
Nyeri annual receipts/financial statements; Samburu annual/Q4/June/CBROP2026.
Exact query inputs are banked in `ROUND12_SESSION_4_SEARCH_INPUTS.json`;
returned candidates are in `ROUND12_SESSION_4_ROUND12SEARCH1.json` through
`ROUND12_SESSION_4_ROUND12SEARCH3.json`.
Read eight fresh official listings/pages, followed their source-linked
documents, and inspected five original documents. An initial Samburu locator
failed because its href is `#`; reading the page's actual `data-downloadurl`
located public ID 4471 successfully. No negative result was hidden.

Samburu's budgets/docs listings expose FY2025/26 Q1/Q2, earlier annual
reports and the wrong-period accrual statements above. No FY2025/26 annual
cash correction was found in this bounded search. The CoB listing/page and
official searches yielded no erratum or replacement edition. These are
bounded observations, not exhaustive proof that a clarification is absent.

`ROUND12_SESSION_4_CHECK.py` exited 0: checked all 15 captured-file hashes,
the retained annual SHA, banked 468-record receipt hash, source text/page
identity controls and Decimal arithmetic above. Its bank checks retain
**47 budgets / 43 cash totals**, all four absent cash totals, and Mombasa
cash **15,790,774,484** versus summary accrual **21,126.23 million**.
Those counts are inherited parser results, not a fresh parser replay.
No backend/settings imports, database connection, app fixture or full suite
ran. The read-only Word render exited 0; derivative pagination/rendering is
local evidence, not publisher edition identity.

An independent GPT-6.1 Sol/high reviewer inspected 29 source-page images,
checked source/derivative identities and page counts, and executed 26 exact
Decimal arithmetic assertions (exit 0). It confirmed the five-group Migori
delta and the continuing refusal decisions. Its receipts are
`ROUND12_SESSION_4_REVIEW_source_checks.json/.log/.py` and
`ROUND12_SESSION_4_REVIEW_REPORT.md`; no live application or production
acceptance was part of that review.

All new differences are duplicate candidates within #299 for coordinator
verification; no new issue or numeric correction was filed. Publication
impact is continued refusal to certify contradictory cash, not a newly
demonstrated production corruption. Human/production acceptance remains
separate. Actions, ingestion, cache refresh, source retirement and public
publication were not performed or authorized by this source investigation.
