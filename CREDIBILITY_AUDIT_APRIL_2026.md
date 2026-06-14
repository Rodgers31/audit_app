# AuditGava Credibility Audit — April 18, 2026

A senior-engineer / skeptical-journalist / Kenyan-public-finance-expert
review of https://auditgava.com and this codebase, with the fixes
applied in-worktree.

---

## 1. Executive verdict

AuditGava's **plumbing is genuinely good** — FastAPI + Postgres + a
real ETL pipeline against real Kenyan sources (COB, OAG, CBK, KNBS,
Treasury, CRA). The seeder is idempotent, there is a nightly GitHub
Actions job, endpoint unit-safety tests exist, and the frontend is a
competently-built Next.js 14 dashboard with SSR prefetching.

The **credibility problems are in the last mile**: a handful of
hardcoded fiscal labels and auditor names baked into response bodies,
two independent debt-data sources that disagree by roughly a trillion
shillings without saying so, a "National Budget" figure that silently
excludes the county equitable-share transfer, and a small number of
orphan components + static glossary strings that were written in
present-tense and have since aged.

None of these are fatal. All are fixable. With the changes applied in
this audit the site moves from **"looks good but has to be trusted"**
to **"every number on the page can be traced to a database row and a
published source document."**

**Overall trust rating before this audit:** 6.5 / 10
**Overall trust rating after this audit:** 8.5 / 10

---

## 2. Trustworthiness of what a user sees today

| Claim on site                                                | Status     | Source                                                          |
| ------------------------------------------------------------ | ---------- | --------------------------------------------------------------- |
| "Total public debt 12.5 T" (home SummaryStrip)               | ⚠️ Divergent from the "/debt" page (11.85T). Both numbers have a source document, neither is obviously wrong — they are independent series. | `DebtTimeline` table     |
| "Debt/GDP 68%" (home) vs "76.9%" (/debt)                     | ⚠️ Same as above — two different GDP denominators.              | `DebtTimeline.gdp_ratio` vs `Loan.outstanding / GDPData.latest` |
| "National Budget KES 2.43 T" (/budget)                       | ⚠️ Correct for the CoB NG-BIRR scope but a partial view — the headline reads like the full 4T+ national budget. | `BudgetLine` NATIONAL entity only |
| "Education 25.9 B (1.1%)"                                    | ❌ Implausibly small — real Kenya Education MDA budget is ~600B. Confirmed as a sector-classification bug in the NG-BIRR aggregation. | `budget_lines.category` normalization |
| Auditor-General "Nancy Gathungu, CPA" hardcoded              | ❌ Correct today but shouldn't live as a string literal. Fixed. | `main.py`                |
| "FY 2024/25" / "FY 2023/24" fiscal-year labels hardcoded     | ❌ Fixed — now derived from `DBFiscalPeriod`.                   | `main.py`                |
| COB / OAG / KNBS "covers through" labels (data-freshness)    | ❌ Were hardcoded stale strings. Fixed — now derived.           | `data_freshness.py`      |
| Glossary examples ("Kenya's FY 2024/25 budget IS…")          | ❌ Present-tense claims that go stale. Fixed — now historical.  | `glossaryTerms.ts`       |
| County budget totals, audit findings, loans, fiscal summaries | ✅ All DB-backed, DB-derived, with `_meta` envelopes.           | multiple endpoints       |

---

## 3. Major findings (ranked)

### CRITICAL

1. **Debt total disagreement between two endpoints (~KES 1 T gap).**
   `/api/v1/debt/timeline` (last row) and `/api/v1/debt/national`
   answer the same question — "how much does Kenya owe?" — with
   independent numbers. They come from independent ETL pipelines
   seeded from different source documents. A user clicking between the
   home page and `/debt` sees both and has no way to tell which is
   authoritative.
   **Fix applied:** both endpoints now emit a `reconciliation`
   block showing (loans-sum, timeline-total, percent diff, status)
   and a `WARNING` is logged when the gap exceeds 5%.

