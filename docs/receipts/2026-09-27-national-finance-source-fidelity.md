# National finance source fidelity — 27 September 2026

Session 3, based on `origin/main` at `1bd397f398450245da83abc2e24502ab16ffb063`. This receipt describes code and local verification, not production adoption. No deployment, seeding, production write, merge or paid review was performed.

## Debt claims: #289 and #320

The premise that 55% is never an IMF benchmark was incorrect. [IMF Country Report 24/316](https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf#page=149), PDF p.149, paragraphs 27–28, uses a **present-value public-debt benchmark of 55%** for medium debt-carrying capacity. The report separately describes Kenya's statutory PV anchor. Neither justifies comparing the app's nominal WEO or CBK ratio to that benchmark. The [source correction](https://github.com/Rodgers31/audit_app/issues/289#issuecomment-5854337301) is recorded on #289.

Read-only production GETs on 27 September returned nominal debt/GDP 69.3% for 2025 alongside `threshold_imf=55`, `threshold_eac=50` and `status=above` at `/api/v1/debt/sustainability`. `/api/v1/fiscal/summary` independently returned `above_anchor=true` from the same nominal/PV comparison. The homepage repeated this as an anchor gauge and breach indicator.

The correction removes those numeric risk thresholds and comparisons, including the uncited 30% debt-service threshold and the debt page's 40/60 banding. Nominal ratios remain explicitly nominal. The DSA assessment is independent of these calculations and remains available when fiscal rows are absent.

The stored DSA is dated 18 October 2024, published 1 November 2024 (PDF p.132). Its latest recorded confirmation is the IMF register as of 31 March 2026. Automated access still returned 403; this work does not advance that date. A 180-day application review interval marks the confirmation as aging on 27 September. It is not an IMF expiry rule. Publication date, confirmation date and current-status qualification are visible beside each assessment.

### Required input evidence: #137

Executed reproduction: a `FiscalSummary` with debt service 20, revenue 100, a row-level document ID and `page_ref="p.1"`, but `meta={}`, returned HTTP 200 from `/api/v1/debt/sustainability` with a 20.0% debt-service ratio and both individual source fields NULL. The row's page can describe an appropriated budget; it does not establish both operands of this derived ratio. The narrow correction requires a URL and page locator for each of `debt_service_source` and `revenue_source`, and returns an explicit absence reason otherwise. It preserves the cited 20% result and genuine zero when both inputs have their own citations. No production count of affected rows was measured.

The separate `/api/v1/provenance/verify/fiscal_summaries?year=2025` branch explicitly verifies **appropriated budget**. A positive control with budget 100, its document/page, and NULL revenue correctly remains publishable for that budget; revenue is not a required input to this claim. It also qualifies that the document has not been fetched/validated. Missing revenue alone is not a defect in that route. The wider #137 provenance work remains open; this change does not certify every stored figure or source document.

## KRA: #298

KRA's [official annual-performance page](https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026) embeds the third-party dashboard. The hostname alone is no evidence of fabrication. Its bundle links a [KRA-hosted annual PDF](https://www.kra.go.ke/images/publications/FY25-26_Annual-Revenue-Performance_.pdf).

The committed fixture `backend/tests/fixtures/kra/fy2025_26_primary_source_comparison_298.json` records both artifacts, SHA-256 hashes, exact values, PDF pages and the read-only production receipt. In billion KES:

| Measure | Dashboard | KRA PDF | PDF page |
|---|---:|---:|---:|
| Total KRA collections | 2844 | 2844 | 3 |
| Exchequer | 2568 | 2568 | 10 |
| Agency | 276.139 | 276.135 | 11 |
| Domestic departmental collections | 1851 | 1851 | 12 |
| Customs departmental collections | 988.780 | 988.757 | 12 |
| PAYE | 598.807 | 598.803 | 13 |
| Domestic VAT | 355.255 | 355.255 | 13 |
| Corporation tax | 347.066 | 347.066 | 13 |
| Domestic excise | 61.845 | 61.844 | 13 |

Agency, Customs, PAYE and excise differ at the same displayed precision; these are not rounding of identical values to three decimals. No revision chronology was established. The dashboard's Exchequer plus agency total is 2844.139B; the 0.139B difference may reflect the rounded trillion totals. Domestic plus Customs is 2839.780B, leaving **4.220B unreconciled**.

The [FY2024/25 Customs release](https://www.kra.go.ke/news-center/press-release/2238-customs-surpasses-revenue-target,-records-remarkable-kshs-3-5-billion-average-daily-collection), paragraphs 1–5, includes Road Maintenance Levy 119.662B in the Customs narrative. The [audited KRA annual report](https://www.kra.go.ke/images/publications/KRA-AUDITED-FIN-STMTS-FY2024-25.pdf), PDF p.80 / printed p.15, Note 6(a), explicitly identifies RML as agency revenue. Its table contains **commission income in KES thousands**, not levy collections; those amounts cannot be subtracted from Customs. Nor can all agency revenue be subtracted from Customs, because agency collections span departments.

No source supplies the needed Customs-to-Exchequer allocation. The correction therefore withholds the app's `Other Tax Revenue` residual and partition shares, including historical stored rows at the public API boundary. Five publisher collection lines and publisher-stated total, Exchequer and agency measures remain separate. Each new dashboard observation keeps its source URLs, period, exact stated amount, retrieval time and content hash, with explicit non-reconciliation. No date is invented for publication. Failed publisher reads return no fixture replacement writes and record a partial run. Explicit withdrawal can clear an old residual; unavailable observations cannot relabel retained actuals with projection provenance.

### Proposed historical cleanup — not executed

The live API showed these residuals on 27 September:

| Unique key `(fiscal_year, revenue_type)` | Old amount, billion KES | Proposed amount |
|---|---:|---:|
| `FY 2022/23`, `Other Tax Revenue` | 174.60 | NULL |
| `FY 2023/24`, `Other Tax Revenue` | 222.40 | NULL |
| `FY 2024/25`, `Other Tax Revenue` | 181.20 | NULL |

FY2025/26 was projected and already NULL. Database IDs, extraction IDs and exact stored metadata were not obtained from this API receipt. This is a proposal by unique key, not a ready-to-execute database diff.

Before any authorized cleanup, read those exact three `revenue_by_source` rows and their referenced source/extraction records, resolve IDs, and export complete rows with a timestamp and checksum. Confirm exact keys, old amounts and the non-published residual basis. Review a diff that clears only each residual's amount, target, performance, growth and share, and adds the explicit incompatible-bases absence reason; preserve source/history links. Abort on missing, duplicate or changed rows. Apply only the reviewed IDs in one transaction with old-value predicates and an exact affected-row assertion. Re-read the rows and public API. Recovery restores the complete saved rows only if no newer observation has replaced them. The API guard protects readers before this cleanup, so a cleanup is not a deployment prerequisite.

## Fiscal accounting, periods and dates: #320 and #297

The [Treasury FY2026/27 Budget Summary](https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget%20Summary%20for%20the%20FY%202026_27%20Budget.pdf), Annex 2a, PDF p.63, is the source for the reconciliation fixture. The page was visually inspected as well as parsed.

| Fiscal column | Revenue incl. A-i-A | Grants | Expenditure and net lending | Published balance | Financing |
|---|---:|---:|---:|---:|---:|
| FY2026/27 Approved | 3629.7 | 43.6 | 4785.2 | −1111.8 | 1111.8 |
| FY2023/24 Actual | 2702.7 | 22.0 | 3605.2 | −880.5 | 818.3 |

All values are billion KES. Expenditure includes county transfers and contingency. FY2023/24 financing does **not** equal the negative balance: the source also prints cash-basis adjustment 45.4B and statistical discrepancy −16.8B. The endpoint preserves both amounts and checks both identities within the maximum 0.2B rounding allowance for four one-decimal terms. It does not substitute recurrent plus development or ordinary revenue for the complete fiscal column. Missing, malformed or unreconciled source columns remain explicit NULL gaps. Genuine zero survives.

Column labels are read only from the recognized header or the independently identified approved narrative. Unknown layouts say “Vintage unconfirmed.” The API and budget charts show Actual / Preliminary / Supplementary I / Approved per point. Source editions are distinct from fiscal years.

National period selection sorts start date, then end date (NULL last), then stable ID, all descending. The regression seeds a nine-month period plus two annual periods sharing the same start: old selection returned ID 1, corrected selection returns ID 3.

Register counts are described as creditor and instrument lines, not individual active loans. The legacy `total_loans` API key remains, with `count_basis=creditor_and_instrument_lines`. English, plain-English and Swahili labels were updated; competent Swahili review remains required under #307.

CBK's printed `05/10/2026` is retained as `publisher_date`, with its original text and `date_basis=publisher_date_meaning_unconfirmed`. `as_of` is NULL; retrieval time remains a separate field. This work does not guess auction versus value date or replace the publisher date with retrieval time.

## Verification and release boundary

Behavioral regressions were executed before and after the changes. The initial debt-claim file failed eight cases; the initial fiscal file failed eleven; the isolated tied-period case failed with ID 1 versus 3; three of four KRA reconciliation tests failed on the old behavior. Independent adversarial execution found invalid source-locator acceptance, rounding-boundary drift and stale notes after a small source revision. Corrections are covered by executed regressions.

Full backend run from `backend/`: **2914 passed, 10 skipped, 9 failed**. All nine failures are integration requests requiring PostgreSQL at localhost:5432. An untouched `origin/main` worktree independently produced the same nine failures, with the same connection-refused cause (baseline integration: 63 passed, 9 failed). This does not certify database-backed integration behavior. No production database was used.

After the final input-source correction, the focused backend run passed **275 tests**. Its independent source-evidence cases first produced 14 failures and 25 passes before the correction. Frontend: **547 passed across 52 suites**, TypeScript passed, ESLint passed. The new all-zero revenue-year regression also failed against unchanged main and passed after correction. Jest used `--forceExit` because of an existing open handle. Independent reviewers executed hostile numeric inputs, zero, absent/malformed metadata, missing source locators, source failure and explicit withdrawal paths.

Release remains separate: inspect current prerequisite heads, obtain CI on the final combined tree, deploy the API guards before any authorized seed, then verify the public debt, fiscal, revenue and loans payloads and corresponding UI. A refreshed fiscal/revenue seed is needed to add new source/column metadata to historical stored rows; until then unknown source versions and NULL outturn gaps are expected. Recheck the IMF register manually, and resolve KRA version differences with publisher evidence. Do not close production-dependent issues based on these local tests.
