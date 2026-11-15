# Financial literal context review for PR #952

This review binds the existing seven raw findings to the API source already on `main` at `4f9f313ad548096d660576278ceaf284c66aa7c7`. No measured value, safeguard rule, or inventory disposition changes. The previous matching source revisions are `4260a42` for `backend/main.py` and `2ed3703` for `backend/routers/data_provenance.py`.

| Existing finding | Current use |
| --- | --- |
| `_MAX_COUNTY_BUDGET_KES` (50 billion) | Definition only. No consumer feeds it into an amount or fallback. |
| `_PENDING_BILLS_SEVERE_SHARE` (25%) | Threshold used twice: to calculate the policy score from the observed ratio and to explain the scale. The liabilities and budget come from stored observations; missing data supplies no score component. |
| `_budget_overview_meta` (1,800) | `cache_ttl_seconds` passed to `_response_meta`. The summary amounts come from the budget queries; the TTL does not enter the totals or their units. |
| `anchor_pct_gdp` (55%) | Fiscal policy threshold. `_latest_imf_debt_to_gdp` still supplies the separate actual ratio, year and vintage. If it has no qualifying actual, the ratio remains absent; `above_anchor` remains null because that ratio and the present-value anchor are not comparable. This review does not revalidate the legal wording. |
| `budget_lines` (180), `gdp_data` (550), `debt_timeline` (240) | Day limits in `_STALE_AFTER_DAYS`, read by `_apply_freshness` to label source age and stale status. They do not supply or replace any budget, GDP or debt observation. |

The intervening `main.py` changes cover API capacity, caching, source status, county pending bills and debt, and the qualified fiscal and debt read paths. The existing county score and budget overview definitions are unchanged. Changes to the fiscal summary use qualified measures and adjust diagnostic metadata without changing the anchor's separate policy and observation fields. In the provenance router, the intervening changes are in the response model and `verify_data_point`: debt totals now come from the qualified publication result, and fiscal measures use their own proofs with absence preserved. The age policy and its only reader are unchanged.

The normalized AST pins are `43a0616147b48e95eaa7790a3c7505479d3fa89abf969540c9b5cfc8150bcd9d` and `d883324af15342203deb0ae2b89dccc8fc42a7b47ca47d55d3afa3a1ae20a011`, respectively. Applying the unchanged detector to both previous and current sources yields the same ordered signatures for all seven sites. Existing unresolved financial findings elsewhere remain tracked by #301 and #424.
