/**
 * Revenue allocation math for the debt page's "Where every KES 100 of
 * revenue goes" card. Extracted out of DebtPageClient so the calculation
 * — including the headline rounding — can be unit-tested in isolation.
 *
 * Two figures, each on a declared basis, never mixed:
 *
 * 1. THE HEADLINE — Treasury's APDMR ratio:
 *      total debt service (interest + principal) ÷ tax & non-tax revenue × 100
 *    We do NOT floor — we round to nearest. 56.65 → 57, not 56. Flooring
 *    would silently understate the burden by up to ~1 percentage point.
 *
 * 2. THE BREAKDOWN — one column of the Budget Summary's fiscal framework
 *    (issue #237), per KES 100 of the same ordinary revenue. Interest is the
 *    debt slice here, because interest is what sits inside recurrent
 *    spending; principal is financing, not spending, so it is neither in
 *    recurrent nor in the bar. This used to subtract the headline's debt
 *    service (interest + principal) from recurrent, which took ~1.06T of
 *    principal out of a figure that never held it and shrank "recurrent" by
 *    that much. Spending beyond revenue is shown with what the table says
 *    financed it (A-i-A, grants, net borrowing), not as a computed residual.
 */
import {
  frameworkOf,
  frameworkSources,
  frameworkUses,
  type FiscalFramework,
} from '@/lib/fiscal/framework';

export interface FiscalCurrent {
  fiscal_year?: string;
  /** Any unit — only its ratio to debt_service_cost is used. */
  total_revenue?: number | null;
  debt_service_cost?: number | null;
  debt_service_per_shilling?: number | null;
  /** The same revenue in KSh billion, to check it IS the framework's. */
  total_revenue_billion?: number | null;
  fiscal_framework?: FiscalFramework | null;
}

export interface RevenueBreakdown {
  /** Ordinary revenue the per-100 figures are measured against, KSh bn. */
  revenueB: number;
  interestPerRev: number;
  recPerRev: number;
  devPerRev: number;
  countiesPerRev: number;
  contingencyPerRev: number;
  /** Spending per KES 100 of revenue; > 100 when revenue does not cover it. */
  spendingPerRev: number;
  /** How the part above 100 was financed, per the same column. */
  aiaPerRev: number;
  grantsPerRev: number;
  borrowingPerRev: number;
  cashAdjustmentPerRev: number;
}

export interface RevenueAllocation {
  rev: number;
  ds: number;
  debtServicePerRev: number;
  fiscalYear?: string;
  /** Null when no same-basis split exists for this year. */
  breakdown: RevenueBreakdown | null;
}

export function computeRevenueBreakdown(
  c: FiscalCurrent | null | undefined,
): RevenueBreakdown | null {
  const ff = frameworkOf(c ?? null);
  const uses = frameworkUses(ff);
  const sources = frameworkSources(ff);
  if (!uses || !sources) return null;
  const rev = sources.ordinaryRevenue;
  if (!(rev > 0)) return null;
  // The headline divides by the row's revenue; the breakdown by the
  // framework's. They must be the same figure, or the card would put two
  // different "KES 100"s side by side.
  const rowRevB = c?.total_revenue_billion;
  if (rowRevB == null || Math.abs(rowRevB - rev) > 0.5) return null;
  const per = (v: number) => (v / rev) * 100;
  return {
    revenueB: rev,
    interestPerRev: per(uses.interest),
    recPerRev: per(uses.recurrentExInterest),
    devPerRev: per(uses.development),
    countiesPerRev: per(uses.counties),
    contingencyPerRev: per(uses.contingency),
    spendingPerRev: per(uses.total),
    aiaPerRev: per(sources.aia),
    grantsPerRev: per(sources.grants),
    borrowingPerRev: per(sources.borrowing),
    cashAdjustmentPerRev: per(sources.cashAdjustment),
  };
}

export function computeRevenueAllocation(
  c: FiscalCurrent | null | undefined,
): RevenueAllocation | null {
  if (!c) return null;
  // Absent is absent: a missing revenue or debt service used to become 0,
  // which is a claim (credibility audit F2).
  const rev = c.total_revenue;
  const ds = c.debt_service_cost;
  if (rev == null || rev <= 0 || ds == null) return null;

  const debtServicePerRev =
    c.debt_service_per_shilling != null ? c.debt_service_per_shilling : (ds / rev) * 100;

  return {
    rev,
    ds,
    debtServicePerRev,
    fiscalYear: c.fiscal_year,
    breakdown: computeRevenueBreakdown(c),
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
