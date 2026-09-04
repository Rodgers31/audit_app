# CREDIBILITY_FINDINGS.md

**Adversarial pre-launch review of https://www.auditgava.com**
Run 2026-09-03 against live production (frontend `www.auditgava.com`, API
`https://audit-app-4pwa.onrender.com/api/v1`) and against `main` at `8376bf7`
(working tree clean apart from untracked briefs).

Read as a hostile reader would: a Treasury official with the COB report open, a
journalist with the CBK bulletin, a county finance officer looking up their own
county. Every finding below carries a `file:line` or a command and its real
output. Nothing here is inferred from a docstring or a design note.

---

## 0. Corrections to the brief's stated premises

The brief asked me not to re-derive its seed findings but to re-run the probes.
Four of them do not survive re-testing. Correcting them matters because two of
them point at the wrong defect.

| Brief said | Actually |
|---|---|
| "`MetricsStrip.tsx:50` and `DebtOverviewCard.tsx:129` both render Total Debt as of `{latestYear}`" | **Neither component is mounted on any route.** `grep -rn "MetricsStrip\|DebtOverviewCard" app components lib` returns only their own definitions plus the barrel export in `components/dashboard/index.ts:7,12`. The homepage renders `HeroSection` (`app/HomeDashboardClient.tsx:35`). |
| "the label showing 2025 means the newest debt datapoint is 2025" | The homepage's "as of" year is **the GDP observation year, not the debt vintage**: `components/dashboard/HeroSection.tsx:121` → `const year = apiData?.gdp_year ?? latest?.year`. The debt figure beside it comes from `total_outstanding` whose `last_updated` is `2026-04-26`. The label and the number describe different things. |
| "Follow the Money is empty at the API… returns identically for 2024, 2025 and 2026 (note: the param is `year`, not `fiscal_year`)" | The parameter takes a **fiscal-year string**, not a calendar year. `?year=2024` returns all-null; `?year=FY2022/23` returns `Allocated 370000000000.04, Spent 273621886278.19, efficiency_score 73.95`. Four fiscal years have data. This is **not** an empty domain — it is an endpoint that answers an unrecognised parameter with a well-formed "no data" object instead of a 400 (finding **F36**). |
| "The string APPD appears nowhere in backend/ or frontend/ source… It is therefore rendered from data" | The string is **APDMR** and it is hardcoded in the frontend: `components/budget/BudgetFlowHero.tsx:243` → `Treasury APDMR · {fy}`. The zero beside it is a `?? 0` fallback (**F2**), not a database row. |

One more, about my own instrument: the `/debt` hero counter read **KES 12.85T**
against the same page's **KES 13.55T** on six other elements. That is *mostly*
my browser pane — `document.hidden === true` throttles `requestAnimationFrame`
to **0 frames/sec** (measured), freezing the count-up mid-flight. But the
underlying design defect is real and is reported as **F28**.

---

## 1. Ranked findings — worst first

"Worst" = most likely to discredit the whole site when one reader checks one
number. Class: **A** no source exists · **B** source exists, not ingested ·
**C** ingested, no endpoint · **D** endpoint exists, UI doesn't consume ·
**E** displayed but wrong/mislabelled/undeclared basis · **F** stale ·
**G** zero/placeholder where the value is unknown.

