/**
 * Budget API service
 */
import { apiClient } from './axios';
import { apiGet } from './request';
import { BUDGET_ENDPOINTS, COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import { ApiResponse, BudgetAllocationResponse } from './types';

// Get budget allocation for a county
export const getBudgetAllocation = async (
  countyId: string,
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<BudgetAllocationResponse> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.BUDGET(countyId), queryParams);
  const response = await apiGet<ApiResponse<BudgetAllocationResponse>>(apiClient, url, signal);
  return response.data.data;
};

// Get budget comparison between counties
export const getBudgetComparison = async (
  countyIds: string[],
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<BudgetAllocationResponse[]> => {
  const queryParams: Record<string, any> = { county_ids: countyIds };
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(BUDGET_ENDPOINTS.COMPARISON, queryParams);
  const response = await apiGet<ApiResponse<BudgetAllocationResponse[]>>(apiClient, url, signal);
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
