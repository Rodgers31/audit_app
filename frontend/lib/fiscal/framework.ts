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
  fiscal_year?: string;
  measure_contract_version?: string;
  precision_kes?: number;
  measure_qualifications?: Record<string, FrameworkMeasureProof>;
  absent_reasons?: Record<string, string>;
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
    sha256?: string;
    title?: string;
    publisher?: string;
    url?: string | null;
    page?: string | number;
    table?: string;
    edition?: string;
    column?: string;
  };
  checks?: string[];
  nominal_gdp_billion?: number | null;
}

/** How far a sum of one-decimal figures may drift from its printed total. */
const EXPENDITURE_TOLERANCE_B = 0.250001;
const REVENUE_TOLERANCE_B = 0.150001;
const CASH_SOURCES_TOLERANCE_B = 0.350001;

const num = (v: number | null | undefined): v is number =>
  typeof v === 'number' && Number.isFinite(v);

export interface FrameworkMeasureProof {
  value_kes: number;
  fiscal_year: string;
  basis: string;
  vintage: string | null;
  precision_kes: number;
  source: NonNullable<FiscalFramework['source']> & { cell?: string };
}
const CELLS: Record<string, string> = {
  total_expenditure_billion: 'Expenditure and Net Lending', recurrent_billion: 'Recurrent Expenditure',
  interest_payments_billion: 'Interest Payments', development_billion: 'Development and Net Lending',
  county_transfers_billion: 'County Transfers', county_equitable_share_billion: 'Equitable Share',
  contingency_billion: 'Contingency', total_revenue_incl_aia_billion: 'Total Revenue including A-i-A',
  ordinary_revenue_billion: 'Ordinary Revenue', ministerial_aia_billion: 'Ministerial Appropriation in Aid',
  grants_billion: 'Grants', fiscal_deficit_incl_grants_billion: 'Fiscal Balance including Grants (sign reversed)',
  total_financing_billion: 'Total Financing', net_foreign_financing_billion: 'Net Foreign Financing',
  net_domestic_financing_billion: 'Net Domestic Financing', adjustment_to_cash_basis_billion: 'Adjustment to Cash Basis',
  statistical_discrepancy_billion: 'Statistical Discrepancy', nominal_gdp_billion: 'Nominal GDP',
  tax_revenue_billion: 'Tax Revenue', non_tax_revenue_billion: 'Non-Tax Revenue',
};
const SIGNED = new Set(['fiscal_deficit_incl_grants_billion', 'total_financing_billion',
  'net_foreign_financing_billion', 'net_domestic_financing_billion',
  'adjustment_to_cash_basis_billion', 'statistical_discrepancy_billion']);
const fiscalYear = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const m = value.match(/^(?:FY\s*)?(\d{4})\/(\d{2})$/);
  return m && (+m[1] + 1) % 100 === +m[2] ? `${m[1]}/${m[2]}` : null;
};
function validSource(s: FiscalFramework['source']): boolean {
  if (!s || typeof s.url !== 'string' || typeof s.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(s.sha256)) return false;
  if (!((typeof s.page === 'number' && Number.isInteger(s.page) && s.page > 0) ||
        (typeof s.page === 'string' && (/^(?:p(?:ages?)?\.?\s*)?[1-9][0-9]{0,8}$/i.test(s.page.trim()) || /\bPDF[ \t]+pp?\.[ \t]*[1-9][0-9]{0,8}(?:[ \t]*(?:,|[-–])[ \t]*[1-9][0-9]{0,8})*\b/i.test(s.page))))) return false;
  if (['title', 'publisher', 'table', 'edition'].some(k => {
    const v = (s as Record<string, unknown>)[k];
    return v != null && (typeof v !== 'string' || !v.trim() || v.length > 2000);
  })) return false;
  try {
    const u = new URL(s.url);
    return u.protocol === 'https:' && ['treasury.go.ke', 'www.treasury.go.ke', 'cob.go.ke', 'www.cob.go.ke'].includes(u.hostname) &&
      !u.username && !u.password && !u.hash && (!u.port || u.port === '443');
  } catch { return false; }
}
/** Validate the displayed cell's own witness, including billion-to-KES conversion. */
export function qualifiedFrameworkValue(ff: FiscalFramework | null, field: string): number | null {
  if (!ff || ff.basis !== FISCAL_FRAMEWORK_BASIS || ff.measure_contract_version !== 'fiscal-measures-v1' ||
      ff.precision_kes !== 100_000_000 || !fiscalYear(ff.fiscal_year) || !validSource(ff.source) || !CELLS[field]) return null;
  const value = (ff as unknown as Record<string, unknown>)[field];
  const q = ff.measure_qualifications?.[field];
  if (typeof value !== 'number' || !Number.isFinite(value) || (!SIGNED.has(field) && value < 0) ||
      !q || !Object.prototype.hasOwnProperty.call(q, 'vintage') || typeof q.value_kes !== 'number' || !Number.isFinite(q.value_kes) ||
      Math.round(value * 1e9 * 100) / 100 !== q.value_kes || q.value_kes % 100_000_000 !== 0 || q.precision_kes !== 100_000_000 ||
      fiscalYear(q.fiscal_year) !== fiscalYear(ff.fiscal_year) || !validSource(q.source)) return null;
  const basis = ['ordinary_revenue_billion', 'tax_revenue_billion', 'non_tax_revenue_billion'].includes(field)
    ? 'ordinary_revenue_excl_aia' : ({ total_revenue_incl_aia_billion: 'revenue_including_aia',
      ministerial_aia_billion: 'ministerial_appropriations_in_aid', nominal_gdp_billion: 'nominal_gdp_fiscal_year' } as Record<string,string>)[field] ?? FISCAL_FRAMEWORK_BASIS;
  const column = ff.source?.column;
  const known = typeof q.vintage === 'string' && ['Actual', 'Preliminary', 'Supplementary I', 'Approved'].includes(q.vintage);
  const unknown = (q.vintage == null || q.vintage === 'Vintage unconfirmed') &&
    (column == null || column === '' || column === 'Vintage unconfirmed');
  if (q.basis !== basis || !(known && q.vintage === column || unknown) || q.source.cell !== CELLS[field] ||
      (['url', 'sha256', 'page', 'table', 'edition', 'column'] as const).some(k => q.source[k] !== ff.source?.[k])) return null;
  return value;
}