| # | Page / section | What is shown | What is true | Class | Sev | Receipt |
|---|---|---|---|---|---|---|
| F1 | `/audits` hero | **UNSUPPORTED EXPENDITURE — KES 73.4B** | A sum of *account balances* quoted as context inside findings, not amounts questioned. Top contributor is a payables balance on which the AG wrote "My opinion is **not** modified in respect of this matter". | E | **Critical** | `backend/seeding/domains/audits/loader.py:165`; `GET /audits/federal` → top 5 amounts below |
| F2 | `/budget` **default landing view** (FY2026/27) | Tax revenue **KES 0B · 0.0%**, Non-tax **KES 0B**, New borrowing **KES 0B**, Debt service **KES 0B · 0.0%**, Development **KES 0B**, Counties **KES 0B**, "Treasury APDMR · FY 2026/27 **KES 0.0** of every KES 100 of revenue services the debt" | All six are `null` in the API. Kenya's tax revenue is not zero and its debt service is not 0% of revenue — the site itself publishes 65.3 for FY2025/26. | G | **Critical** | `components/budget/BudgetFlowHero.tsx:78-94` (`?? 0` × 7); live DOM read below |
| F3 | Homepage hero + `/debt` dual card | **TOTAL DEBT AS OF 2025 · KES 13.55T · Source: CBK / National Treasury** | CBK's published stock for Dec 2025 is **KES 12.299T** — which the site's *own* `/debt/timeline` serves. 13.55T is a 28-row internal loan register, attributed to CBK. | E | **Critical** | `components/dashboard/HeroSection.tsx:115-118,145`; `GET /debt/timeline` 2025 total = `12299476400000` |
| F4 | Homepage vs `/debt` | Home: **EXTERNAL KES 6.03T (44.4%)** / **DOMESTIC KES 7.55T (55.6%)**. `/debt` treemap: **EXTERNAL 47.9% KES 6.49T** / **DOMESTIC 52.1% KES 7.06T**. `/debt` sustainability panel: **External share 44.4%**. | The loan rows sum to external 6.522T / domestic 7.059T. The 6.03T shown on the homepage is the **CBK percentage split applied to the loan-register total** — a number in no source document. Two external-debt figures 460B apart, on the same site; two on the same page. | E | **Critical** | `backend/main.py:8937-8945` |
| F5 | `/debt` sustainability + peer strip | **Kenya — Service / Revenue 0.0%** (IMF threshold 30%), and **0.0%** in the peer strip below Rwanda 7.7%, Uganda 21.0% | `debt_service_to_revenue` is `null` in the API. The code's own fallback constant for Kenya is **57.6**. The site shows Kenya as the best debt-servicer in East Africa on the metric where it is worst. | G | **Critical** | `app/debt/DebtPageClient.tsx:321` `?? 0`; `GET /debt/sustainability` → `"debt_service_to_revenue": null` |
| F6 | County pages → Projects tab | 25 named "stalled projects" against 21 counties, each with an **OAG case reference** (`OAG/MSA/2023/HLT-004`), amounts, % complete, and a narrative cause ("Contractor abandoned site after payment disputes; pending arbitration") | A hand-written fixture. **All 25** records have `paid/contracted` equal to an exact whole percent, drawn only from {20,30,40,50,60}. The fetcher itself records `mark_fixture(reason="no_live_source", … "for which no extractor exists yet")`. No OAG report was ever read. | E | **Critical** (legal) | `backend/seeding/real_data/stalled_projects.json`; `backend/seeding/domains/stalled_projects/fetcher.py:48-58` |
| F7 | `/counties/compare` vs `/counties/[id]` | Mombasa: **KES 14.6B budget, 49.8% executed, KES 783M pending bills** on Compare; **KES 9.42B, 32.0%, KES 4.65B** on Mombasa's own page. Nairobi pending bills: **KES 3.96B** vs **KES 90.73B**. | Two endpoints publish different numbers for every county. Systematic — 6/6 sampled. | E | **Critical** | table in §2.7 |
| F8 | `/debt` "Two measures of public debt" | **BROADER MEASURE — IMF GENERAL GOVERNMENT — KES 12.29T … Includes counties, SOE debt, pension arrears, and pending bills** | The "broader" measure is **KES 1.26 trillion smaller** than the "narrower" one beside it. Self-refuting on its face. | E | **Critical** | `components/dashboard/NationalDebtCard.tsx:325-333`; `GET /debt/broader` → `value_kes 12293230950000` |
| F9 | `/debt` "AUDIT TRAIL" / "Sources & Reconciliation" | "a **9.3% gap typical for line-level vs. roll-up data**" and "The two totals disagree because Treasury's aggregate is published after consolidation adjustments — forex revaluation…, T-bill rollovers in transit, and **pending bills yet to be booked**" | An invented accounting explanation for a data defect. The backend's own note says the tables "are seeded from **different source documents**". The explanation also runs the wrong way: it predicts the aggregate should be *larger*; it is smaller. | E | **Critical** | `components/debt/DebtSourceReconciliation.tsx:200-206`; suppression of the honest note at `:209-215`; `backend/main.py:9012-9017` |
| F10 | `/debt` peer comparison | **SERVICE / REV** "% of tax revenue going to debt repayment", vs "IMF 30%". **EXTERNAL** "% of debt held by foreign lenders (FX-exposed)" — Rwanda **94%** | Both are the wrong World Bank indicator. `GC.XPN.INTP.RV.ZS` is titled by the World Bank **"Interest payments (% of revenue)"** — interest only, no principal. `DT.DOD.DECT.GN.ZS` is **"External debt stocks (% of GNI)"** — Rwanda's external debt is 94% *of its GNI*, not 94% of its debt. | E | **Critical** | `backend/main.py:10169-10173`; verification calls in §2.10 |
| F11 | `/sectors`, every county page, `/budget` outer ring | Health **25.0%**, Education **20.0%**, Roads **15.0%**, Water **10.0%**, Agriculture **8.0%**, Administration **7.0%**, Trade **5.0%**, Environment **4.0%**, Social **3.0%**, Other **3.0%** | One hardcoded template. **1 distinct sector-share signature across all 47 counties.** `/sectors` is titled "WHERE COUNTIES ACTUALLY SPEND" and its methodology box describes a label-normalisation step that cannot be running. | E | **Critical** | computation in §2.11 |
| F12 | `/transparency` FY2024/25 | **KES 1.36T allocated** to 47 counties; **Nairobi KES 111.1B**, Nakuru 57.7B, Narok 43.3B | ~2.4× the neighbouring years on the same endpoint (FY2022/23 370.0B, FY2023/24 385.0B, FY2025/26 405.1B). Named counties with budgets far above anything published. | E | **Critical** | `GET /money-flow/all-counties?year=FY2024/25` |
| F13 | Homepage debt chart | "Kenya's National Debt · **2013–2025** · Source: Central Bank of Kenya & National Treasury"; **"4.0× since 2013"**; **"From 58.4% in 2013"** | 2013–2021 are **nine consecutive round hundred-billions** (3,100 / 3,600 / 4,300 / 5,000 / 5,400 / 5,800 / 6,500 / 7,200 / 8,200 B). No CBK publication produces those. Both headline claims rest on the fabricated 2013 base — and **understate** the deterioration. | E | **High** | `backend/seeding/real_data/debt_timeline.json`; `GET /debt/timeline` |
| F14 | Homepage "Where Your Taxes Go" | **Education KES 624.7B — 33.3%** of the national budget; Health **5%** | The denominator is KES 1.88T, a partial COB NG-BIRR measure — not the KES 4.69T gross NG budget the site publishes elsewhere. A reader concludes a third of Kenya's budget goes to education. Scope note is present but sits under the number. | E | **High** | `GET /budget/national` `_meta.scope_detail` |
| F15 | County pages → Budget & Debt | **World Bank (County Infrastructure) — KES 6.33B — 81.2% of total debt** (Mombasa); KES 13.11B (Nairobi) | The string exists **nowhere in the repository** (grep over 1,611 files, positive-controlled). An orphaned production row asserting county-level World Bank liabilities. Counties cannot borrow externally without a national guarantee (Art. 212 / PFM Act s.58). | E | **High** (legal) | §2.15 |
| F16 | `/sources` | "**Every figure** on AuditGava traces back to a document…"; "Every extracted value retains a provenance pointer — the source document ID and page reference — so you can **trace any county's budget execution number** back to the original COB quarterly report" | `GET /provenance/verify/budget_lines` → `{"detail":"Unknown table: budget_lines. Supported: population_data, gdp_data, audits, loans"}`. The one thing the sentence promises is the one table the verifier cannot do. `population_data` returns `verification_status: "unverified"`. | E | **High** | §2.16 |
| F17 | `/sources` "Data health" | All 10 datasets **Healthy**; caption "Green means the table is **fully populated from its source**" | A row-count floor with no freshness input. `status="healthy" if poverty_count >= 1` — **one row turns Poverty Data green**. `>= 5` for the debt timeline. A check that cannot fail. | E | **High** | `backend/routers/data_provenance.py:316,326,341,357,369,378,392,402,410` |
| F18 | Homepage vs `/sources` | Hero: "**updated nightly** from official sources" | `/sources` in the same session: National Treasury **LAST FETCHED 4 months ago**, OAG **6 months ago**, County Treasury **1 years ago**, National Treasury (loans) **2 years ago** — and every row still reads "Healthy". | F | **High** | `GET /sources/summary` `last_fetched` values |
| F19 | `/debt`, homepage, explainer modal | "CBK's Statistical Bulletin (**June 2025** issue, the most recent published)"; "CBK Public Debt Statistical Bulletin — **April 2025**"; "**As of Apr 2026**" | The seeded source is the **December 2025** bulletin (Tables 4.1.3/4.1.4, PDF pp. 56-57). Three different vintages claimed for one source. The code comment admits it: *"The 'June 2025 issue' string is currently static"*. | E | **High** | `app/debt/DebtPageClient.tsx:746-747,755`; `components/dashboard/DebtExplainerModal.tsx:115`; `DATA_CORRECTIONS_2026-08-29.md` §1-2 |
| F20 | `/learn/government` | "Counties receive **at least 15 % of national revenue**"; "The CRA **ensures** fair sharing of revenue" | Art. 203(2)-(3): not less than 15% of revenue **raised nationally**, based on **the most recently audited** accounts approved by the National Assembly — typically 2-3 years behind. Omitting "audited" makes the site's own 415B/2,910B look like a constitutional breach. Art. 216: CRA **recommends**; Parliament decides via DoRA/CARA. | E | **High** | live DOM |
| F21 | `/audits` hero | **IRREGULAR EXPENDITURE KES 0**; **ADVERSE/DISCLAIMER OPINIONS 0**; **Recurring Findings — 0 patterns** ("the real scandals") | `|| 0` on absent fields. The only opinion value the parser produced is "Unmodified Opinion", so "0 adverse" is a parser artefact rendered as a finding that every audited entity was clean. | G | **High** | `app/audits/AuditsPageClient.tsx:217,224,230` |
| F22 | `/transparency` FY2022/23 | **QUESTIONED BY AUDITOR GENERAL — KES 0 — "No flagged findings"** — directly beside the waterfall's own "OAG audit report **not yet published** for this year / data unavailable" | The same panel says both "not published" and "zero findings". The KPI exonerates 47 county governments on the strength of an unpublished report. | G | **High** | live DOM, §2.22 |
| F23 | County pages KPI + Overview | **0 AUDIT ISSUES**; **AUDIT SNAPSHOT — 0 critical, 0 warning, 0 info**; Audit Findings tab **"0 Total Findings"** | `findings_count: 0` means no audit has been ingested. The adjacent **Accountability** tab handles this correctly ("An absent grade is not a low grade… This is not a finding that the county is clean"). Two tabs, opposite conventions. | G | **High** | `GET /counties/047/comprehensive` `audit.findings_count` |
| F24 | `/debt` "When the bills come due" | "**BIGGEST WALL — 2034 — KES 2.28T**"; "Showing **3 loans** with published maturity dates across 2026–2037"; then "**Revolving & pooled instruments — Continuously rolled over**" listing World Bank IDA, AfDB, JICA, AFD, KfW | A refinancing ladder built on 3 of 28 rows, with five separate Eurobond issues collapsed onto one date. Multilateral and bilateral **project loans are amortising term debt with fixed maturities** — they are not revolving instruments. | E | **High** | `GET /debt/national` `categories.*.items[]` (no `year`), live DOM |
| F25 | `/debt` treemap | 7 category shares summing to **106.9%** (43.3+21.0+19.7+8.0+7.4+6.9+0.7), under "TOTAL OWED KES 13.55T · 7 categories" | `percentage_of_total` divides by a total that **excludes** `pending_bills`, while pending bills is rendered as one of the parts. The same 931.3B is also the "NATIONAL" half of the page's separate "Stalled payments — KES 1.13T". | E | **High** | `backend/main.py:9070-9076`; §2.25 |
| F26 | `/debt` peer strip | **Ethiopia — "Within sustainable band" — 31%** | World Bank `GC.DOD.TOTL.GD.ZS` for **2019** — seven years stale, and *central-government* debt while Kenya's 70% is General-Government. IMF WEO 2025 for Ethiopia is **43.1**. Ethiopia has been in sovereign default / G20 Common Framework restructuring since Dec 2023. | E | **High** | §2.10 |
| F27 | `/budget` flow, all years | **"Other financing"** 16–23% of every historical budget (FY2025/26 **KES 870B**), and **100.0%** for FY2026/27; **"Counties KES 415B"** inside a 4.69T envelope | `otherFinancing = Math.max(0, budget − tax − nonTax − borrowing)` — a residual plug, given the tooltip "Grants, drawdowns, carryover balances, one-off receipts" as if it were sourced. And COB's gross budget **excludes** the county equitable share by definition, so "Counties" cannot be a slice of it. | E | **High** | `components/budget/BudgetFlowHero.tsx:87,89`; `DATA_CORRECTIONS_2026-08-29.md` §3 |
| F28 | `/debt` hero counter | Headline debt rendered by a JS count-up starting at **60% of the true value** with no static fallback | `useMotionValue(value * 0.6)`. Measured: with `document.hidden`, `requestAnimationFrame` runs at **0 fps** and the headline froze at **KES 12.85T** for 8+ seconds while six other elements on the page read 13.55T. Affects background tabs, prerenders, thumbnails and social-preview captures. I did not verify the recovery-on-visible path. | E | Medium | `app/debt/DebtPageClient.tsx:101,106`; measurement in §2.28 |
| F29 | `/budget/enhanced` (API) | `total_population: 907025674`; `per_capita_budget_kes: 6048` | Kenya's population is ~57.5M — the site's own `/economic/population/latest` says `57532493`. The API publishes a figure ~16× too high and a per-capita budget ~16× too low. **Not currently rendered** (declared but unused at `components/budget/EconomicContextStrip.tsx:27-29`) — but it is public API. | E | Medium | `GET /budget/enhanced` |
| F30 | `/budget/national` (API) | `development_budget: 59130000000` | Exactly equal to the **"Agriculture, Rural and Urban *Development*"** sector line. `recurrent_budget` is the remainder. COB states FY2025/26 ministerial development at **KES 744.84B** — 12.6× larger. String match, not classification. **Not currently rendered on `/budget`** (the page uses `fiscal_summary`), so latent. | E | Medium | `GET /budget/national`; `DATA_CORRECTIONS_2026-08-29.md` §3 |
| F31 | `/fiscal/summary` (API) | `debt_ceiling: 10000000000000` and `debt_ceiling_usage_pct: 125.0` on FY2022/23–FY2025/26; `actual_debt` 9.1 / 10.2 / 11.49 / **12.5T** | The KES 10T ceiling was repealed in 2023 — **the homepage says so**. And `actual_debt` is the pre-correction series that `DATA_CORRECTIONS_2026-08-29.md` replaced (2023: 10.2T vs CBK's 11.14T; 2025: 12.5T vs 12.299T). Two "Kenya total debt by year" series in one API. `debt_ceiling_usage_pct` is not currently rendered. | F | Medium | `GET /fiscal/summary`; `lib/api/fiscal.ts:31-42` |
| F32 | Homepage county card, county pages | **"Financial Health 42.9/100"** beside **"Budget Utilisation 42.9%"** | `financial_health_score == budget_utilization` for **47/47 counties**. Two differently-labelled metrics that are the same number. | E | Medium | §2.32 |
| F33 | `/learn/why-it-matters` | "**Youth Fund Money That Vanished** — How **KES 300 million** meant for youth employment disappeared"; "left **800 children** without a school for 3 years" — under the heading **"Real Stories, Real Impact"** | Invented figures on a site whose promise is that every figure traces to a document. The composite disclaimer is present but sits above cards headed "Real". The Youth Enterprise Development Fund is a real named institution. | E | Medium | live DOM |
| F34 | `/audits` "Top 10 Worst Offenders" | Column header **"County"**, rows are State Departments and the **Executive Office of the President**. Heading calls them "**Worst Offenders**" | Directly contradicts the page's own standing caveat two elements below ("Questioned ≠ confirmed loss… queries to be resolved, not proven theft"). `kenya-legal`: use audit terminology, not accusation. | E | Medium (legal) | `app/audits/AuditsPageClient.tsx:260` |
| F35 | County pages → Budget & Debt | Sector "spent" figures | Sector spend sums to **154%** of Baringo's own `total_spent` (Bomet 108%, Bungoma 88%, Busia 71%). Sector allocations sum to only **62–71%** of the county's stated budget, unlabelled. Mombasa: **"RECURRENT KES 9.42B"** = 100% of the budget while "DEVELOPMENT — Unavailable". | E | Medium | §2.35 |
| F36 | `/audit/money-flow/national` | `?year=2024` → every stage `null`, `data_unavailable: true`, HTTP 200 | The parameter is a fiscal-year string. An unrecognised value returns a well-formed "no data" object rather than a 400. A caller cannot distinguish "no data published" from "you passed the wrong thing" — which is exactly what happened to the brief that commissioned this audit. | — (no-silent-fallbacks) | Medium | §0 |
| F37 | `/transparency` | Default state is **"FOLLOW THE MONEY · FY 2026/27 — No data yet"**; FY2026/27 **is not one of the seven picker buttons**. The CRA source card still says "County Equitable Share — FY 2026/27 · **PUBLISHED** · Feeds: Allocated" | The landing state of the page is an empty year the reader cannot select, under a provenance card claiming a published source feeds a null stage. | D | Medium | live DOM |
| F38 | `/sources` | **"PUBLISHING AGENCIES 17"** | The list contains "Office of the Auditor General" *and* "Office of the Auditor-General"; "National Treasury Kenya", "National Treasury of Kenya", "National Treasury"; "Controller of Budget", "National Treasury & Controller of Budget", "Office of the Controller of Budget (OCOB)". ~9 distinct publishers counted as 17. | E | Low | `GET /sources/summary` |
| F39 | `/audits` table & facets | Page 1 = 20 rows, 11 identical "Teachers Service Commission / REPORT ON THE FINANCIAL STATEMENTS / — / info", all amounts "—". Finding-type facet has **12 near-duplicate values** differing only in case/punctuation, plus a raw enum **`financial_audit`** | The flagship findings table's first screen carries no information; the type filter is unusable. | E | Low | live DOM |
| F40 | `/audits` footer vs homepage | "Data as of: **17 Feb 2026** | Source: OAG"; homepage "**813** findings"; `/audits` "**TOTAL FINDINGS 814**"; `/sources` OAG "LAST FETCHED **Today**" | Three inconsistent counts/dates for one dataset. | F | Low | live DOM |
| F41 | County Overview | **"TOTAL REVENUE KES 8.32B · Local: KES 8.32B"** (Mombasa) | Presents the whole figure as own-source revenue. A county's largest revenue line is the equitable share, not local collection. `revenue_collection` is a modelled field. | E | Low | `GET /counties/047` |
| F42 | Homepage loans card | **"ANNUAL SERVICE COST KES 1.27T"**; rows with `interest_rate: null` render **"0.00% — KES 0"** | The total is Σ(outstanding × assumed rate) — **interest only**, on representative rates attached to synthetic aggregate rows, labelled "service cost" (which includes principal). Null rates render as 0.00%. | E/G | Low | `GET /debt/national` `categories.domestic_overdraft.items[].interest_rate = null` |
| F43 | `/status` | — | Returns **307 → `/?authRequired=1`**. Not publicly reachable; no public-credibility exposure. | — | Info | `curl -o /dev/null -w "%{http_code} %{redirect_url}"` |

---

## 2. Detail, per finding

Only findings whose evidence needs more than a table cell are expanded.

### F1 — "KES 73.4B unsupported expenditure" is a sum of account balances

**On screen (`/audits`):** `UNSUPPORTED EXPENDITURE / KES 73.4B`, and
`Top 10 Worst Offenders → 3. Executive Office of the President — KES 13.7B`.

**The mechanism**, `backend/seeding/domains/audits/loader.py:164-165`:

```python
amounts = payload.get("amounts") or []
amount = amounts[0] if len(amounts) == 1 else None
```

If a finding paragraph contains exactly one `Kshs.` figure, that figure becomes
`amount_involved`. There is no test of what the figure *means*. `_AMOUNT_RE` at
`backend/seeding/extractors/oag_blue_book.py:80` matches every `Kshs.` token in
the paragraph body.

**What that produces.** The five largest of the 49 findings that carry an
amount (`GET /audits/federal`), which together are 60% of the 73.4B:

| Entity | Amount taken | What the OAG paragraph actually says |
|---|---:|---|
| Executive Office of the President | 13,656,423,839 | "the statement of financial position reflects a **balance** of Kshs.13,656,423,839 in respect of trade and other payables… **My opinion is not modified in respect of this matter.**" |
| State Dept for Immigration | 8,690,152,710 | "made various **procurements worth** Kshs.8,690,152,710. However, the State Department did not deduct… the **0.03%** capacity building levy" — the sum at issue is ~KES 2.6m |
| State Dept for Medical Services | 7,993,113,605 | "reflects **employee costs** amount of Kshs.7,993,113,605. However… **181 employees** earned a net salary of less than a third of their basic pay" |
| State Dept for Medical Services | 7,993,113,605 | **the same balance again**, for a separate finding about disability staffing — double-counted |
| State Dept for Immigration | 5,966,074,772 | another **payables balance** |

So the headline is: two payables balances, a procurement value, and one payroll
balance counted twice. The homepage carries a correct caveat ("this is what the
findings themselves add up to — not the report's headline figure"); `/audits`
drops it and calls the number **"Unsupported Expenditure"**.

**Publisher that should govern it:** Office of the Auditor-General, *Report on
National Government FY2024/25* (the site holds the PDF and the page refs —
`page_ref: "p.106"`, `"p.136"`, `"p.272"`). **Source exists.**

**Smallest change that makes it honest:** stop publishing an aggregate. Rename
the tile to "Amounts cited in findings" or withhold it, and remove the "Worst
Offenders" ranking, until an extraction rule distinguishes *amount questioned*
from *balance discussed*. The honest interim is `—` plus the reason, exactly as
`/accountability/missing-funds` already does.

---

### F2 — Eight hard zeros on the default `/budget` view

**Verified by DOM read on the live page** (viewport asserted at 1280×900 and
again at 375×812; no horizontal overflow at either):

```
Treasury APDMR · FY 2026/27  KES 0.0  of every KES 100 of revenue services the debt
Tax revenue        KES 0B · 0.0%
Non-tax revenue    KES 0B · 0.0%
New borrowing      KES 0B · 0.0%
Other financing    KES 5.49T · 100.0%
Debt service       KES 0B · 0.0%
Recurrent (ex-debt) KES 0B · 0.0%
Development        KES 0B · 0.0%
Counties           KES 0B · 0.0%
Other (CFS etc.)   KES 5.49T · 100.0%
```

`components/budget/BudgetFlowHero.tsx:78-94`:

```ts
const revenue    = data?.total_revenue      ?? 0;
const tax        = data?.tax_revenue        ?? 0;
const nonTax     = data?.non_tax_revenue    ?? 0;
const borrowing  = data?.total_borrowing    ?? 0;
const debtService= data?.debt_service_cost  ?? 0;
...
const debtServicePct = revenue > 0 ? (debtService / revenue) * 100 : 0;
const debtServiceCents = data?.debt_service_per_shilling ?? Math.round(debtServicePct);
```

`GET /fiscal/summary` → `current` (FY 2026/27) has `total_revenue: null`,
`tax_revenue: null`, `total_borrowing: null`, `debt_service_cost: null`,
`development_spending: null`, `county_allocation: null`. The API is correct and
withholds. **The frontend converts every withheld value to zero.**

`DATA_CORRECTIONS_2026-08-29.md` explains *why* they are null and says so
deliberately: *"The FY2026/27 row has no revenue… Left null until the revenue
series gets the same basis treatment."* The ETL made the right call; the UI
undoes it.

**Smallest change:** replace every `?? 0` in `BudgetFlowHero` with a null-aware
segment that renders `—` and greys the bar. The component already has `fmtT()`
returning `'—'` for null at `:50` — it is simply never reached.

Note the picker works (my first click missed the button; a DOM click switched
FY correctly). FY2025/26 and earlier render real numbers. **The broken state is
the default landing state.**

---

### F3 / F4 — The debt headline and the split

`GET /debt/national` — verified arithmetic:

```
sum(category principal, excl. pending_bills) = 13,580,833,964,464 == total_debt      ✓
sum(category outstanding, excl. pending)     = 13,552,833,964,464 == total_outstanding ✓
categories external (principal)              =  6,522,182,064,464   (48.0%)
categories domestic (principal)              =  7,058,651,900,000   (52.0%)
summary.external_debt                        =  6,030,992,448,694.595
summary.domestic_debt                        =  7,549,841,515,769.405
implied external share                       =  44.408%
CBK Dec-2025 5,462.0 / 12,299.5              =  44.408%   ← identical
```

`backend/main.py:8937-8945`:

```python
# Correct the external-vs-domestic DIRECTION using the
# authoritative CBK aggregate (DebtTimeline). The loan register
# ... under-represents domestic instruments (T-bonds/bills) ...
external_debt = _base * (_tl_ext / _tl_split)
domestic_debt = _base * (_tl_dom / _tl_split)
```

The comment concedes the loan register is wrong, then keeps its **total** while
borrowing CBK's **ratio**. The result — KES 6.031T external — appears in no
document. `/debt`'s treemap ignores the rescaling and shows the raw category
sums (6.49T / 47.9%), so the two pages disagree and `/debt` disagrees with
itself.

The headline pairing is also internally impossible: **KES 13.55T** next to
**69.3%** implies GDP of 19.55T, while the same payload reports
`gdp: 17,577,557,000,000`. 13.55/17.58 = **77.1%** — which the API carries as
`debt_to_gdp_computed_central_gov` and the UI does not use.

**Smallest change:** publish one basis end to end. Either make the CBK
aggregate (12.299T, external 5.462T, domestic 6.838T) the headline everywhere
and keep the loan register as an instrument-level detail, or withhold the
external/domestic split until the register is complete. Do not blend.

---

### F5 — Kenya shown as East Africa's best debt-servicer

`GET /debt/sustainability` → `"debt_service_to_revenue": null` at top level,
`24.3` inside the Kenya peer row. `app/debt/DebtPageClient.tsx:321`:

```ts
const topServiceToRev = extractNum(raw.debt_service_to_revenue) ?? 0;
```

Rendered at `:850` in the ring gauge and `:334-336` in the peer strip. On
screen: `0.0%  IMF 30%  Service / Revenue`, and `🇰🇪 Kenya … SERVICE / REV 0.0%`
against Rwanda 7.7%, Uganda 21.0%, Tanzania 13.9%, Ethiopia 12.6%.

The code's own "verified fallback" constant for Kenya (`backend/main.py:10313`)
is **57.6**.

---

### F6 — Fabricated OAG references against named counties

`backend/seeding/real_data/stalled_projects.json` — 25 records. Signature:

```
records where paid/contracted is an exact whole percent: 25 of 25
distinct values of that percent: {20, 30, 40, 50, 60}
```

`_meta` claims `"source": "Office of the Auditor General - County Government
Audit Reports FY2022/23 & FY2023/24"`, `"scraped_at": "2025-01-15"`.

`backend/seeding/domains/stalled_projects/fetcher.py:48-58` records the truth
into the pipeline:

```python
mark_fixture(
    "stalled_projects",
    reason="no_live_source",
    detail=(f"{len(projects)} record(s) from the in-repo fixture; source is "
            f"OAG audit reports, for which no extractor exists yet"),
)
```

The UI nonetheless renders them under `SOURCES: … Audit` and
`data_sources.stalled_projects: "OAG Audit Reports & County Assembly
Committees"`.

Rendered example (Mombasa, Projects tab):
> *Mombasa County Referral Hospital Expansion · Health · **OAG/MSA/2023/HLT-004** ·
> Stalled · 28% complete · KES 740.0M / KES 1.85B · Started 2020 · Expected 2023 ·
> "Funding gaps due to pending bills backlog from previous fiscal years"*

`kenya-legal`: *"Make accusations not supported by official documents"* and
*"Extrapolate beyond what the audit report states"* are both DON'Ts. A cited
case number is an assertion that a document exists.

**Smallest change:** delete the Projects tab and the homepage "N Stalled
Projects" card until an OAG extractor exists. There is no labelling that
rescues a fabricated case reference.

---

### F7 — Every county has two published budgets

```
county            list_budget    comp_budget   list_ut  comp_ut   list_pending   comp_pending
Nairobi          44,620,890,000  22,903,924,446   72.0     34.2     3,957,365,700  90,726,565,700
Mombasa          14,630,000,000   9,419,375,168   49.8     32.0       782,999,784   4,650,699,784
Baringo           9,542,030,000   7,129,183,006   42.9     54.6       240,034,680     586,334,680
Kiambu           26,831,320,000  14,533,696,456   47.2     39.0     1,131,499,980   9,019,399,980
Nakuru           22,397,400,000  13,453,098,060   48.0     51.6     1,089,749,808   4,766,949,808
Homa Bay         13,601,450,000   9,096,366,604   50.0     33.4       407,502,000   2,045,702,000
```

`list` = `GET /counties` → homepage map, `/counties`, `/counties/compare`.
`comp` = `GET /counties/{id}/comprehensive` → the county's own detail page.
Both label the period **FY2025/26**.

Direction is not even consistent: Baringo's and Nakuru's utilisation is *higher*
on the detail page, everyone else's is lower. Nairobi's pending bills differ by
**23×**.

A reader on `/counties/compare` sees Mombasa at 49.8% executed with KES 783M of
pending bills, clicks the county name, and lands on 32.0% and KES 4.65B.

**Smallest change:** make `/counties` and `/counties/compare` read
`comprehensive`, or vice versa. One number per county per period.

---

### F9 — The reconciliation panel explains away its own defect

Rendered on `/debt` (`components/debt/DebtSourceReconciliation.tsx:200-206`):

> "The two totals disagree because Treasury's aggregate is published after
> consolidation adjustments — forex revaluation on external debt, T-bill
> rollovers in transit, and pending bills yet to be booked into the instrument
> register. Treasury reconciles these at year-end. We use the live loan register
> as the headline because it's tied directly to the CBK bulletin our ETL parses
> daily — so the number you see moves when CBK publishes fresh data."

Against:
- `backend/main.py:9012-9017` — *"The two tables are seeded from **different
  source documents**."*
- The stated mechanism predicts the aggregate should be **larger**. It is
  1.25T **smaller**.
- "our ETL parses daily" — `/debt/national` `last_updated` is **2026-04-26**.
- `:209-215` explicitly decides to keep the backend's honest note out of the UI.

---

### F10 / F26 — The peer table, verified against the source APIs

```bash
curl "https://api.worldbank.org/v2/country/KEN;ETH;TZA;UGA;RWA/indicator/GC.XPN.INTP.RV.ZS?format=json&per_page=100&date=2015:2026"
# indicator name: "Interest payments (% of revenue)"
# ETH 2024 12.6 | KEN 2023 24.3 | RWA 2023 7.7 | TZA 2024 13.9 | UGA 2024 21.0
```
→ exactly the site's "SERVICE / REV" column, labelled *"% of tax revenue going
to debt repayment"* and compared against an **IMF 30% debt-service** threshold.
Interest excludes principal redemption, which for Kenya is the larger half.

```bash
curl ".../indicator/DT.DOD.DECT.GN.ZS?..."
# "External debt stocks (% of GNI)"
# KEN 2024 35.0 | RWA 2024 93.9 | TZA 2024 47.3 | UGA 2024 39.2 | ETH 2022 24.3
```
→ exactly the site's "EXTERNAL — % of debt held by foreign lenders" column.
Rwanda's **94%** means external debt ≈ 94% of GNI. Ethiopia's value is from
**2022** while the rest are 2024, undisclosed.

```bash
curl ".../indicator/GC.DOD.TOTL.GD.ZS?..."   # "Central government debt, total (% of GDP)"
# ETH 2019 31.4 | UGA 2024 54.4     (no recent TZA/RWA observation)
```
→ Ethiopia's **31%** and Uganda's **54%**. Tanzania 48.2 and Rwanda 67.2 are the
**hardcoded fallback constants** at `backend/main.py:10318,10330`. Kenya's 70.0
is the site's own CBK-derived ratio.

So one row is a 2019 World Bank central-government figure, one is 2024, two are
in-repo constants, and Kenya is on a fifth basis — presented as one comparison
under "Sources: IMF WEO, World Bank IDS (via WDI)". The `or` chain
(`backend/main.py:10352-10358`) leaves no flag saying which is which.

IMF WEO 2025, which the site already ingests for `/debt/broader`, has
ETH 43.1, TZA 49.7, UGA 54.2, RWA 64.6, KEN 69.3. **None of the four peers on
screen matches it.**

Also: the panel is titled "Kenya in the East African context" / "EAC peer
average" and includes **Ethiopia, which is not an EAC member**, while omitting
Burundi, South Sudan, DRC and Somalia, which are.

---

### F11 — One sector template for 47 counties

```python
# across GET /counties, per county: share of each sector in the sector total
distinct sector-share signatures across 47 counties: 1
  Health Services 25.00% | Education 20.00% | Roads and Public Works 15.00%
  Water and Sanitation 10.00% | Agriculture 8.00% | Administration 7.00%
  Trade and Industry 5.00% | Environment 4.00% | Social Services 3.00% | Other 3.00%
```

`/sectors` aggregates the same template: Health 101.3B / 405.1B = **25.0%**,
Education 81.0/405.1 = **20.0%**, Roads **15.0%**, Water **10.0%**, …

The page is titled **"WHERE COUNTIES ACTUALLY SPEND"** and its methodology box
says:

> "Counties use slightly different labels ("Health Services", "Health &
> Sanitation", "Medical Services" all appear). We normalise them into 10
> canonical sectors so cross-county comparison is apples-to-apples. For each
> county we use its latest fiscal period that has **actual execution recorded**
> — so the numbers reflect **money already spent**, not just allocated."

None of that can be happening: every county already has the identical ten labels
and the identical ten shares. This is AUDIT_FINDINGS **F5.2 and pattern P2**,
still live in production, on the page that consists entirely of the artefact.

The county pages render it to one decimal — `25.0% / 20.0% / 15.0%` — so two
counties opened side by side falsify it in one glance.

---

### F13 — Nine fabricated years on the homepage chart

`backend/seeding/real_data/debt_timeline.json`, `metadata.source =
"Central Bank of Kenya Annual Reports & National Treasury Budget Policy
Statements"`:

```
2013 ext 1500 dom 1600 total 3100    2018 ext 2900 dom 2900 total 5800
2014 ext 1700 dom 1900 total 3600    2019 ext 3200 dom 3300 total 6500
2015 ext 2100 dom 2200 total 4300    2020 ext 3600 dom 3600 total 7200
2016 ext 2500 dom 2500 total 5000    2021 ext 3900 dom 4300 total 8200
2017 ext 2700 dom 2700 total 5400
```

`GET /debt/timeline` confirms 2013–2021 are still these values in production;
only 2022–2025 were replaced with real CBK figures by the August correction.
The chart caption reads **"2013–2025 · Source: Central Bank of Kenya & National
Treasury"**.

Two homepage claims are computed off the fabricated base:
- **"4.0× since 2013"** = 12,299 / 3,100
- **"From 58.4% in 2013"** = 3,100 / 5,311

Both *understate* the deterioration they are meant to dramatise.

---

### F15 — A World Bank loan to a county, with no provenance anywhere

`GET /counties/047/comprehensive` → `debt.breakdown[0]`:

```json
{"lender": "World Bank (County Infrastructure)", "category": "other",
 "principal": 8000000000.0, "outstanding": 6334420131.22, "interest_rate": null}
```

Nairobi: `outstanding 13,114,825,391.23`. Rendered on the Budget & Debt tab as
*"World Bank (County Infrastructure) — KES 6.33B — 81.2% of total debt"*.

```bash
grep -rn "County Infrastructure" . --exclude-dir={node_modules,.git,venv}   # no matches
# positive control on the same invocation:
grep -rn "Likoni-Mtongwe" . --exclude-dir={node_modules,.git,venv}
#   backend/seeding/real_data/stalled_projects.json:51 ...            (1,611 files scanned)
```

The grep can find things; it cannot find this. The rows exist only in the
production database. `data_sources.debt` claims *"National Treasury - County
Debt Register"*.

---

### F16 — The provenance promise, falsified by the provenance endpoint

`/sources` states: *"Every extracted value retains a provenance pointer — the
source document ID and page reference — so you can trace **any county's budget
execution number** back to the original COB quarterly report or OAG audit."*

```bash
GET /provenance/verify/budget_lines
  {"detail":"Unknown table: budget_lines. Supported: population_data, gdp_data, audits, loans"}
GET /provenance/verify/debt_timeline
  {"detail":"Unknown table: debt_timeline. ..."}
GET /provenance/verify/population_data
  {"source_document": null, "source_url": null, "publisher": null,
   "verification_status": "unverified", "reason": "no resolvable source document"}
GET /provenance/verify/loans
  {"source_document": "CBK Public Debt Statistical Bulletin — April 2025",
   "source_url": "https://www.centralbank.go.ke/public-debt/", "fetch_date": null}
```

Four separate defects in one probe: the two tables behind the homepage chart and
every county budget figure are **not verifiable at all**; `population_data`
returns `unverified` while `/sources` shows it **Healthy**; and the one table
that does verify names the **wrong bulletin** and points at a listing page, not
a document.

---

### F17 — A health panel that cannot go red

`backend/routers/data_provenance.py`:

```python
:316  status="healthy" if county_count      >= 47
:326  status="healthy" if budget_count      >= 400
:341  status="healthy" if audits_with_year  >= 50
:357  status="healthy" if pop_count         >= 48 and nat_pop
:369  status="healthy" if gdp_count         >= 5
:378  status="healthy" if econ_count        >= 5
:392  status="healthy" if poverty_count     >= 1        # ← one row is "Healthy"
:402  status="healthy" if loan_count        >= 50
:410  status="healthy" if debt_tl_count     >= 5
```

No freshness term anywhere. `GET /provenance/health` currently returns
`overall: healthy` with all ten green. The page caption promises something
else — *"Green means the table is fully populated from its source"* — and the
intro promises *"If a feed goes stale, we flag it"*, next to rows reading
"LAST FETCHED **1 years ago**".

`STAGE3_PROMPT.md` records that `seeding/staleness.py` replaced exactly this
pattern (*"row-count floors (`27 >= 20` passes forever)"*) inside the pipeline.
The public-facing panel never got the same treatment.

Also note "Debt Records — Healthy — **172 rows**" while `/debt/national` reports
`loan_count: 28` and `/debt` shows 15.

---

### F22 — "KES 0 — No flagged findings" beside "not yet published"

`/transparency`, FY2022/23 selected. Same panel, verbatim:

> Of which the Auditor General flagged — **OAG audit report not yet published
> for this year** — Flagged · OAG: irregular, unsupported, or wasteful — **not
> yet published** — **data unavailable**
>
> … QUESTIONED BY AUDITOR GENERAL — **KES 0** — **No flagged findings**

The waterfall is honest; the KPI tile beside it converts the same null into a
finding of zero. The API is correct (`stages[2].amount: null`,
`data_unavailable: true`); `app/transparency/TransparencyPageClient.tsx:271-273`
does `?? 0` on all three stages.

Same panel: **"NATIONAL EFFICIENCY 74.0% — Good — above target"** — an editorial
verdict on an absorption rate, with no target named.

---

### F25 — A pie whose parts sum to 107%

```
Domestic Bonds 43.29 + External Multilateral 20.96 + External Commercial 19.70
+ Domestic Bills 8.03 + External Bilateral 7.36 + Pending Bills 6.86
+ Domestic Overdraft 0.66  =  106.86%
```
under `TOTAL OWED KES 13.55T · 7 categories`.
`backend/main.py:9070-9076` divides each category by `total_debt`, which is the
sum of the other six. `pending_bills` is simultaneously a slice of the debt
treemap **and** the "NATIONAL KES 931.3B" half of the page's separate
"Stalled payments — TOTAL MONEY OWED, UNPAID KES 1.13T".

Related: `summary.county_guaranteed = 0` is served but **not rendered anywhere**
(`grep -rn "county_guaranteed" app components lib` → no matches), so the brief's
"hard zero on display" is API-only. It still violates Rule 1 for API consumers.

---

### F28 — The debt headline depends on an animation completing

`app/debt/DebtPageClient.tsx:101,106`:

```ts
const mv = useMotionValue(value * 0.6);          // first paint = 60% of the truth
useEffect(() => { const c = animate(mv, value, { duration, ease: [...] }); ... });
```

Measured on the live page:

```js
let frames=0; const t0=performance.now();
const tick=()=>{frames++; if(performance.now()-t0<1000) requestAnimationFrame(tick);};
requestAnimationFrame(tick); await new Promise(r=>setTimeout(r,1200));
// → { hidden: true, visibilityState: "hidden", framesIn1s: 0 }
```

With 0 fps the counter held **KES 12.85T** across eight one-second samples while
`KES 13.55T` appeared six times elsewhere on the same page. There is no static
fallback: if the animation never runs, the page states a wrong national-debt
figure with no indication. `app/globals.css:402` only neutralises **CSS**
animations, so `prefers-reduced-motion` does not reach this. I did not verify
whether the value corrects itself once a background tab is brought forward.

---

### F32 / F35 — County arithmetic that does not close

```
financial_health_score == budget_utilization for 47 of 47 counties
development_budget == recurrent_budget      for 18 of 47 counties
(dev + rec) / total_budget                  = 0.47 – 0.67   (never 1.0)
Σ(sector allocated) / total_budget          = 0.62 – 0.71
Σ(sector spent) / total_spent               Baringo 1.54 · Bomet 1.08 · Bungoma 0.88 · Busia 0.71
```

Baringo's sector-level spending is **154% of Baringo's own reported total
spending**, inside a single API record. Mombasa's detail page reads
`DEVELOPMENT — Unavailable · Not classified in source data` beside
`RECURRENT KES 9.42B` (= 100% of the budget), while `/counties/compare` says
Mombasa's development share is **30.4%**.

---

### The county-page provenance contradiction (spans F7, F11, F15)

Every county page carries this disclaimer, which is good and correct:

> "**Modelled estimate — not official Controller of Budget figures.** County
> budget allocations use the Commission on Revenue Allocation (CRA)
> equitable-share formula. The county debt and pending-bill figures are
> modelled: they are not county-reported actuals…"

and then, ~200px below it, the execution card reads:

> **Source: Controller of Budget · FY2025/26**

and the API declares `data_sources.budget = "Controller of Budget - County
Budget Implementation Review Reports"`. The Follow-the-Money tab attributes the
same allocation to two different publishers in one panel — `source: "CRA
Allocation + Conditional Grants"` in the stage, and `SOURCE 2025 Budget Policy
Statement — County Equitable Share Projection` in the footer.

---

## 3. What is already right — preserve it, and copy it

These are the internal standard the rest of the site should be held to.

- **`/accountability/missing-funds`** is exemplary. "TOTAL FLAGGED — *Not yet
  published*", "**3 cases held back for lack of a traceable source document**",
  and "**An empty tracker is not a finding that public money is fully accounted
  for.**" AUDIT_FINDINGS F5.3 was fixed properly.
- **The county Accountability tab**: "No grade can be given yet… **An absent
  grade is not a low grade**", "This is **not** a finding that the county is
  clean."
- **The homepage OAG card**: "AUDIT OPINION NOT YET PUBLISHED HERE… This is not
  a finding that the national accounts are clean", plus the correct caveat on
  the 73.4B.
- **`/transparency` waterfall copy**: "Budget still available — not yet paid out
  at report time. **Not missing.**" and "a query, not proven loss or theft."
- **`_meta.scope_detail`** on `/budget/national`, and `budget_basis` +
  `budget_basis_source` on every `fiscal_summary` row, with quote, page and
  cross-checks. That is best-in-class provenance — it is just not reaching the
  page.
- **The seeding layer's `mark_fixture` / `mark_live` instrumentation** told me
  the truth about stalled projects before I looked at the data.

The gap is not capability. Every honest pattern in this list already exists in
this codebase. The failures are places where a component reached for `?? 0`, or
where prose was written to smooth over a number the pipeline had correctly
flagged.

---

## 4. Withdraw before launch

Cannot be made truthful in the time available; a blank is honest, these are not.

1. **`/audits` "Unsupported Expenditure KES 73.4B" tile and the "Top 10 Worst
   Offenders" table** (F1, F34). The number does not mean what the label says
   and the ranking names the Executive Office of the President on a matter the
   AG declined to modify.
2. **The Projects tab and the "N Stalled Projects" cards** (F6). Fabricated OAG
   case references against 21 named counties.
3. **`/sectors` in its entirety, and the county "Sector Spending" panels**
   (F11). The content is a hardcoded template under a heading that says it is
   actual spending.
4. **The `/debt` peer comparison and the "Can Kenya keep paying?" ring gauges**
   (F5, F10, F26). Two of three metrics are the wrong indicator; the third mixes
   five bases; Kenya's own service ratio renders 0.0%.
5. **The "Revolving & pooled instruments" list and the maturity ladder** (F24).
   Three instruments cannot support a refinancing-wall chart, and IDA/AfDB/JICA
   project loans are not revolving.
6. **`/debt` "Two measures of public debt" + "Audit trail" strip** (F8, F9)
   until the reconciliation copy is replaced by the backend's own note.
7. **The county "World Bank (County Infrastructure)" debt rows** (F15).
8. **`/learn/why-it-matters` "Youth Fund Money That Vanished — KES 300 million"
   and the other invented figures** (F33), or strip the amounts.
9. **`/budget` FY2026/27 as the default year** (F2) — land on FY2025/26 until
   the FY2026/27 revenue series exists.

## 5. Label before launch

Correct or defensible figures whose basis is unstated. Cheap, and this is where
most of the debt and budget risk sits.

1. **Every "total debt" figure needs its basis in the label** (F3, F4, F8).
   "KES 13.55T — loan register, 28 aggregate instruments" vs "KES 12.30T — CBK
   Statistical Bulletin, Dec 2025, central government gross". Pick one for the
   headline. Today the site says "Source: CBK" over a number CBK does not
   publish.
2. **Debt-to-GDP must name its basis wherever it appears** (69.3% IMF General
   Government vs 70.0% CBK/timeline vs 77.1% central-gov/GDP), and must not sit
   beside a debt total from a different basis.
3. **"Above the 55%-of-GDP anchor"** on the homepage compares a *nominal* ratio
   against a *present-value* anchor. `/debt` states this caveat correctly; the
   homepage does not. Copy the `/debt` wording.
4. **"Total Debt as of {year}"** must use the debt vintage, not `gdp_year`
   (`HeroSection.tsx:121`), and must say the underlying bulletin is Dec 2025.
5. **Fix the source vintage in three places** (F19): "June 2025 issue",
   "April 2025", "As of Apr 2026" → the December 2025 bulletin, ideally plumbed
   from the parser's `measurement_date` as the code's own TODO says.
6. **"Where Your Taxes Go"** (F14) needs its denominator in the heading, not
   under the number: "Education 33.3% **of the KES 1.88T ministerial
   allocation**", or restate on the 4.69T gross basis.
7. **"Other financing" and "Other (CFS etc.)"** (F27) must be labelled as
   computed residuals — the "Where the money goes" donut already does this
   correctly ("a computed balancing item — not a separately sourced line"). Use
   the same wording on the flow bars, and move "Counties" outside the NG gross
   envelope.
8. **County pages** (F7): one budget per county per period. Whichever endpoint
   wins, remove "Source: Controller of Budget" from figures the page's own
   disclaimer says are modelled.
9. **Homepage debt chart** (F13): either truncate to 2022–2025, or mark
   2013–2021 as modelled and stop deriving "4.0× since 2013" and "58.4% in 2013"
   from them.
10. **`/sources`** (F16, F18, F38): soften "Every figure…" to what is true,
    de-duplicate the 17→~9 agency count, and surface `last_fetched` age in the
    health status so "Healthy" and "1 years ago" cannot co-exist.
11. **`/learn/government`** (F20): "at least 15% of the **most recently audited**
    revenue raised nationally"; "the CRA **recommends** the formula; Parliament
    approves it".
12. **`/audits`** (F34, F39): rename "Worst Offenders" → "Entities with the most
    findings"; fix the "County" column header; collapse the 12 duplicate
    finding-type facets and the raw `financial_audit` enum.

## 6. Fix after launch

Real gaps that a blank state represents honestly today.

1. **Replace every `?? 0` / `|| 0` on a published figure with a null-aware
   render.** Known sites: `BudgetFlowHero.tsx:78-94`, `DebtPageClient.tsx:321`,
   `AuditsPageClient.tsx:217,224,230`, `TransparencyPageClient.tsx:271-273`,
   `MetricsStrip.tsx:21-23` (dead), `SpendDonut.tsx:109-110`,
   `DebtPageClient.tsx:795`. A lint rule on these two operators inside
   `components/` and `app/` would make this a check that can fail.
2. **County audit counts** (F23): copy the Accountability tab's convention onto
   the KPI strip and the Audit Findings tab. `findings_count: 0` must render as
   "not yet ingested", never "0".
3. **Money-flow join** (Class **C**): `Allocated` and `Spent` already exist for
   four fiscal years; `/audit/money-flow/national?year=2025` and the H1/9M
   periods return null because they are not joined. The `Flagged` stage is a
   genuine **B** — county-level questioned amounts are not extracted.
4. **`/audit/money-flow` parameter handling** (F36): reject an unparseable
   `year` with a 400 and a reason instead of a well-formed empty object.
5. **`GET /budget/enhanced` `total_population: 907025674`** (F29) — 16× the real
   figure, latent because no component renders it.
6. **`GET /budget/national` `development_budget`** (F30) — a substring match on
   "…Urban **Development**"; 59.1B against COB's 744.84B. Latent for the same
   reason.
7. **`/fiscal/summary`** (F31): drop `debt_ceiling` / `debt_ceiling_usage_pct`
   (repealed instrument, "125% of ceiling") and reconcile `actual_debt` with the
   corrected `debt_timeline`, or delete the field.
8. **`financial_health_score`** (F32): make it a real composite or delete it —
   it is `budget_utilization` under a different name for all 47 counties.
9. **Debt instrument coverage** (Class **B**): 28 aggregate rows cannot support
   a maturity ladder, a lender treemap, or "every lender named". CBK publishes
   instrument-level domestic data and Treasury's APDMR carries the external
   register.
10. **Extend `/provenance/verify` to `budget_lines` and `debt_timeline`**
    (F16), and make `/provenance/health` fail on staleness (F17).
11. **`/transparency` default year** (F37): land on the newest year that has
    data, not on a year absent from the picker.

---

## 7. Method, and what would invalidate this

- Crawled at **1280×900** and **375×812**, viewport asserted by
  `documentElement.clientWidth` before every measurement; no horizontal overflow
  at either width; no mobile-only or desktop-only content found.
- Interaction exercised, not just page-at-rest: all five `/budget` fiscal-year
  buttons, all seven `/transparency` year buttons, all six county tabs, the
  `/counties/compare` selects. **My first `/budget` year click missed its
  target** and I wrongly read the picker as broken; a DOM-level click showed it
  works. Corrected above.
- API read directly for every figure before comparing to the DOM; responses
  saved under the session scratchpad.
- External verification against the **World Bank** and **IMF DataMapper** APIs
  for the peer table (commands and outputs in §2.10).
- Greps were positive-controlled before any "does not exist" claim (§2.15).
- I did **not** open the underlying COB, OAG or CBK PDFs. Where a figure's
  correctness depends on a document page, I have said what the site's own other
  surfaces or its own correction records claim, not what the PDF says. The
  findings that would change if a PDF disagreed are **F14** (what the 1.88T
  measure is) and **F12** (the FY2024/25 county basis); every other finding is
  internal contradiction, hardcoded template, wrong indicator, or a
  null-rendered-as-zero, and stands on its own receipt.
- Production moves. Every probe here was run on **2026-09-03**; re-run before
  acting.
