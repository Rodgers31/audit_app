# Published figures that change in this PR

Every "after" value below was produced by running the pipeline against the live
publisher on 2026-08-29 and diffing the result against the git-tracked fixture.
No figure here was typed in by hand; each row names the document, the table and
the PDF page it came from.

Reproduce:

```bash
cd backend && python -m seeding.cli seed --domain fiscal_summary --domain debt_timeline --domain national_debt
```

---

## 1. Public debt by year — `debt_timeline`

**Source:** CBK Statistical Bulletin, December 2025 — Table 4.1.3 *"Deficit
Financing and Public Debt"*, **PDF page 56**.
`https://www.centralbank.go.ke/uploads/statistical_bulletin/107371226_Statistical%20Bulletin%20-%20December%202025.pdf`
(3,013,088 bytes; discovered from the CBK listing page, not hardcoded.)

Values are KSh billion, at each year's **latest published month (December)**.

| Year | Total — before | Total — after | Δ | External before → after | Domestic before → after |
|---|---:|---:|---:|---|---|
| 2022 | 9,100.0 | 9,146.0 | **+46.0** | 4,300 → 4,673.1 | 4,800 → 4,472.8 |
| 2023 | 10,200.0 | 11,139.7 | **+939.7** | 4,800 → 6,089.6 | 5,400 → 5,050.1 |
| 2024 | 11,490.0 | 10,925.3 | **−564.7** | 5,326 → 5,057.0 | 6,164 → 5,868.3 |
| 2025 | 12,500.0 | 12,299.5 | **−200.5** | 5,680 → 5,462.0 | 6,820 → 6,837.5 |

The 2025 row is the headline: the fixture published **KSh 12.50T** where CBK
publishes **KSh 12.299T**.

Note the external/domestic split moves further than the totals do — the fixture
had 2023 external too low by 1.29T and domestic too high by 0.35T, which
happened to partly cancel in the total. A reconciliation that only checked
totals would have passed.

Every row is accepted only if it satisfies CBK's own identity
`domestic + external = total` (±0.5%); rows that fail are dropped rather than
published (`parse_public_debt_table`), so a mis-parsed row cannot become a
figure on the site.

---

## 2. Domestic debt by instrument — `national_debt`

**Source:** CBK Statistical Bulletin, December 2025 — Table 4.1.4 *"Composition
of Government Gross Domestic Debt by Instrument"*, **PDF page 57**, month-end
**December 2025**. Same document as above.

| Instrument | Before | After | Δ |
|---|---:|---:|---:|
| Domestic Treasury Bonds | 4.564T | **5.579T** | **+1.015T** |
| Domestic Treasury Bills (91/182/364-day) | 1.050T | **1.090T** | +0.040T |
| CBK Overdraft Facility | 0.250T | **0.0782T** | **−0.1718T** |
| Advances from Commercial Banks | *(absent)* | **0.0114T** | new row |

Treasury Bonds — the largest single component of Kenya's domestic debt — were
understated by **KSh 1.015 trillion**. The CBK Overdraft Facility was
overstated by a factor of 3.2.

---

## 3. National budget headline — `fiscal_summary`

**Decision:** the Controller of Budget's **original gross budget** is now the
canonical basis for `appropriated_budget`, for past, present and future years.

The previous values were **Budget Policy Statement** figures. Those are a
different measure, not an out-of-date version of the same one, so they were
**re-sourced from each year's COB report** rather than relabelled. Every row now
declares `budget_basis` and carries the document, page and quoted sentence it
came from.

| Fiscal year | Before (BPS) | After (COB original gross) | Δ | Receipt |
|---|---:|---:|---:|---|
| FY 2022/23 | 3,310 | **3,675** | +365 | COB NG-BIRR FY2022/23 (Aug 2023), §3.2 p.16 (PDF p.37) |
| FY 2023/24 | 3,600 | **4,340** | +740 | COB NG-BIRR FY2023/24 (Aug 2024), §3.2 p.17 (PDF p.39) |
| FY 2024/25 | 3,900 | **4,490** | +590 | COB NG-BIRR FY2024/25 (Aug 2025), Exec. Summary p.xxviii (PDF p.29) |
| FY 2025/26 | 4,190 | **4,690** | +500 | COB NG-BIRR 9M FY2025/26 (May 2026), Exec. Summary p.xxii (PDF p.23) |
| FY 2026/27 | *(row did not exist)* | **5,485.7** | new | Treasury FY2026/27 Approved Programme Based Budget Book — voted total PDF p.11, CFS summary PDF p.1193 |

KSh billion. FY2022/23's figure is the only derived one: COB states 4.19T for
National **and** County government combined and 515.18B for the counties in the
same sentence, so the National-Government figure is the difference. The
derivation is recorded on the row.

