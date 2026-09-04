/**
 * Revenue allocation math for the debt page's "Where every KES 100 of
 * revenue goes" card. Extracted out of DebtPageClient so the calculation
 * — including the headline rounding — can be unit-tested in isolation.
 *
 * Methodology: authoritative total-debt-service framing.
 *   debt-service-per-100-of-revenue = total debt service ÷ tax & non-tax revenue × 100
 *
 * The denominator is tax & non-tax revenue.
 * The numerator is total debt service (interest + principal redemptions).
 *
 * We do NOT floor — we round to nearest. 56.65 → 57, not 56. Flooring would
 * silently understate the burden by up to ~1 percentage point and change
 * thresholds (e.g. the IMF 30% ceiling badge).
 */
export interface FiscalCurrent {
  fiscal_year?: string;
  total_revenue?: number;
  debt_service_cost?: number;
  debt_service_per_shilling?: number;
  recurrent_spending?: number;
  development_spending?: number;
  county_allocation?: number;
  appropriated_budget?: number;
}

export interface RevenueAllocation {
  rev: number;
  budget: number;
  ds: number;
  borrowing: number;
  debtServicePerRev: number;
  recPerRev: number;
  devPerRev: number;
  countiesPerRev: number;
  borrowingPerRev: number;
  fiscalYear?: string;
}

export function computeRevenueAllocation(
  c: FiscalCurrent | null | undefined,
): RevenueAllocation | null {
  if (!c) return null;

  // Every component must be present. A missing one used to become 0, and the
  // "per KES 100 of revenue" breakdown then attributed that shilling to
  // borrowing instead — inventing a composition out of an absent series
  // rather than declining to draw one (credibility audit F2).
  const rev = c.total_revenue;
  const ds = c.debt_service_cost;
  const recTotal = c.recurrent_spending;
  const dev = c.development_spending;
  const counties = c.county_allocation;
  if (
    rev == null ||
    rev <= 0 ||
    ds == null ||
    recTotal == null ||
    dev == null ||
    counties == null
  ) {
    return null;
  }

  const rec = Math.max(recTotal - ds, 0);
  const budget = c.appropriated_budget || ds + rec + dev + counties;
  const borrowing = Math.max(budget - rev, 0);

  const debtServicePerRev =
    c.debt_service_per_shilling != null
      ? c.debt_service_per_shilling
      : (ds / rev) * 100;
  const recPerRev = (rec / rev) * 100;
  const devPerRev = (dev / rev) * 100;
  const countiesPerRev = (counties / rev) * 100;
  const allocatedPerRev =
    debtServicePerRev + recPerRev + devPerRev + countiesPerRev;
  const borrowingPerRev = Math.max(allocatedPerRev - 100, 0);

  return {
    rev,
    budget,
    ds,
    borrowing,
    debtServicePerRev,
    recPerRev,
    devPerRev,
    countiesPerRev,
    borrowingPerRev,
    fiscalYear: c.fiscal_year,
  };
}

/**
 * Headline number used in the "Debt service takes about KES X" copy.
 * Math.round (round-half-up for positive numbers) is intentional and
 * documented — see file header.
 */
export function formatHeadlineKes(debtServicePerRev: number): number {
  return Math.round(debtServicePerRev);
}
