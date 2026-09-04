/**
 * Debt measured against the statutory anchor.
 *
 * The alarm styling on the homepage headline is driven from here rather than
 * from a styling decision at the call site, so red only ever appears when a
 * published figure actually exceeds a published threshold — and the UI can
 * state which threshold, by how much.
 *
 * Absence is not compliance. A missing or unusable ratio must never render as
 * "within the anchor", for the same reason `classifyDebtRisk` refuses to turn
 * a failed API call into a Low risk band: a reassuring default is still a
 * claim. Hence the explicit `unassessed` state rather than a boolean.
 */

/**
 * PFM (Amendment) Act 2023 — 55% of GDP, in PRESENT-VALUE terms, targeted for
 * 2028. It replaced the repealed KES 10T numeric ceiling.
 *
 * The ratio the homepage compares against it is IMF General Government Gross
 * Debt on a NOMINAL basis, so the comparison is indicative rather than exact.
 * That caveat travels with the figure wherever this is rendered; it is not a
 * reason to withhold the comparison, which is the one published threshold
 * Kenya's debt position is formally measured against.
 */
export const PFM_ACT_ANCHOR_PCT_GDP = 55;

export type DebtAnchorStatus =
  | { state: 'above'; ratioPct: number; anchorPct: number; pointsAbove: number }
  | { state: 'within'; ratioPct: number; anchorPct: number }
  | { state: 'unassessed' };

/**
 * Compare a debt-to-GDP ratio against the anchor.
 *
 * `anchorPct` comes from the API (`fiscal.debt_anchor.anchor_pct_gdp`) so a
 * change in the law does not need a frontend release; the constant is only a
 * fallback for when the field is absent.
 */
export function assessDebtAnchor(
  ratioPct: number | null | undefined,
  anchorPct?: number | null
): DebtAnchorStatus {
  if (ratioPct == null || !Number.isFinite(ratioPct) || ratioPct <= 0) {
    // A non-positive debt-to-GDP reading is not a real observation for a
    // sovereign — it is what a failed request looks like.
    return { state: 'unassessed' };
  }

  const anchor =
    anchorPct != null && Number.isFinite(anchorPct) && anchorPct > 0
      ? anchorPct
      : PFM_ACT_ANCHOR_PCT_GDP;

  if (ratioPct <= anchor) return { state: 'within', ratioPct, anchorPct: anchor };

  return {
    state: 'above',
    ratioPct,
    anchorPct: anchor,
    pointsAbove: ratioPct - anchor,
  };
}
