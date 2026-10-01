# County cash layout recovery — 1 October 2026

Issue #299; local offline acceptance only. The exact Controller of Budget
[FY2025/26 annual county report](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482)
was downloaded again and matched SHA-256
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
All 20 relevant pages were rendered and read before interpreting their cells.

The merged baseline `95d48ad98978b7fb15de69cb88594d6d6d003cb9` parses
**40/47** cash tables. The changed parser parses **43/47** on the same bytes
and parser stack. All 260 prior cash records, including all 40 totals, survive
unchanged. All 188 budget amounts and other financial fields survive unchanged.
Four existing budget Total records receive updated cash coverage metadata only:
Kisii, Kisumu, Kitui, and Samburu. Full output grows from 448 to 468 records;
the 20 additions are cash records for the three recovered counties.

| County | Table; PDF / printed pages | Cash total, KES | Recovery and local evidence |
|---|---|---:|---|
| Kisii | 3.241; 330–332 / 296–298 | 16,499,037,626 | Literal underscore nil marks in six grants cells caused rejection. Treat the marks as unobserved nil, like a dash. Printed grants subtotal 855,582,918; the stream subtotals sum to 16,499,037,625, KES 1 below the total. |
| Kisumu | 3.256; 349–351 / 315–317 | 13,360,566,017.46 | The extractor puts the leading target digit into `Total 1`, leaving `6,973,318,712` in the target cell. Rejoin that bounded grouped-number boundary as target 16,973,318,712, and retain cash B separately from accrual D. Cash stream subtotals sum to 13,360,566,017, KES 0.46 below the total. |
| Kitui | 3.269; 367–369 / 333–335 | 13,809,805,963 | The grants subtotal label is a dash. Cash 1,286,750,893.25 independently repeats in accrual D with explicit nil C, and preceding cash items sum to 1,286,750,893. The KES 0.25 difference is within their printed precision. The next row opens OSR. Missing item targets stay missing; the independently printed aggregate target is 2,071,208,708.42. Cash stream subtotals sum to 13,809,805,962.25, KES 0.75 below the total. |

The existing KES 1,000 grand-total tolerance is unchanged. Recovery of the
unnamed subtotal uses a narrower Decimal bound based on half a unit in each
cell's last printed decimal place. It also requires local row evidence, a
following named stream, and no missing cash item; a grand total cannot rescue
an unsupported subtotal. A numbered grant with erased amount cells must not
disappear as a heading. Malformed grouping and nonfinite values remain refused.
Missing targets remain null where no printed aggregate supplies them. Explicit
numeric zero remains publishable; underscore/dash/blank totals do not become
observed zero.

## Four remaining withheld counties

| County | Table; PDF / printed pages | Exact parser refusal | Source evidence |
|---|---|---|---|
| Kwale | 3.285; 385–387 / 351–353 | `streams_do_not_sum_to_grand_total (out by 59,814,318.00)` | Cash subtotals sum to 14,868,217,168 against printed cash total 14,808,402,850. Do not substitute the accrual total or balance the residual. |
| Migori | 3.412; 546–549 / 512–515 | `a_section_has_two_subtotals` | Three nested grant subtotals remain unsupported. Their cash components are 3,684,754 + 0 + 630,968,493 = 634,653,247. Figure 3.154 on PDF 549 prints additional allocations 1,075.93 million, a material publisher disagreement. It cannot corroborate recovery. |
| Nyeri | 3.546; 712–713 / 678–679 | `unobserved_receipts_cell` | The OSR heading prints cash 746,508,377 but its closing subtotal is blank. The chapter narrative reports total receipts 8.58 billion while the table prints 8,952,037,562. Do not fill the blank or select a preferred total. |
| Samburu | 3.560; 729–730 / 695–696 | `streams_do_not_sum_to_grand_total (out by 24,413)` | The numbered equitable-share item is labeled Sub-Total and followed by an identical target/cash subtotal, 6,336,970,364. Resolve that duplicate locally, then refuse the arithmetic conflict: stream subtotals sum to 7,668,339,796 against printed 7,668,364,209. Known printed grants cash items sum to 899,402,185 against their subtotal 873,402,185, a further KES 26,000,000 disagreement. |

Samburu's more specific refusal changes coverage explanation, not a published
amount. These residual source problems belong under existing #299.
Mombasa's accepted cash/accrual roles remain unchanged: ordinary cash OSR
3,799,700,513 plus FIF cash 2,414,889,970, chapter cash total including opening
balance 15,790,774,484, and summary accrual measure 21,126.23 million.

## Verification and release limits

- The same final regression cases executed against the baseline module fail
  for Kisii, Kisumu, and Kitui (three failures), then pass against the change.
- 313 focused tests passed with no skips. Actual PostgreSQL 16.15 persistence
  and public comprehensive-account HTTP checks ran for all three recovered
  counties, using the original PDF for captions/year and source-shaped cash
  rows. The HTTP download and parse-cache transport were stubbed; the cash
  parser, normalization, writer, SQL round trip, and public account executed.
- An independent GPT-6.1 Sol/high reviewer ran 265 probes. Its introduced
  missing-grant finding was reproduced red, fixed, and independently verified.
  No introduced finding remained in those probes.
- Runtime: Python 3.13.9, pdfplumber 0.11.10, pdfminer.six 20260107,
  psycopg2-binary 2.9.12, SQLAlchemy 2.0.51. Node 22.19.0 was observed but no
  frontend code or frontend runtime participated in the comparison.

The default source regressions are in `test_county_cash_layout_recovery.py`.
The real PostgreSQL test is opt-in: supply `COUNTY_CASH_TEST_POSTGRES_URL` for an
owned `round8_s5` loopback database with explicit port and no URL query, and
`COUNTY_CASH_SOURCE_PDF` for this checksum-pinned PDF. No dotenv or production
URL may authorize that test. Its randomly owned schemas are removed afterward.

This is not production publication or nightly acceptance. Before a separately
authorized bounded release, re-run checksum-bound preflight on the consolidated
code and pin 47 budget totals, 43 cash totals, 468 candidates, and these four
refusals. Capture a fresh exact-key database beforeimage/recovery plan; preserve
historical periods and the current 47-county project arrays. Confirm deployed
code and source version before any serialized county-budget ingestion. After
an approved refresh, check public API and rendered pages for a recovered
county, Mombasa's cash/accrual distinction, and each residual refusal. Keep
Actions off and #299 open until coordinator verification and actual public
acceptance. This receipt grants no seed, cleanup, refresh, or release authority.
