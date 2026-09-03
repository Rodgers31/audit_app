/**
 * Fiscal API service — national budget, revenue, borrowing, debt service data
 */
import { apiClient } from './axios';
import { FISCAL_ENDPOINTS } from './endpoints';

export interface FiscalYearData {
  fiscal_year: string;
  /** Declared unit of the money fields. "KES" = raw KES (stage1 3a
   *  migration). Absent on a pre-migration backend, whose values are
   *  bare billions — convert with toRawKES(), never by guessing. */
  unit?: 'KES';
  // Every money field is NULLABLE. `_row_to_dict` emits None for any value
  // it cannot source, and that is the normal case rather than an edge one:
  // a fiscal year carries only an enacted budget until the Controller of
  // Budget publishes execution, so FY 2026/27 has an appropriated_budget and
  // nulls for the rest until mid-November.
  //
  // Declaring these as `number` (reported as F2 on #136) let `null` flow into
  // arithmetic and formatting as though it were data — `null` coerces to 0 in
  // a sum, and 0 is a claim. Making the contract honest is what forces each
  // call site to decide what absence should look like.
  appropriated_budget: number | null;
  total_revenue: number | null;
  tax_revenue: number | null;
  non_tax_revenue: number | null;
  total_borrowing: number | null;
  borrowing_pct_of_budget: number | null;
  debt_service_cost: number | null;
  debt_service_per_shilling: number | null;
  debt_ceiling: number | null;
  actual_debt: number | null;
  debt_ceiling_usage_pct: number | null;
  development_spending: number | null;
  recurrent_spending: number | null;
  county_allocation: number | null;
}

/**
 * Fiscal anchor. The KES 10T NUMERIC debt ceiling was repealed by the PFM
 * (Amendment) Act 2023, which replaced it with a 55%-of-GDP (present-value)
 * anchor. The per-year debt_ceiling/debt_ceiling_usage_pct fields are
 * historical context only — not the binding rule.
 */
export interface DebtAnchor {
  anchor_pct_gdp: number;
  basis: string;
  debt_to_gdp_pct: number | null;
  debt_to_gdp_year: number | null;
  debt_to_gdp_basis: string;
  above_anchor: boolean | null;
  former_numeric_ceiling_kes_billion: number;
  former_ceiling_repealed: boolean;
}

export interface FiscalSummaryResponse {
  status: string;
  data_source: string;
  last_updated: string;
  source: string;
  current: FiscalYearData;
  history: FiscalYearData[];
  total_fiscal_years: number;
  debt_anchor?: DebtAnchor;
}

export const getFiscalSummary = async (): Promise<FiscalSummaryResponse> => {
  const response = await apiClient.get<FiscalSummaryResponse>(FISCAL_ENDPOINTS.SUMMARY);
  return response.data;
};
