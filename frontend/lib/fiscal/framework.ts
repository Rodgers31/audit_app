/**
 * The fiscal-framework split of a fiscal year, and the only way the budget
 * surfaces are allowed to draw one.
 *
 * WHY THIS EXISTS (issue #237)
 * ----------------------------
 * Every budget breakdown on the site drew recurrent / development / counties
 * against `appropriated_budget` and subtracted `debt_service_cost` from
 * recurrent to get "recurrent ex-debt". Those are three different measures:
 *
 *   appropriated_budget   COB gross: voted + Consolidated Fund Services.
 *                         Counts principal REDEMPTION, excludes county
 *                         transfers. FY 2026/27: 5,485.7B.
 *   debt_service_cost     Interest PLUS principal (APDMR). FY 2026/27: 2,315.9B.
 *   recurrent (Treasury)  Contains INTEREST (1,254.2B) and no principal.
 *
 * So "recurrent minus debt service" took 1,061.6B of principal out of a
 * figure that never held it, and the residual slices silently absorbed the
 * gap between the bases.
 *
 * The API now ships `fiscal_framework`: the split AND the total it
 * reconciles to, all read from one column of the Budget Summary's Annex
 * Table 2a. The helpers below draw ONLY from that object, and refuse (return
 * null) when it is absent or does not add up, so there is no residual slice
 * anywhere. Money is in KSh BILLION, as the key names say.
 */

export const FISCAL_FRAMEWORK_BASIS = 'treasury_fiscal_framework';

/** Preserve a declared vintage; older payloads cannot be dated by year alone. */
export function fiscalColumnLabel(row: { fiscal_framework?: FiscalFramework | null }): string {
  const column = row.fiscal_framework?.source?.column;
  return column && ['Actual', 'Preliminary', 'Supplementary I', 'Approved'].includes(column)
    ? column : 'Vintage unconfirmed';
}

export interface FiscalFramework {
  basis: string;
  identified_by?: 'approved_budget' | 'revenue_column' | string;
  total_expenditure_billion: number | null;
  recurrent_billion: number | null;
  interest_payments_billion: number | null;
  development_billion: number | null;
  county_transfers_billion: number | null;
  county_equitable_share_billion?: number | null;
  contingency_billion: number | null;
  total_revenue_incl_aia_billion: number | null;
  ordinary_revenue_billion: number | null;
  ministerial_aia_billion: number | null;
  grants_billion: number | null;
  fiscal_deficit_incl_grants_billion?: number | null;
  total_financing_billion: number | null;
  net_foreign_financing_billion?: number | null;
  net_domestic_financing_billion?: number | null;
  adjustment_to_cash_basis_billion?: number | null;
  statistical_discrepancy_billion?: number | null;
  tax_revenue_billion?: number | null;
  non_tax_revenue_billion?: number | null;
  tax_heads_billion?: Record<string, number | null>;
  tax_split_absent_reason?: string | null;
  source?: {
    title?: string;
    publisher?: string;
    url?: string | null;
    page?: string;
    table?: string;
    edition?: string;
    column?: string;
  };
  checks?: string[];
}

/** How far a sum of one-decimal figures may drift from its printed total. */
const TOLERANCE_B = 0.5;

const num = (v: number | null | undefined): v is number =>
  typeof v === 'number' && Number.isFinite(v);

/** The object, if it is present AND declares the one basis this module draws. */
export function frameworkOf(
  row: { fiscal_framework?: FiscalFramework | null } | null | undefined,
): FiscalFramework | null {
  const ff = row?.fiscal_framework;
  return ff && ff.basis === FISCAL_FRAMEWORK_BASIS ? ff : null;
}

export interface FrameworkUses {
  total: number;
  interest: number;
  recurrentExInterest: number;
  development: number;
  counties: number;
  contingency: number;
}

/**
 * Where the money goes, on one basis. Interest is split OUT of recurrent
 * (it is inside it); principal is not subtracted, because it is not there.
 * Null unless every part is present and the parts reconcile to the total.
 */
export function frameworkUses(ff: FiscalFramework | null): FrameworkUses | null {
  if (!ff) return null;
  const {
    total_expenditure_billion: total,
    recurrent_billion: recurrent,
    interest_payments_billion: interest,
    development_billion: development,
    county_transfers_billion: counties,
    contingency_billion: contingency,
  } = ff;
  if (
    !num(total) ||
    !num(recurrent) ||
    !num(interest) ||
    !num(development) ||
    !num(counties) ||
    !num(contingency) ||
    total <= 0 ||
    interest > recurrent
  ) {
    return null;
  }
  if (Math.abs(recurrent + development + counties + contingency - total) > TOLERANCE_B) {
    return null;
  }
  return {
    total,
    interest,
    recurrentExInterest: recurrent - interest,
    development,
    counties,
    contingency,
  };
}

export interface FrameworkSources {
  /** What the sources sum to. Equals the spending total within rounding. */
  total: number;
  /** Null when the edition prints no tax / non-tax split. */
  tax: number | null;
  nonTax: number | null;
  /** Tax + non-tax, always present. */
  ordinaryRevenue: number;
  aia: number;
  grants: number;
  borrowing: number;
  /**
   * Adjustment to cash basis minus statistical discrepancy — two rows the
   * table PRINTS, which settled years need to reconcile. Zero in a budget
   * year. Signed: negative means the recorded sources exceed spending.
   */
  cashAdjustment: number;
}

/**
 * Where the money comes from, on the same basis. Reconciles to the spending
 * total through the table's own rows:
 *
 *   expenditure = ordinary revenue + A-i-A + grants + financing
 *                 + adjustment to cash basis - statistical discrepancy
 */
export function frameworkSources(ff: FiscalFramework | null): FrameworkSources | null {
  if (!ff) return null;
  const ordinary = ff.ordinary_revenue_billion;
  const aia = ff.ministerial_aia_billion;
  const grants = ff.grants_billion;
  const borrowing = ff.total_financing_billion;
  const total = ff.total_expenditure_billion;
  const adjustment = ff.adjustment_to_cash_basis_billion;
  const discrepancy = ff.statistical_discrepancy_billion;
  // Both rows are required: an absent one is not a zero one.
  if (
    !num(ordinary) ||
    !num(aia) ||
    !num(grants) ||
    !num(borrowing) ||
    !num(total) ||
    !num(adjustment) ||
    !num(discrepancy)
  ) {
    return null;
  }
  const cashAdjustment = adjustment - discrepancy;
  if (Math.abs(ordinary + aia + grants + borrowing + cashAdjustment - total) > TOLERANCE_B) {
    return null;
  }
  const tax = num(ff.tax_revenue_billion) ? ff.tax_revenue_billion : null;
  const nonTax = num(ff.non_tax_revenue_billion) ? ff.non_tax_revenue_billion : null;
  const splitOk = tax != null && nonTax != null && Math.abs(tax + nonTax - ordinary) <= TOLERANCE_B;
  return {
    total,
    tax: splitOk ? tax : null,
    nonTax: splitOk ? nonTax : null,
    ordinaryRevenue: ordinary,
    aia,
    grants,
    borrowing,
    cashAdjustment,
  };
}

/** "Annex Table 2a, PDF p.63 — Budget Summary for the FY 2026/27 Budget". */
export function frameworkCitation(ff: FiscalFramework | null): string | null {
  const s = ff?.source;
  if (!s?.page) return null;
  return s.edition ? `${s.edition}, ${s.page}` : `Budget Summary, ${s.page}`;
}
