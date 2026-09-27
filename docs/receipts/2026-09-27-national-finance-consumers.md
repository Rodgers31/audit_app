# National finance consumers and refresh readiness — 27 September 2026

Session 1 starts from `dc58685bb72007a5654863bfbeee912cfd6b89e3`. Read current #289, #274, #298, #320 and release tracker #323 before editing. No production seed, database mutation, deployment, document retirement, merge or paid review was performed. This is implementation prepared for review; production acceptance remains open.

## Debt page: #289 and #320

A real browser read of `https://www.auditgava.com/debt` reproduced `69.3% vs PFM Act 55%`. The component still colored its gauge at 40/60. Its missing-ratio fallback also manufactured 60.0% from a 12T register and 20T GDP in a rendering regression, without a compatible period or basis.

[IMF Country Report 24/316](https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf#page=149), PDF p.149 paragraphs 27–28, defines the 55% benchmark in **present-value** terms. PDF p.96 describes Kenya's separate statutory PV anchor. PDF p.132 dates the DSA 18 October 2024 and reports High overall and external risk. Neither supports classifying a nominal ratio with this page's 40/60 colors or comparing it with 55% PV.

The page now presents the finite, nonnegative API ratio with its own basis, observation year and source. It does not reconstruct a missing ratio from the register/GDP. Missing ratio, source, basis and year are explicit; reported zero survives. The independently sourced DSA remains linked and visibly dated. Malformed source/year metadata cannot crash React or render as a valid citation.

A real local browser rendering against the live read-only API showed `69.3%`, the nominal WEO basis, `Observation: 2025`, and the separate October 2024 DSA. Visual inspection confirmed the comparison and gauge are gone. This is **not** production adoption. The production homepage already showed the separate PV explanation and dated DSA; a component regression additionally found and fixed `null%` in its secondary debt card when both sources lack a ratio.

The public sustainability API at 20:03 UTC reports nominal 69.3%, year 2025 and the non-comparability explanation. `/fiscal/summary` reports `above_anchor: null` and an explicit absent-comparison reason. No API threshold was restored. Caller search found the old `assessDebtAnchor` helper has only test callers; it is not used by the debt page or current homepage. Other 40/60 hits concern county metrics and are outside this debt correction.

The IMF register was successfully downloaded this time. Its PDF still says **as of 31 March 2026**, with Kenya on row 27, publication 1 November 2024. The September retrieval does not extend that confirmation date, and the app's aging notice remains correct.

## Exact writer result: #274

The read-only production transaction at 20:02:40 UTC explicitly executed `SET TRANSACTION READ ONLY` and asserted `SHOW transaction_read_only = on`. Complete bounded rows were saved privately with checksum in the companion JSON. An earlier connection-option-only attempt failed that assertion and stopped before selecting rows; it made no writes.

| Record | Production before | Local replay using freshly fetched CBK rows |
|---|---|---|
| Document 2430 | National Treasury of Kenya; encoded bulletin URL | Same ID/URL, Central Bank of Kenya |
| Loans 381, 383, 384, 439 | Cite 1840 | Cite 2430; four balances unchanged |
| Loan 382 | 300B duplicate infrastructure/green-bond subset; cites 1840 | Removed by the already-merged aggregate/subset rule |
| Document 1840 | National Treasury of Kenya | Retained, no remaining loan references in this bounded replay |

**Loan 382 was not deleted by #318.** The local replay is not a production deletion. Document retirement belongs to Session 2/#319 after a fresh all-dependency manifest, recovery evidence and the required authorization.

A fixture-only control repaired three references but left 439 on 1840 and would replace current balances with older fixture amounts (for example, bonds 5578.9824B → 4564B). That control must not be used as a production refresh.

The live CBK discovery selected the December 2025 Statistical Bulletin from 45 listing candidates. Its Table 4.1.4, **PDF p.57**, reports gross domestic debt by instrument in **KES millions** for **December 2025**: bills 1,090,017.8; bonds 5,578,982.4; CBK overdraft 78,231.3; commercial-bank advances 11,420.4. The four parsed amounts are scaled to raw KES. The companion JSON records the exact artifact hash. These are four instrument aggregates, not individual loans.

This actual live path reproduced a remaining #274 defect: discovery returns literal spaces in the PDF URL, but document 2430 stores `%20`. The merged writer matched exact strings, created another document, and left 2430 mislabeled. The correction matches literal spaces and `%20` identically while preserving reserved encodings such as `%2F`, publisher declarations, separate source editions and existing IDs. It does not perform general URL decoding or delete duplicate documents. The live four-row replay then repaired 2430 and all four references.

The homepage also hardcoded the link caption `Treasury` while pointing at CBK. The caption now says `Source` (existing `Chanzo` wording in Swahili), preserving its supplied URL. That rendering fix is independent of database attribution.

## Source/version and fiscal evidence: #298 and #320

The companion [machine-readable receipt](2026-09-27-national-finance-consumer-evidence.json) records freshly downloaded artifacts, SHA256s, observations, parsed values and the local writer result. KRA's official page still embeds the dashboard. Its bundle and annual PDF match the hashes in the earlier primary-source comparison fixture; Agency, Customs, PAYE and Domestic Excise still differ at their stated precision. No revision chronology was established.

The real `_read_release` path followed the official page to its iframe and bundle, preserved the linked KRA-hosted PDF, recorded retrieval time `2026-09-27T20:08:11.123700+00:00`, bundle hash and `dashboard_bundle` version, and left publication date null. The overlay produced five stated collection lines, three stated totals and an explicitly withheld Other Tax Revenue row. All partition shares remain null. This is a read/parse result, not a database publication. The live public API already withholds Other Tax Revenue for FY2022/23 through FY2025/26; stored historical cleanup remains separate.

Treasury's FY2026/27 Budget Summary is unchanged at SHA256 `1e24992d34cb4dddefd4ad04c3f77055e6be976b8b326256a17b5312725a550b`. The actual downloaded PDF was parsed and reconciled on Annex Table 2a, PDF p.63:

| Column | Revenue incl. A-i-A | Grants | Expenditure/net lending | Balance | Financing |
|---|---:|---:|---:|---:|---:|
| FY2023/24 Actual | 2702.7 | 22.0 | 3605.2 | -880.5 | 818.3 |
| FY2026/27 Approved | 3629.7 | 43.6 | 4785.2 | -1111.8 | 1111.8 |

All amounts are **billion KES**. The actual-year cash adjustment 45.4B and statistical discrepancy -16.8B reconcile the different balance/financing figures. Source columns and accounting bases stay distinct; reported contingency zero in the Actual column remains zero. An initial local probe supplied a wrong ordinary-revenue join input, 2292.4B, and the parser correctly refused it. The PDF row prints 2288.9B; that observed input passed. Nothing was written by either probe.

Production `/dashboards/national/fiscal-outturns` still has five explicitly absent columns marked `Vintage unconfirmed`, plus 24 historical rows withheld for missing page references. `/fiscal/summary` current is FY2026/27 with `fiscal_framework: null`. New column metadata has not been ingested; the draft does not substitute invented actuals for those gaps.

## Verification

- Debt-page rendering: baseline **10 failed / 5 passed**, including valid controls. Malformed metadata regression before the guard: **15 failed / 20 passed**. Final debt-page cases: **35 passed**.
- Homepage null-ratio regression: **1 failed / 8 passed** before; corrected suite passed. Source-link regression: **2 failed / 4 passed** before; **6 passed** after.
- URL-identity regression: **2 failed / 12 passed** before; **14 passed** after. The actual live domestic replay failed with a new document before and passed with the same document ID after. The disposable SQLite replay is not PostgreSQL or production acceptance.
- Full frontend Jest suite: **749 passed across 68 suites**. It printed the existing open-handle warning after passing. TypeScript and focused ESLint passed.
- Focused backend checks: **103 passed** across source attribution, debt writer/fetcher/register and national fiscal/KRA/DSA behavior. No PostgreSQL claim is made for the SQLite writer fixtures.
- Independent verification executed **41 frontend hostile/control cases** and **20 direct writer cases**, all passing after the fixes. Reserved URL characters, distinct publication/query versions, publisher absence, document type, equivalent duplicates and stable IDs were exercised.
- Session 5's combined production Next build + isolated real FastAPI Chromium run: **11 passed**, including all **3 debt acceptance specs** added here. The temporary component/spec copies were restored from Session 5's tree after the run. Log: `/tmp/session5-browser-combined.log`. This proves integration in the local fixture-backed environment, not the production refresh loop.
- Independent execution also confirmed a preexisting direct-writer limitation: missing URL **and** null/empty title create a new default-titled document on each call. It reproduces on unchanged main and remains outside this narrowly sourced URL correction; no current production occurrence was established. Record it under the existing source-writer issue, without claiming that all possible malformed-source paths are fixed.

### Draft review follow-up

Copilot's PR #341 overview flagged a missing debt-chart ratio. The actual homepage `CustomTooltip` rendered a bare `%` for a hoverable timeline row with a null ratio, rather than the literal `null%` in the overview. The real `/debt/timeline` route emits null for missing `gdp_ratio` while retaining the row's debt totals. A tooltip render fixture captured the chart's transformed row and Recharts content element: **1 failed / 2 passed** before the fix; **3 passed** afterward, preserving reported zero and 65.9%. The related homepage suites passed **20/20**; TypeScript and focused ESLint passed. The timeline ratio type now reflects the nullable API, and the tooltip shows `—` for absence. `/debt`'s separate debt-service tooltip already checks null.

A controlled endpoint probe found a separate backend zero-loss path: a stored `DebtTimeline.gdp_ratio=0` returned `gdp_ratio: null` from `/debt/timeline` (HTTP 200). This was recorded as [#346](https://github.com/Rodgers31/audit_app/issues/346) after duplicate-issue search; the temporary probe was removed and the backend route was not changed in this draft. No production zero occurrence was established.

## Remaining release sequence

1. Review and merge/deploy the draft consumer and writer fixes. Production still shows the old debt-page comparison until then.
2. Session 5 must establish shared signed invalidation configuration and demonstrate backend invalidation before frontend refresh. It reported no approved fallback and no verified configuration at this check.
3. Stage the **full** national-debt payload and exact database delta, including external-creditor reconciliation, bond-register replacement, affected IDs, backup/recovery and drift checks. The domestic-only replay is not authorization or a complete manifest for generic `national_debt`. Never use the fixture-only control.
4. Coordinate serial bounded `national_debt`, `fiscal_summary` and `revenue_by_source` publication with Session 5, `run_bootstrap=false`, after each source/version and proposed delta is accepted. Capture before/after IDs, artifact/version/hash, observation metadata, coverage/refusals, database and public-API results.
5. Verify rendered debt/home/budget after refresh, including missing-input cases. Give Session 2 the fresh document-reference state; do not retire 1840 based on a local replay. Keep #289, #274, #298 and unfinished #320 scope open until their production acceptance passes.
