/**
 * Budget API service
 */
import { apiClient } from './axios';
import { apiGet } from './request';
import { BUDGET_ENDPOINTS, COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import { ApiResponse, BudgetAllocationResponse, BudgetComparisonAllocationResponse } from './types';

/** Reject successful HTTP bodies that do not carry the flat account contract. */
function assertCountyBudgetAccount(value: unknown): asserts value is BudgetAllocationResponse {
  const object = (input: unknown): input is Record<string, unknown> =>
    input !== null && typeof input === 'object' && !Array.isArray(input);
  const text = (input: unknown) => input === null || typeof input === 'string';
  const amount = (input: unknown) => input === null ||
    (typeof input === 'number' && Number.isFinite(input) && input >= 0);
  const count = (input: unknown) => typeof input === 'number' && Number.isInteger(input) && input >= 0;
  const period = (input: unknown) => input === null || (object(input) &&
    count(input.id) && input.id !== 0 && text(input.label) && text(input.start_date) && text(input.end_date));
  const sources = (input: unknown) => Array.isArray(input) && input.every(source =>
    object(source) && (source.id === null || (count(source.id) && source.id !== 0)) &&
    text(source.title) && text(source.publisher) && text(source.url) &&
    Array.isArray(source.page_refs) && source.page_refs.every(page => typeof page === 'string'));
  const reasons = (input: unknown) => object(input) &&
    Object.values(input).every(reason => typeof reason === 'string' && reason.trim().length > 0);
  const basis = (input: unknown) => input === null ||
    input === 'reported_total' || input === 'recurrent_plus_development';
  const emptyBreakdown = (input: unknown) => object(input) && Object.keys(input).length === 0;
  const sameMetadata = (left: unknown, right: unknown): boolean => {
    if (left === right) return true;
    if (Array.isArray(left) && Array.isArray(right))
      return left.length === right.length && left.every((item, index) => sameMetadata(item, right[index]));
    if (object(left) && object(right))
      return Object.keys(left).length === Object.keys(right).length &&
        Object.keys(left).every(key => Object.prototype.hasOwnProperty.call(right, key) && sameMetadata(left[key], right[key]));
    return false;
  };
  const fail = () => { throw new Error('Invalid county budget response'); };
  if (!object(value) || typeof value.county_id !== 'string' || !value.county_id ||
    typeof value.county_name !== 'string' || !value.county_name || !object(value.financial_summary)) return fail();
  const summary = value.financial_summary;
  if (!['total_budget', 'total_spent', 'budget_2025', 'budget_utilization', 'budget_execution_rate', 'revenue_2024'].every(key => amount(value[key])) ||
    !['total_allocation', 'total_spent', 'execution_rate'].every(key => amount(summary[key])) ||
    !period(value.fiscal_period) || !period(summary.fiscal_period) ||
    !sources(value.sources) || !sources(summary.sources) ||
    !reasons(value.absent_reasons) || !reasons(summary.absent_reasons) ||
    !basis(value.accounting_basis) || !basis(summary.accounting_basis) ||
    !text(value.currency) || !text(summary.currency) || !text(value.budget_source) ||
    !count(summary.budget_lines_count) ||
    !emptyBreakdown(value.expenditure_breakdown) || !emptyBreakdown(value.budget_allocation)) return fail();
  if (value.total_budget !== summary.total_allocation || value.budget_2025 !== summary.total_allocation ||
    value.total_spent !== summary.total_spent || value.budget_utilization !== summary.execution_rate ||
    value.budget_execution_rate !== summary.execution_rate || value.currency !== summary.currency ||
    value.accounting_basis !== summary.accounting_basis ||
    !sameMetadata(value.fiscal_period, summary.fiscal_period) ||
    !sameMetadata(value.sources, summary.sources) ||
    !sameMetadata(value.absent_reasons, summary.absent_reasons)) return fail();
  // Positive evidence is required for any published amount, including zero.
  if (summary.total_allocation !== null || summary.total_spent !== null || summary.execution_rate !== null) {
    const fiscalPeriod = summary.fiscal_period;
    const accountSources = summary.sources as Array<Record<string, unknown>>;
    if (!object(fiscalPeriod) || typeof fiscalPeriod.start_date !== 'string' ||
      typeof fiscalPeriod.end_date !== 'string' || !Number.isFinite(Date.parse(fiscalPeriod.start_date)) ||
      !Number.isFinite(Date.parse(fiscalPeriod.end_date)) || Date.parse(fiscalPeriod.end_date) < Date.parse(fiscalPeriod.start_date) ||
      typeof summary.currency !== 'string' || !summary.currency.trim() || summary.accounting_basis === null ||
      accountSources.length !== 1 || accountSources[0].id === null ||
      typeof accountSources[0].url !== 'string' || !accountSources[0].url.trim()) return fail();
  }
  if (summary.execution_rate !== null) {
    const allocated = summary.total_allocation as number | null;
    const spent = summary.total_spent as number | null;
    const rate = summary.execution_rate as number;
    if (allocated === null || allocated <= 0 || spent === null) return fail();
    const computed = spent / allocated * 100;
    if (!Number.isFinite(computed) || Math.abs(rate - computed) > Math.max(1, Math.abs(computed)) * 1e-12) return fail();
  }
  const absent = summary.absent_reasons as Record<string, unknown>;
  for (const key of ['total_allocation', 'total_spent', 'execution_rate']) {
    if (summary[key] === null && !absent[key]) return fail();
  }
}

/** Get the selected supported county account.
 * fiscalYear is retained for compatibility; the backend currently ignores
 * fiscal_year. Read fiscal_period from the response for the actual account.
 */
export const getBudgetAllocation = async (
  countyId: string,
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<BudgetAllocationResponse> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.BUDGET(countyId), queryParams);
  const response = await apiGet<unknown>(apiClient, url, signal);
  assertCountyBudgetAccount(response.data);
  return response.data;
};

// Get budget comparison between counties
export const getBudgetComparison = async (
  countyIds: string[],
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<BudgetComparisonAllocationResponse[]> => {
  const queryParams: Record<string, any> = { county_ids: countyIds };
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(BUDGET_ENDPOINTS.COMPARISON, queryParams);
  const response = await apiGet<ApiResponse<BudgetComparisonAllocationResponse[]>>(apiClient, url, signal);
  return response.data.data;
};

// Get national budget summary
export const getNationalBudgetSummary = async (fiscalYear?: string, signal?: AbortSignal): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(BUDGET_ENDPOINTS.NATIONAL, queryParams);
  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get budget trends for a county
export const getBudgetTrends = async (countyId: string, years?: number, signal?: AbortSignal): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (years) queryParams.years = years;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.BUDGET_TRENDS(countyId), queryParams);

  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get sector-wise budget allocation
export const getSectorBudgetAllocation = async (
  sector: string,
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(BUDGET_ENDPOINTS.SECTORS(sector), queryParams);
  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get budget utilization summary
export const getBudgetUtilizationSummary = async (fiscalYear?: string, signal?: AbortSignal): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(BUDGET_ENDPOINTS.UTILIZATION, queryParams);
  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get consolidated budget overview (merged sectors + fiscal history)
export const getBudgetOverview = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet(apiClient, BUDGET_ENDPOINTS.OVERVIEW, signal);
  return response.data;
};

// Get enhanced budget data (revenue sources, economic context, commitment pipeline)
export const getBudgetEnhanced = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet(apiClient, BUDGET_ENDPOINTS.ENHANCED, signal);
  return response.data;
};
