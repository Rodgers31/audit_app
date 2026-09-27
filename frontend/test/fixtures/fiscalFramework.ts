/**
 * FY 2026/27 and FY 2023/24 as /api/v1/fiscal/summary serves them after
 * issue #237. The fiscal_framework figures are read from Treasury's Budget
 * Summary, Annex Table 2a:
 *   FY 2026/27 — "Approved Budget" column, PDF p.63 of the FY 2026/27 edition
 *   FY 2023/24 — "Act." column of the same table (a settled year: non-zero
 *                cash-basis adjustment 45.4 and statistical discrepancy -16.8)
 * Money in KSh BILLION, as the key names say.
 */
import type { FiscalFramework } from '@/lib/fiscal/framework';

export const FF_2026_27: FiscalFramework = {
  basis: 'treasury_fiscal_framework',
  identified_by: 'approved_budget',
  total_expenditure_billion: 4785.2,
  recurrent_billion: 3538.7,
  interest_payments_billion: 1254.2,
  development_billion: 749.0,
  county_transfers_billion: 495.5,
  county_equitable_share_billion: 420.0,
  contingency_billion: 2.0,
  total_revenue_incl_aia_billion: 3629.7,
  ordinary_revenue_billion: 2985.7,
  ministerial_aia_billion: 644.0,
  grants_billion: 43.6,
  fiscal_deficit_incl_grants_billion: 1111.8,
  total_financing_billion: 1111.8,
  net_foreign_financing_billion: 116.2,
  net_domestic_financing_billion: 995.7,
  adjustment_to_cash_basis_billion: 0.0,
  statistical_discrepancy_billion: 0.0,
  tax_revenue_billion: 2858.7,
  non_tax_revenue_billion: 127.1,
  source: {
    title: 'Budget Summary',
    publisher: 'The National Treasury',
    page: 'Annex Table 2a, PDF p.63',
    edition: 'Budget Summary for the FY 2026/27 Budget',
  },
};

export const FF_2023_24_ACTUAL: FiscalFramework = {
  basis: 'treasury_fiscal_framework',
  identified_by: 'revenue_column',
  total_expenditure_billion: 3605.2,
  recurrent_billion: 2678.4,
  interest_payments_billion: 840.7,
  development_billion: 546.4,
  county_transfers_billion: 380.4,
  contingency_billion: 0.0,
  total_revenue_incl_aia_billion: 2702.7,
  ordinary_revenue_billion: 2288.9,
  ministerial_aia_billion: 413.7,
  grants_billion: 22.0,
  total_financing_billion: 818.3,
  adjustment_to_cash_basis_billion: 45.4,
  statistical_discrepancy_billion: -16.8,
  tax_revenue_billion: 2167.8,
  non_tax_revenue_billion: 121.1,
};

/** The FY 2026/27 row in bare billions (the flow hero's normalised input). */
export const FY_2026_27_BILLIONS = {
  fiscal_year: 'FY 2026/27',
  appropriated_budget: 5485.7,
  total_revenue: 2985.7,
  tax_revenue: 2858.7,
  non_tax_revenue: 127.1,
  total_borrowing: 1111.8,
  debt_service_cost: 2315.9,
  debt_service_per_shilling: 77.6,
  development_spending: 749.0,
  recurrent_spending: 3538.7,
  county_allocation: 495.5,
  debt_redemption_billion: 1061.6,
  fiscal_framework: FF_2026_27,
};
