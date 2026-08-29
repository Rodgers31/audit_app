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
  appropriated_budget: number;
  total_revenue: number;
  tax_revenue: number;
  non_tax_revenue: number;
  total_borrowing: number;
  borrowing_pct_of_budget: number;
  debt_service_cost: number;
  debt_service_per_shilling: number;
  debt_ceiling: number;
  actual_debt: number;
  debt_ceiling_usage_pct: number;
  development_spending: number;
  recurrent_spending: number;
  county_allocation: number;
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
