# Financial figure context review for #959

Compared `backend/main.py` on `42c7fe8` with the scoring change in `96ea284`. The whole-module AST differs only inside `_compute_accountability`. This change removes the score deduction inferred from publication status and reports resolution as unavailable. It introduces no financial amount, threshold, fallback, or publication rule.

The unchanged detector found the same four signatures in the same order in both versions. Their uses were checked again:

| Finding | Use after the scoring change |
| --- | --- |
| `_MAX_COUNTY_BUDGET_KES` (50 billion) | Defined once and never read. No amount or fallback uses it. |
| `_PENDING_BILLS_SEVERE_SHARE` (25%) | Both existing reads stay in the separate financial-health computation: one calibrates a score from the observed pending-bills share, and one explains the calibration. No score component is added for an absent input. |
| `_budget_overview_meta` (1,800) | Remains the response metadata TTL in seconds. The TTL and the unit fields do not supply budget amounts. |
| `anchor_pct_gdp` (55%) | The threshold is still separate from the sourced IMF actual. The measured ratio, period and vintage still come from the qualified reader and stay absent if it returns no qualified row. This review does not reassess the policy wording. |

The inventory keeps all four findings, reasons and tracking links. Only this module's reviewed fingerprint and review receipt change. The scanner and its drift checks are unchanged.
