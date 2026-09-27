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
 * silently understate the burden by up to ~1 percentage point.
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
  /**
   * The document THIS YEAR'S DEBT SERVICE was read from. Not
   * `budget_basis_source`, which is where the budget came from — for some
   * years a different document.
   */
  debt_service_source?: {
    title?: string | null;
    publisher?: string | null;
    url?: string | null;
    page?: string | null;
  } | null;
  /**
   * Where the BUDGET figure came from. Declared here only so a row carrying it
   * type-checks; `fiscalSourceLine` deliberately does not read it.
   */
  budget_basis_source?: {
    title?: string | null;
    publisher?: string | null;
    url?: string | null;
    page?: string | null;
  } | null;
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

/**
 * Which document a fiscal year's debt-service figure comes from, in words,
 * read off the row. Replaces a hardcoded "aligned with the Treasury APDMR
 * series while FY2025/26 remains budgeted": a literal pinned to one year,
 * shown against FY2026/27, whose debt service comes from the approved
 * Programme Based Budget and not the APDMR (issue #235). The document's own
 * title says whether it is a budget or an outturn.
 */
export function fiscalSourceLine(c: FiscalCurrent | null | undefined): string {
  const fy = c?.fiscal_year;
  const src = c?.debt_service_source;
  if (!fy) return 'The fiscal year of these figures is not recorded.';
  if (!src?.title) return `The source document for ${fy}'s debt-service figure is not recorded.`;
  const who = src.publisher ? `${src.publisher}, ` : '';
  const where = src.page ? ` (${src.page})` : '';
  return `${fy} debt service is from ${who}${src.title}${where}.`;
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

/**
 * The worked arithmetic under the headline, in trillions of shillings.
 *
 * The page used to print `(ds / 1000).toFixed(3)` + "T", which assumed the
 * figures were in billions. They are raw KES (the stage1 3a unit migration),
 * so it rendered "KSh 2315900000.000T" — hidden only because the card is not
 * drawn while the current year lacks a recurrent/development split.
 */
export function ratioWorking(a: RevenueAllocation): string {
  const t = (kes: number) => (kes / 1e12).toFixed(3);
  return (
    `total debt service of about KSh ${t(a.ds)}T divided by tax & non-tax revenue of about ` +
    `KSh ${t(a.rev)}T (${t(a.ds)} ÷ ${t(a.rev)} × 100 ≈ ${a.debtServicePerRev.toFixed(1)})`
  );
}