/** A column's core must be independently qualified and reconcile on its own basis. */
export function frameworkOf(
  row: { fiscal_framework?: FiscalFramework | null; fiscal_year?: string | null } | null | undefined,
): FiscalFramework | null {
  const ff = row?.fiscal_framework;
  if (!ff || (row?.fiscal_year != null && fiscalYear(row.fiscal_year) !== fiscalYear(ff.fiscal_year))) return null;
  const keys = ['total_revenue_incl_aia_billion', 'total_expenditure_billion',
    'fiscal_deficit_incl_grants_billion', 'total_financing_billion', 'grants_billion',
    'adjustment_to_cash_basis_billion', 'statistical_discrepancy_billion'];
  const values = keys.map(key => qualifiedFrameworkValue(ff, key));
  if (values.some(v => v == null)) return null;
  const [revenue, expenditure, deficit, financing, grants, adjustment, discrepancy] = values as number[];
  return Math.abs(revenue + grants - expenditure + deficit) <= 0.200001 &&
    Math.abs(deficit - financing - adjustment + discrepancy) <= 0.200001 ? ff : null;
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
  if (!frameworkOf({ fiscal_framework: ff }) || !ff) return null;
  if (['total_expenditure_billion', 'recurrent_billion', 'interest_payments_billion',
    'development_billion', 'county_transfers_billion', 'contingency_billion'].some(k => qualifiedFrameworkValue(ff, k) == null)) return null;
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
  if (Math.abs(recurrent + development + counties + contingency - total) > EXPENDITURE_TOLERANCE_B) {
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
  if (!frameworkOf({ fiscal_framework: ff }) || !ff) return null;
  if (['ordinary_revenue_billion', 'ministerial_aia_billion', 'grants_billion', 'total_financing_billion',
    'total_expenditure_billion', 'adjustment_to_cash_basis_billion', 'statistical_discrepancy_billion'].some(k => qualifiedFrameworkValue(ff, k) == null)) return null;
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
  if (!num(ff.total_revenue_incl_aia_billion) || Math.abs(ordinary + aia - ff.total_revenue_incl_aia_billion) > REVENUE_TOLERANCE_B) return null;
  const cashAdjustment = adjustment - discrepancy;
  if (Math.abs(ordinary + aia + grants + borrowing + cashAdjustment - total) > CASH_SOURCES_TOLERANCE_B) {
    return null;
  }
  const tax = qualifiedFrameworkValue(ff, 'tax_revenue_billion');
  const nonTax = qualifiedFrameworkValue(ff, 'non_tax_revenue_billion');
  const splitOk = !ff.tax_split_absent_reason && tax != null && nonTax != null && Math.abs(tax + nonTax - ordinary) <= REVENUE_TOLERANCE_B;
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