`borrowing_pct_of_budget` is derived from `total_borrowing / appropriated_budget`
at parse time, so it moves with these budgets automatically (FY2025/26:
21.7% → 19.4%).

### What "gross" means, and what it excludes

COB states its own composition (NG-BIRR 9M FY2025/26, p.xxii):

> The National Government's original gross budget for FY 2025/26 amounts to
> Kshs. 4.69 trillion […] Kshs.744.84 billion for ministerial development
> expenditure […] ministerial recurrent allocation of Kshs.1.80 trillion […]
> and Consolidated Fund Services (CFS) at Kshs. 2.14 trillion

so **gross budget = gross ministerial (recurrent + development) + CFS**, and it
**excludes the county equitable share**, which COB reports separately.

---

## 4. FY 2026/27 — the figure that is NOT KSh 4.82T

The brief for this work expected the enacted FY2026/27 budget to be
**KSh 4.82 trillion** and asked for the parse to be quarantined if it disagreed
materially. It does disagree, and the reason is a basis difference, not a parse
error.

On the canonical (COB gross) basis, read from Treasury's own approved book:

| Component | FY 2026/27 | Where |
|---|---:|---|
| Total voted expenditure (gross current + gross capital) | 2,922,706,913,184 | PBB PDF p.11, "TOTAL VOTED EXPENDITURE … KShs." |
| Consolidated Fund Services (grand total) | 2,562,973,919,672 | PBB PDF p.1193, "SUMMARY 1 – CONSOLIDATED FUND SERVICES", GRAND TOTAL |
| **Gross budget** | **5,485,680,832,856** | sum of the two |

Three independent checks pass on that parse:

1. `gross current (2,078,271,468,734) + gross capital (844,435,444,450) = gross total` ✓
2. `interest & redemption (2,315,884,392,206) + pensions/salaries/misc (247,089,527,466) = CFS grand total` ✓
3. **Cross-publisher:** the same book prints FY2025/26 CFS as
   **2,141,025,101,165**, and COB independently publishes FY2025/26 CFS as
   **"Kshs. 2.14 trillion"** — 0.05% apart. A parse that grabbed the wrong
   column could not satisfy this.

**KSh 4.82T is a different measure.** Working back from the same book, the
figure usually quoted in the Budget Statement is total expenditure *excluding
debt redemption* and *including* county transfers:

```
2,922.7 (voted gross)
+ 1,254.2 (CFS interest)      ← redemption of 1,061.6 excluded
+   241.9 (pensions)
+     5.1 (salaries & misc)
= 4,424.0  + county equitable share (~0.4T) ≈ 4.82T
```

That is a legitimate published measure. It is **not** COB's original gross
budget, which is the basis chosen for this field, and publishing it under the
`cob_gross` label would be exactly the conflation the basis gate exists to stop.

**So the pipeline publishes 5,485.7B and labels it `cob_gross`.** If the
intended headline is the 4.82T measure instead, that is a basis decision, not a
bug fix: the change is `CANONICAL_BUDGET_BASIS` plus a second composition in
`budget_estimates.py`, and every row would need re-sourcing on that basis the
same way this PR re-sourced them on gross. Say the word and it is a follow-up.

A consistency check that the 5.49T figure is right: Treasury's own *Estimates of
Revenue, Grants and Loans FY2026/27* (PDF p.v) puts total revenue including
grants at **3,674,151,304,332**. `5,485.7 − 3,674.2 = 1,811.5B` of borrowing,
of which 1,061.6B is debt redemption from the CFS table — leaving a deficit of
~750B. That is the right order of magnitude for Kenya's FY2026/27 deficit
target; the alternative readings are not.

---

## What is deliberately NOT changed

* **`recurrent_spending`, `development_spending`, `county_allocation`** stay on
  the Budget Policy Statement / APDMR definitions they have always had. Only
  `appropriated_budget` was in scope for the basis decision, and moving four
  more published series as a side effect of it is a separate, deliberate change.
  The mixed basis is now *recorded* in the fixture's `definitions` block rather
  than being silent, and COB's own composition per year is quoted on each row in
  `budget_basis_source.composition` so the follow-up has its receipts ready.

* **The homepage "Where the money goes" bar** attributes the gap between the
  gross envelope and those BPS-basis components to *Other* (FY2025/26: 753B,
  16%). Correcting it means either moving the components onto the gross basis
  (above) or teaching the bar that the county share sits outside a
  National-Government gross budget. Both touch `HeroSection.tsx`, which carries
  uncommitted design work, so neither is in this PR.

* **The FY2026/27 row has no revenue.** Treasury's revenue book publishes
  3,630.5B excluding grants for FY2026/27, but the fixture's `total_revenue`
  series is on a narrower measure (FY2025/26: 2,910B against the same book's
  3,321.7B). Publishing them side by side would show revenue jumping 25% for
  measurement reasons. Left null until the revenue series gets the same
  basis treatment the budget just had.
