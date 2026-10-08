# Evidence caller-label localization follow-up

Baseline: `a46ec977c4129149e7b2d6adecd9fd8dcb71e343`.

Copilot comment **4175752373 is UNDERSTATED**: translating the shared disclosure prose left descriptive application labels from its callers in English. The first fix covered the shared statuses and controls; this follow-up covers every descriptive FigureEvidence label authored in this work.

`labelKey` and `labelValues` now explicitly select translated display copy. `label` continues to define the original `data-figure-evidence` selector. There is no text/suffix inference or automatic translation of unknown record labels. Template substitution keeps raw county/sector names literal, including dollar sequences and placeholder-like text.

## Caller inventory

- Dashboard HeroSection, NationalDebtCard and DebtExplainerModal: debt register operands, GDP/ratio and debt timeline descriptors.
- DebtPageClient: register, published ratio, GDP and timeline descriptors.
- County BudgetTab and OverviewTab: budget descriptors, plus the newly authored GCP/poverty headings, headcount/extreme/Gini labels and missing-publication text. Reported values, dates, units and exact fact links are unchanged.
- CountiesPageClient and ComparePageClient: explicitly translated county-budget descriptors with raw county names as values.
- ExecutionAuditLens: explicitly translated allocation/expenditure descriptor with the raw sector name as a value.
- EconomicContextStrip: explicit evidence display keys for its GDP, budget/GDP and inflation cards; pre-existing unrelated card/section prose is unchanged.
- RevenueMix: translated revenue-by-period descriptor. Its individual row label remains the API's `measure ?? revenue_type` fact.
- Exact FigureEvidencePage: stable `this observation` selector with a localized display key.
- The remaining three unkeyed lender calls (NationalLoansCard and two DebtPageClient rows) preserve their existing raw lender-name display. No new FigureEvidence `loan register` label exists on this baseline; the separate pre-existing debt-page heading is outside this scoped change.

## Executed checks

Eight SW/plain regressions mounting actual county, sector, economic and dashboard callers were seen **red on the unchanged baseline**. They failed because the actual application labels/headings remained English. **Final targeted Jest: 46 passed across five files (10 new caller/template controls plus 36 existing controls).** The run also retains previous shared qualification/localization, comprehensive county facts and dashboard register controls. Two explicit-key controls preserve raw names and prove that an unkeyed matching English label is not guessed as application copy.

Scoped ESLint, TypeScript `tsc --noEmit --incremental false` and `git diff --check` pass. Author Jest retains the runtime-only React module map previously documented; repository dependencies and test configuration are unchanged. Logs are saved under `REMAINING_EVIDENCE_CALLERS_LOCAL` in the shared verification artifact directory. Root owns the fresh full frontend suite/build and frozen hosted acceptance; these were not repeated in this narrow author follow-up.

The [Kiswahili worksheet](2026-10-03-evidence-language-review.md) now appends **22 draft keys** (58 new keys across both localization commits). Human approval was subsequently recorded on 7 October 2026 (America/Chicago): the human user in the coordinator chat approved all 58 existing drafts without corrections. The [approval receipt](2026-10-07-evidence-swahili-approval.json) records the scope; language acceptance does not certify data or providers. The earlier approved 144 strings and #307/#372 work are unchanged. This completes the same review comment, with no separate issue filing or provider/GitHub/production writes.
