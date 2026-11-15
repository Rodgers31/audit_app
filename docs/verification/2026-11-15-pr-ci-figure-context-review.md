# Financial literal context review for PR #952

This review binds raw findings to the source already on `main` at `4f9f313ad548096d660576278ceaf284c66aa7c7`. The safeguard still reports each raw finding and requires a fresh review if the source or use changes. No measured value or safeguard rule changes.

| Existing finding | Current use |
| --- | --- |
| `_MAX_COUNTY_BUDGET_KES` (50 billion) | Definition only. No consumer feeds it into an amount or fallback. |
| `_PENDING_BILLS_SEVERE_SHARE` (25%) | Threshold used twice: to calculate the policy score from the observed ratio and to explain the scale. The liabilities and budget come from stored observations; missing data supplies no score component. |
| `_budget_overview_meta` (1,800) | `cache_ttl_seconds` passed to `_response_meta`. The summary amounts come from the budget queries; the TTL does not enter the totals or their units. |
| `anchor_pct_gdp` (55%) | Fiscal policy threshold. `_latest_imf_debt_to_gdp` still supplies the separate actual ratio, year and vintage. If it has no qualifying actual, the ratio remains absent; `above_anchor` remains null because that ratio and the present-value anchor are not comparable. This review does not revalidate the legal wording. |
| `budget_lines` (180), `gdp_data` (550), `debt_timeline` (240) | Day limits in `_STALE_AFTER_DAYS`, read by `_apply_freshness` to label source age and stale status. They do not supply or replace any budget, GDP or debt observation. |

The intervening `main.py` changes cover API capacity, caching, source status, county pending bills and debt, and the qualified fiscal and debt read paths. The existing county score and budget overview definitions are unchanged. Changes to the fiscal summary use qualified measures and adjust diagnostic metadata without changing the anchor's separate policy and observation fields. In the provenance router, the intervening changes are in the response model and `verify_data_point`: debt totals now come from the qualified publication result, and fiscal measures use their own proofs with absence preserved. The age policy and its only reader are unchanged.

The previous matching sources are `4260a42` and `2ed3703`, respectively. Applying the unchanged detector to those sources and `main` yields the same seven ordered signatures.

| Other finding | Current use |
| --- | --- |
| `audits_county_start_budget_seconds` (240) | Elapsed-time admission setting. The audit domain discloses it as `start_budget_seconds` and compares it with elapsed time. Compared with `4260a42`, the config adds separate opt-ins and adjusts whole-run and transfer budgets; the 240-second setting and its role are unchanged. |
| `_PLAUSIBLE_ORDINARY_REVENUE_BILLION` (1,500–6,000) | Validates the candidate magnitude at extraction time; an out-of-range number is refused. Compared with `8d11628`, PDF reading moved into the isolated parser, while the validation threshold and its consumer stayed the same. Neither limit fills an absent amount. |
| Four BROP Table 8 checks in `actuals.py` and the corresponding four in `fiscal_qualification.py` | Compared the checked-in PDF's SHA-256 with `BROP_SHA256` and read PDF page 21 visually. In the FY 2022/23 “Prel. Actual” column, the table prints 2,041 ordinary revenue, 1,887 tax, 154 non-tax, 319 A-i-A and 2,361 total, in KES billions. The producer compares the exact PDF-backed transcription to the expected values, and the reader matches these fields, basis, vintage, precision and source before returning the stored observation. The printed rounded total is kept as printed. This is separate from the higher-precision APDMR observation, and the review provides no production source-adoption authority. |
| `GRANT_VERIFICATION_BUDGET_EXCEEDED` (503) | A whitelisted HTTP status for a verification error from the child process; no financial amount or plan budget is provided by this number. |
| `revenue_by_source` (2) | An advisory lock namespace slot passed to `pg_advisory_xact_lock`, not a revenue observation or fallback. |

The four newly inventoried modules use exact whole-module pins and per-site signatures. No wildcard exclusion, suppression, or change to unresolved sites from #301 or #424 is included.
