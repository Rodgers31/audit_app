# County source reconciliation — 1 October 2026

**Decision: retain the four cash refusals and the existing 168 source-backed
project detail rows.** No source-proven parser defect was found in this bounded
investigation, so no parser, tolerance, writer, service, or fixture was changed.
This is offline source evidence for [#299](https://github.com/Rodgers31/audit_app/issues/299)
and [#230](https://github.com/Rodgers31/audit_app/issues/230), not production
publication acceptance or authority to ingest, refresh, or clean stored data.

The [machine-readable manifest](2026-10-01-round11-county-source-manifest.json)
records the exact four-case cash ledger, edition identity, arithmetic, controls,
and continuing refusal. The [47-county project coverage CSV](2026-10-01-round11-project-source-coverage.csv)
keeps reported counts, extracted cardinality, captions, pages, and reconciliation
failures separate. An empty CSV reported-count cell is absent evidence;
`detail_rows: 0` describes extraction cardinality, not zero stalled projects.

## Source identity and edition chronology

The official [annual FY2025/26 report](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482)
was freshly downloaded on 1 October 2026. HTTP response date: **23:43:47 UTC**
(18:43:47 America/Chicago); filename `CGBIRR FY 2025_26 August 2026 Final 5.pdf`.
The cover says August 2026, the fiscal year is FY2025/26, and the project
observations are as at 30 June 2026. The PDF has 935 pages. SHA-256 is
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`:
fresh bytes equal the retained artifact used by the prior receipts and the
29 September nightly described in the current #230 comment.

The official [download page](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/)
shows both creation and last update as **25 September 2026**. The fresh
[county-report listing](https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/)
lists this annual report, then the FY2025/26 nine-month, first-half and
first-quarter reports. Cover month, website publication date, download date,
and observation date are different fields. The filename's `Final 5` does not
establish five publicly issued editions or a correction chronology.

No later annual edition, corrigendum, revised edition, or clarification was
located in this bounded official listing/download-page investigation and
official-domain searches for FY2025/26 with revised, revised edition,
corrigendum, correction, and clarification. This is **not exhaustive proof of
absence**. Earlier quarterly reports cover different periods and cannot fill
annual cells. An OAG finding, county budget estimate, or repeated graph label
does not establish a corrected annual actual-receipts measure.

Tables attribute the observations to County Treasuries, published by the
Office of the Controller of Budget. They are county-reported budget
implementation observations, not OAG audit conclusions. PDF references below
are one-based; printed chapter pages are PDF page minus 34.

## Four-case cash ledger

All figures in this table are KES unless explicitly marked million/billion.
Column B is actual cash receipts; column D is accrual receipts plus
receivables/arrears. Opening balances remain part of the table cash measure.

| County | Table; PDF / printed pages | Fresh refusal and exact observed conflict | Alternate-source assessment |
|---|---|---|---|
| Kwale | 3.285; 385–387 / 351–353 | `streams_do_not_sum_to_grand_total (out by 59,814,318.00)`. Cash section subtotals 1,770,505,972 + 9,078,699,643 + 3,167,878,534 + 367,738,513 + 483,394,506 = **14,868,217,168**, exceeding printed B total **14,808,402,850** by **59,814,318**. | Figure 3.107, PDF 388 / printed 354, uses grants **3,518.87 million** and ordinary OSR **401.48 million**, following D's accrual values rather than B's **3,167,878,534** and **367,738,513**. Opening/refunds are split differently. It cannot corroborate a cash replacement. |
| Migori | 3.412; 546–549 / 512–515 | `a_section_has_two_subtotals`. Section C has nested grants subtotals **3,684,754**, a printed **dash**, and **630,968,493**. Known numeric subtotals sum to **634,653,247**; the dash remains unobserved, not sourced zero. | Narrative PDF 545 / printed 511 says **634.65 million** additional allocations, but Figure 3.154 on PDF 549 says **1,075.93 million**, **441,276,753** above the known table subtotal sum. Receivables are nil-marked; no compatible different basis was established for the chart. Neither a preferred statement nor nested-layout support alone resolves the source conflict. |
| Nyeri | 3.546; 712–713 / 678–679 | `unobserved_receipts_cell`. OSR heading B is **746,508,377**; closing subtotal is **blank**. Printed grand total is **8,952,037,562**. Equitable-share B and D print **6,985,132,673**, while A prints **6,896,132,673**, a difference of **89,000,000**. | Figure 3.208, PDF 714 / printed 680, shows **6,896.13 million** equitable share, following A rather than B. Narrative PDF 712 says total **8.58 billion**, then mentions opening cash separately. A equitable share + grants **935,332,347** + OSR **746,508,377**, excluding opening **285,064,165**, yields **8,577,973,397**, consistent with that rounding. This is a possible basis explanation, not authority to select A as actual or fill the blank. The observed B/figure conflict remains. |
| Samburu | 3.560; 729–730 / 695–696 | `streams_do_not_sum_to_grand_total (out by 24,413)`. After recognizing the repeated equitable-share subtotal, cash section subtotals sum to **7,668,339,796**, versus printed **7,668,364,209**: **24,413** short. Known numeric grant items sum to **899,402,185**, versus subtotal **873,402,185**: **26,000,000** above. | Figure 3.214, PDF 731 / printed 697, repeats grants **873.40 million**, without resolving the item contradiction; opening **4.05 million** differs from table **4.023196 million**. Narrative PDF 728 likewise says opening **4.05 million**. Repetition is not independent corroboration or a residual-allocation rule. |

**Continuing refusal applies to all four.** No residual was allocated, blank
filled, accrual value substituted, tolerance enlarged, or preferred publisher
statement promoted to an accepted cash amount. Decimal arithmetic was executed
against the visible source transcriptions. Rounded graph labels are retained
at their printed precision; they do not supply exact revised cash cells.

The Nyeri narrative qualification refines the earlier receipt: different
treatment of opening balances can explain part of the apparent narrative/table
gap. It does not resolve the blank subtotal or the separate equitable-share
column disagreement. This is a source/basis observation within #299, not a
new amount correction.

## Projects: reported totals versus detail-table scope

Fresh actual extraction gives **168 detail rows, 20 body captions, and 47 county
records**. Section 2.4.3 and Table 2.6 (PDF 44–45 / printed 10–11) report
**189** projects, **10,508.01 million** value, and **4,206.15 million** paid
(narrative rounds to 10.51/4.21 billion). Those are reported summary assertions,
not app-computed complete detail totals.

Independently extracted visible numeric county counts in Table 2.6 sum to
**188 across 21 counties**. Trans Nzoia's count cell is genuinely blank; its
value/paid cells are populated. There are **167** parsed detail rows in those
comparable 21 counties and another **one** Trans Nzoia row. Thus 189−168=21
is an arithmetic difference between incompatible source scopes; it does not
identify 21 missing projects or prove that 21 records can be recovered.

| County | Summary / Table 2.6 count | Detail rows | Source inspected and qualification |
|---|---:|---:|---|
| Elgeyo Marakwet | 2 / 2 | 1 | Table 3.76, PDF 139 / printed 105: only row 1 (Governor's Official Residence), then total/source/next section. Row value/paid **52,739,516 / 14,787,937** conflict with totals **98,739,516 / 60,787,937**. No second identity is printed here. |
| Kakamega | 26 / 26 | 10 | Table 3.170, PDF 248–249 / printed 214–215: rows 1–10, then total/source. National prose PDF 45 separately says **22**. Keep all three count assertions; detailed monetary totals also disagree. |
| Kilifi | 10 / 10 | 9 | Table 3.234, PDF 322–323 / printed 288–289: printed row numbers **1,2,3,5,6,7,8,9,10**. Row 4 is absent from the visible table, not discarded by this parser. Known values/paid reconcile to rounded monetary summaries; that does not establish another identity. |
| Lamu | 4 / 4 | 3 | Table 3.325, PDF 431–432 / printed 397–398: rows 1–3, then source/next section. The three monetary rows reconcile to the rounded summaries. Mislabelled percentage/cause columns remain raw/flagged. |
| Nyamira | 1 / 1 | 0 | PDF 686 / printed 652 supplies a narrative, not a stalled-table caption: County Assembly Speaker's Residence in Bonyamatuta Ward. Summary paid **26.62 million** differs from the named narrative's **26.65 million**. Institution scope and conflicting paid statements must survive any future narrative extraction. |
| Siaya | 1 / 1 | 0 | PDF 758 / printed 724 names completion of Nyamonye Juakali in Yimbo East in narrative, not a stalled table. Reported value **1.88 million** and paid **3.72 million** are not clamped; national prose expressly discusses overpayment. |
| Trans Nzoia | 1 / blank | 1 | Table 3.644, PDF 825 / printed 791: one Kitale Business Centre row. Headers say Kshs.; row value/paid **874 / 94.52**, total **874 / 794.52**, versus summaries **874.00 / 794.52 million**. Current writer withholds detailed monetary fields and retains source cells/statements; no rescaling is justified. |

For the remaining counties, the CSV preserves all statuses, including Nairobi
and Tharaka Nithi monetary disagreements despite matching counts, missing paid
cells, and unsupported observations. No numeric national count or detail table
for the other 25 counties is evidence of zero projects. Named Nyamira/Siaya
narratives are possible future scope extensions requiring an explicit
extraction/publication contract, not a defect in the existing table parser.
No OAG volumes were replayed or new name matches asserted in this session.
Prior unmatched/different-year OAG observations remain inherited and qualified.

## Caller and executed verification

Base: `355c057a6138ed47212a5aab865f4bdf26a02177`, tree
`57d55dfdb1c01b04f92297edd02ff6a78a8e4cbf`, prepared branch
`codex/round11-county-source-reconciliation`; clean checkout verified first.
All repository work used that checkout. Primary user edits/services were not
accessed, apart from the permitted read-only Python dependency runtime.

Actual paths inspected/executed:

- Cash: `CoBQuarterlyReportParser.parse` → `county_revenue_receipts` in
  `backend/seeding/pdf_parsers.py`, including the existing section/grand-total
  and observed-cell guards. Fresh output compared with the prior final bank.
- Projects: domain `run` → `fetcher.fetch` → `parse_edition` →
  `CbirrStalledProjectsParser.parse`; `writer.build_county_block` →
  `services.stalled_projects.build_stalled_projects_block`, called by the
  comprehensive county handler in `backend/main.py`. No database writer ran
  against a live destination; focused pipeline tests used their SQLite fixtures.

| Fresh execution | Result and boundary |
|---|---|
| Full-PDF financial replay | Exit 0: **468 candidates, 47 budgets, 43 cash totals**. Every candidate and all 47 statuses exactly equal the banked final output; four exact refusals above. Checksums verified before/after. All accepted cases, explicit zero/null distinctions and Mombasa cash total **15,790,774,484** preserved. |
| Full-PDF project replay | Exit 0: **168 rows / 20 captions / 47 counties**. Source summaries and discrepancies retained; checksum unchanged. |
| Focused pytest | Exit 0: **192 passed, no skips**, final run 2.57 seconds. `test_county_cash_layout_recovery.py`, `test_county_revenue_receipts.py`, `test_cob_stalled_projects_parser.py`, `test_stalled_projects_pipeline.py`, `test_stalled_projects_edition_gate.py`. Three existing warnings; no new implementation was tested. Explicit inert lifespan and application-engine connection guard reported **zero PostgreSQL connection attempts**. |
| Local block/public-service controls | Exit 0: all 47 county blocks retain their parsed row counts; no-table public counts stay null; Trans Nzoia monetary fields withheld; Baringo Marigut dash-paid remains null. |
| Independent GPT-6.1 Sol/high source review | Both source and controls runs exit 0. Independently extracted raw national/count-conflict tables and rendered relevant full pages; row-number sequences match parser output. Actual fetch gate refuses empty outputs, captions with no rows, and invalid row counts (`True`, negative, NaN, infinity, string, null); actual 168-row positive control passes. Absent/empty PDF controls fail visibly. |

Python runtime uses `/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python`;
pdfplumber **0.11.10**, pdfminer.six **20260107**, pypdfium2 **5.11.0**,
SQLAlchemy **2.0.51**. The allowlisted child environment cleared inherited
destinations, disabled dotenv/Pydantic env files, seed/warmup and Redis, and
read back synthetic engine/libpq loopback **127.0.0.1:55472**. No database
connection was opened for replay/control scripts, no PostgreSQL container was
started, and no dependency directories/symlinks were modified. Application
lifespan was disabled and outbound provider HTTP guarded for focused tests.
Transport stubs and SQLite tests do not certify production transaction parity,
stored source metadata, deployed code, cache freshness, or rendered pages.

External reproducible artifacts are banked beside the session briefs under
`ROUND11_SESSION_2_`: `RUN.py`, `REPLAY.py`, `CASH_REPLAY.json/.log`,
`PROJECTS.json`, `PROJECT_REPLAY.log`, `CONTROLS.py/.log`, `ARITHMETIC.json`,
`FOCUSED.log`, `FOCUSED_FINAL.log`, official listing/download HTML, response headers, fresh PDF,
rendered pages, fresh issue JSON, and independent `REVIEW_*` scripts/results.
The manifest pins hashes for the key source/replay evidence. To reproduce:

```sh
# Run from the assigned checkout. ART points to the external receipt directory.
PY=/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python
$PY "$ART/ROUND11_SESSION_2_RUN.py" script "$ART/ROUND11_SESSION_2_REPLAY.py" projects
$PY "$ART/ROUND11_SESSION_2_RUN.py" script "$ART/ROUND11_SESSION_2_REPLAY.py" cash
$PY "$ART/ROUND11_SESSION_2_RUN.py" script "$ART/ROUND11_SESSION_2_CONTROLS.py"
$PY "$ART/ROUND11_SESSION_2_RUN.py" pytest tests/test_county_cash_layout_recovery.py \
  tests/test_county_revenue_receipts.py tests/test_cob_stalled_projects_parser.py \
  tests/test_stalled_projects_pipeline.py tests/test_stalled_projects_edition_gate.py -q
```

## Source decisions and separately gated release

All newly detailed conflicts are duplicate candidates under existing #299
(cash/basis) and #230 (project source scopes), not independently filed bugs.
No source-proven parser defect or demonstrated new production amount failure
was found. The 29 September real ingestion and earlier production snapshots
are inherited dated receipts, not fresh public/database observations here.

Before any future source recovery, obtain a corrected same-period/measure
official edition or explicit publisher clarification naming the exact cells,
scope and units. Pin its checksum and chronology. Reproduce a genuine parser
defect red on a source-shaped fixture before changing code; preserve every
accepted old control and qualification. A changed document with a preferred
total is not automatic acceptance.

Before separately approved ingestion/public acceptance, use the existing
[cash recovery release prerequisites](2026-10-01-county-cash-layout-recovery.md)
and [financial publication plan](2026-09-27-county-financial-publication.md),
with fresh consolidated-code/source preflight and an exact-key beforeimage/
recovery manifest. Preserve all historical periods, current project arrays,
documents 1823/2541, accepted population row 79, and unrelated later metadata.
Any legacy cleanup needs its own fresh dependency manifest and authority;
never restore the old fixture arrays or blanket-purge source-backed blocks.

Deployed code, serialized ingestion, refresh, API/provenance and rendered-page
acceptance must be recaptured for a recovered county, Mombasa and all four
refusals; project coverage and qualifications need their own public review.
Actions, production writes, source retirement, credential/configuration changes,
and Projects UI exposure remain outside this session. Keep both issues open.