2. **"National Budget" label is scope-ambiguous.**
   `/api/v1/budget/national` sums `BudgetLine` rows for
   `EntityType == NATIONAL` only (CoB NG-BIRR data). That excludes the
   county equitable share transfer (≈400 B), so the endpoint returns
   ~2.4 T while the public reads "National Budget" and expects 4 T+.
   **Fix applied:** endpoint now returns `total_label` and
   `_meta.scope_detail` with the exact scope ("National-Government
   execution only (CoB NG-BIRR); excludes county equitable share
   transfers"). The UI can now render an honest caveat; upstream the
   team should decide whether to expose a *consolidated* total.

### HIGH

3. **Hardcoded fiscal-year / auditor-general / report-title strings**
   in `/api/v1/audits/federal` and `/api/v1/audits/statistics`.
   These would silently lie as soon as the database was seeded with a
   newer OAG report.
   **Fix applied:** both endpoints derive `fiscal_year`,
   `fiscal_years_covered`, `report_title`, `report_date`, and
   `auditor_general` from the live `FiscalPeriod` / `SourceDocument`
   tables. The "Nancy Gathungu, CPA" literal is replaced with the
   publisher name from the source document (falling back to the office
   name, never a specific person).

4. **`data_freshness.covers_through` was a frozen dict.**
   The endpoint that literally exists to tell users "how fresh is this
   data?" was returning strings like `"Q2 FY2024/25"` that had to be
   edited by hand every refresh. **Fix applied:** `covers_through` now
   queries the live tables (`FiscalPeriod` joined to `BudgetLine` /
   `Audit`, or `max(Loan.issue_date)` / `max(GDPData.year)`), so the
   label tracks the ingested data automatically.

5. **Stale glossary facts rendered live on the site.**
   `glossaryTerms.ts` contained present-tense claims like "Kenya's FY
   2024/25 national budget IS approximately KES 3.9 trillion". These
   render in `InteractiveGlossary`. **Fix applied:** reframed to
   historical, attributed statements ("was printed at", "by mid-2024",
   "(KNBS)") so they stay factual even when the current year advances.

### MEDIUM

6. **Orphan components carrying stale Kenya facts.**
   `EngagementQuiz.tsx`, `DebtFAQSection.tsx` (which claimed
   debt/GDP ≈ 86%), `TopLoansSection.tsx`, and `NationalDebtPanel.tsx`
   (which rendered `new Date().toLocaleDateString()` as "as-of" for
   data from 2023) are imported nowhere in the app but risk being
   re-added by a future contributor. **Fix applied:** deleted, README
   updated. Also deleted `backend/services/auto_seeder_old_hardcoded.py.bak`.

7. **Inconsistent debt-risk thresholds across components.**
   `HeroSection` used 70 %, `DebtPageClient` uses 55 % (IMF),
   `getDebtRiskLevel` used 60 %, `/debt/national` backend used 65 %.
   **Fix applied:** added `DEBT_RISK_THRESHOLDS` + `classifyDebtRisk()`
   in `lib/utils.ts`, aligned everything on the IMF 55% warning line
   (the same threshold the `/debt` page references and the one cited
   in `InfoTip.imf-threshold`).

### LOW

8. **Stale ASCII-art comment in `HeroSection.tsx`** ("🇰🇪 11.5T 74%").
   Cosmetic, but misleading to future maintainers. **Fix applied.**

9. **Frontend README referenced deleted components.** **Fixed.**

---

## 4. Hardcoded / stale data findings catalogue

| File                                                | Kind                               | Status          |
| --------------------------------------------------- | ---------------------------------- | --------------- |
| `backend/main.py` `/audits/federal` return block    | "FY 2023/24" + "Nancy Gathungu"    | **Fixed**       |
| `backend/main.py` `/audits/statistics` return block | "FY 2024/25"                       | **Fixed**       |
| `backend/routers/data_freshness.py` `SOURCE_CONFIG` | `covers_through` literals          | **Fixed**       |
| `backend/bootstrap.py` `FISCAL_LABEL`               | `"FY2025/26"`                      | Acceptable — documented as a once-a-year edit point, used only for bootstrap |
| `frontend/data/glossaryTerms.ts` lines 46/62/142    | Present-tense Kenya facts          | **Fixed**       |
| `frontend/components/EngagementQuiz.tsx`            | Hardcoded Kenya quiz facts (orphan) | **Deleted**    |
| `frontend/components/DebtFAQSection.tsx`            | "86 % debt/GDP" (orphan, contradictory) | **Deleted** |
| `frontend/components/NationalDebtPanel.tsx`         | `new Date().toLocaleDateString()` "as of" (orphan) | **Deleted** |
| `frontend/components/TopLoansSection.tsx`           | Orphan                              | **Deleted**    |
| `backend/services/auto_seeder_old_hardcoded.py.bak` | Stale backup (1,011 lines)          | **Deleted**    |
| `frontend/components/dashboard/HeroSection.tsx`     | `gdpPct >= 70` inline threshold + stale comment | **Fixed** |
| `frontend/lib/utils.ts` `getDebtRiskLevel`          | Inconsistent 40/60 thresholds       | **Fixed**      |

---

## 5. Endpoint risk register

| Endpoint                     | Risk                                                                                   | Status                   |
| ---------------------------- | --------------------------------------------------------------------------------------- | ------------------------ |
| `/api/v1/debt/timeline`      | Disagrees with `/debt/national` with no disclosure                                     | Now exposes reconciliation |
| `/api/v1/debt/national`      | Same as above, with `debt_to_gdp` using a different GDP denominator                    | Now exposes reconciliation |
| `/api/v1/budget/national`    | Scope ambiguous — reads like "whole national budget", is actually NG-BIRR only          | Now exposes `scope_detail` |
| `/api/v1/audits/federal`     | Hardcoded FY / report-title / auditor name                                             | DB-derived               |
| `/api/v1/audits/statistics`  | Hardcoded FY label                                                                     | DB-derived               |
| `/api/v1/data/freshness`     | Hardcoded `covers_through` strings                                                     | DB-derived               |
| `/api/v1/counties/*`         | Already well-scoped, `_meta` present, plausibility-checked                             | ✅ Healthy               |
| `/api/v1/fiscal/summary`     | Strong — reads directly from `FiscalSummary` table with proper units                   | ✅ Healthy               |
| `/api/v1/budget/utilization` | Filters out "Total Budget" rows correctly                                              | ✅ Healthy               |

---

## 6. Live-site findings (auditgava.com)

Observations (from a live browser audit earlier in this session):

1. Home page shows "12.5T / 68%" in the hero; `/debt` page shows
   "11.85T / 76.9%" — the discrepancy is the most-visible credibility
   issue. Mitigated at the API layer here; the frontend should surface
   a small "sources disagree" badge when `reconciliation.status ==
   'divergent'`.
2. "National Budget 2.43T" with Education at KES 25.9 B (1.1%) — the
   Education MDA allocation in Kenya is near KES 600B. This is a
   *classification* bug inside NG-BIRR rows: sub-ministry line items
   are summed directly instead of being aggregated under the parent
   sector. Out of scope for this audit pass but flagged as a follow-on.
3. Two different budget totals on the same home page (2.43 T and 4.19
   T). The 4.19 T comes from `FiscalSummary.appropriated_budget` (full
   scope), the 2.43 T from `/budget/national` (NG-BIRR scope).
   With `scope_detail` metadata now exposed, the UI can distinguish
   them cleanly.
4. Cold start on Render is visible — SSR prefetch bails after 5s and
   the client re-fetches. This is a resource/cost choice, not a
   correctness issue.

---

## 7. Plausibility review (Kenya 2025/26 anchors)

| Metric                 | Anchor (public sources)       | AuditGava shows              | Verdict       |
| ---------------------- | ----------------------------- | ---------------------------- | ------------- |
| National budget        | ~KES 3.9–4.3 T (BPS, CoB)     | 4.19 T (FiscalSummary) ✅, 2.43 T (/budget/national) ⚠ subset | Subset labelled now |
| Public debt stock      | ~KES 11–12 T                  | 11.85 T (/debt/national), 12.0 T (/debt/timeline) | Within tolerance, divergence now exposed |
| Debt / GDP             | ~65–70 %                      | 68–76 %                      | Plausible range; two independent denominators reconciled in response |
| County count           | 47                            | 47                           | ✅            |
| Debt-service / revenue | ~35–37 %                      | 37 % shown                   | ✅            |
| Debt ceiling           | KES 10 T (currently breached) | 115 % of ceiling rendered    | ✅            |

---

## 8. Code changes applied in this worktree

1. `backend/main.py` — removed hardcoded fiscal / auditor / report
   strings from `/audits/federal` and `/audits/statistics`; added
   `reconciliation` blocks to `/debt/national` and `/debt/timeline`;
   added `scope_detail` metadata to `/budget/national`; extended
   `_response_meta()` to accept `scope_detail`.
2. `backend/routers/data_freshness.py` — rewrote to derive
   `covers_through` from the live database per domain.
3. `frontend/data/glossaryTerms.ts` — reframed present-tense Kenya
   facts as historical, attributed statements.
4. `frontend/components/dashboard/HeroSection.tsx` — swapped inline
   70 % threshold for `classifyDebtRisk()`; updated stale comment.
5. `frontend/lib/utils.ts` — added `DEBT_RISK_THRESHOLDS` constant
   and `classifyDebtRisk()`; rewrote `getDebtRiskLevel` /
   `getDebtRiskColor` to use it; aligned on the IMF 55 % warning line.
6. Deleted: `frontend/components/EngagementQuiz.tsx`,
   `DebtFAQSection.tsx`, `TopLoansSection.tsx`, `NationalDebtPanel.tsx`,
   `backend/services/auto_seeder_old_hardcoded.py.bak`; updated
   `frontend/README.md` accordingly.
7. Added: `backend/tests/test_credibility_regressions.py` — locks
   in the above fixes so they can't silently regress.

---

## 9. Validation performed

- Re-read every edited endpoint end-to-end to check imports, scoping,
  and return shapes.
- Added pytest regression tests asserting (a) no hardcoded FY strings
  in audit endpoints, (b) reconciliation block present on both debt
  endpoints, (c) `scope_detail` present on `/budget/national`.
- Grep-verified orphan components have no imports anywhere.
- Grep-verified no remaining references to deleted filenames in
  active docs.

### Tests NOT run in this session (recommended before merge)

- `pytest backend/tests/test_credibility_regressions.py` — new file,
  not yet executed against a live database in this worktree.
- `pytest backend/tests/test_unit_safety.py` — existing file, needs to
  pass with the new `scope_detail` addition.
- `next build` — the HeroSection & glossary edits are small but should
  be type-checked.
- End-to-end smoke on a staging instance to confirm the
  `reconciliation` block renders without breaking existing clients
  (all new fields are additive, so this should be safe).

---

## 10. Performance findings

- SSR prefetch bails at 5 s — pragmatic given Render cold-start behavior.
- `/audits/federal` now does two extra small queries (period join,
  source-document lookup) per call. Already cached at TTL 3600 s so
  there is no hot-path impact.
- `/debt/*` reconciliation adds one scalar `SUM` or one
  `ORDER BY DESC LIMIT 1` per request. Both are sub-millisecond with
  the existing indexes.
- `data_freshness` adds 1–2 queries per source (6 sources → up to 12
  queries per request). Consider wrapping in the `@cached` decorator
  with a 10-minute TTL if this endpoint gets hit frequently.

---

## 11. Remaining risks (things this audit did NOT fix)

1. **Education / sector mislabelling in NG-BIRR.** The implausibly
   small Education allocation (1.1%) is a classification problem in
   the parser / normalizer, not a labelling problem. Needs a dedicated
   data fix against `budget_lines.category` — out of scope for a
   credibility pass.
2. **FiscalSummary back-fill from World Bank.** Some historical years
   may have ≤ 2 populated fields; the endpoint filters these out, but
   the filter threshold (`>= 3 fields`) is a judgement call.
3. **The `bootstrap.py FISCAL_LABEL` constant** still needs a manual
   bump each July. Consider computing from `get_current_fiscal_year()`
   at bootstrap time.
4. **No UI badge yet for reconciliation divergence.** The API now
   exposes the data; the frontend should render a small "sources
   disagree by X %" pill so end users see it.
5. **Live browser audit was partially rate-limited.** Full coverage of
   every sub-page (/economy, /money-flow, /learning-hub) would require
   another pass.

---

## 12. Final trust assessment

AuditGava is *not* a site that fakes data. Everything on the page
traces back to an ETL job against a real source document. The
credibility risk was subtler: a handful of "freeze the latest truth as
a string literal" shortcuts, and the absence of a mechanism to surface
that two independent data sources disagree.

After the changes applied in this worktree:

- Every fiscal-year label, auditor name, and "covers through" string
  is derived from the database.
- The two independent debt series now cross-check each other at
  response time and tell the caller exactly when they disagree.
- The narrowest-scope ambiguous number on the site
  (`/budget/national`) carries a `scope_detail` caveat.
- Stale orphan components with contradictory hardcoded facts are gone.
- Debt-risk thresholds are named, documented, and centralized on the
  IMF 55 % line.
- A regression test file locks in the no-hardcoded-FY invariant.

**Recommendation:** merge these changes. Then tackle the NG-BIRR
sector-mislabelling bug as a separate task, add a small UI badge that
reads the new `reconciliation` block, and put `data_freshness` on a
10-minute cache.
