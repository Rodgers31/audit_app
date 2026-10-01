/**
 * Custom React Query hooks for budget data
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { SSR_HYDRATED_STALE_TIME_MS } from './isr';
import {
  getBudgetAllocation,
  getBudgetComparison,
  getBudgetEnhanced,
  getBudgetOverview,
  getBudgetTrends,
  getBudgetUtilizationSummary,
  getNationalBudgetSummary,
  getSectorBudgetAllocation,
} from '../api/budget';
import { BudgetAllocationResponse, BudgetComparisonAllocationResponse } from '../api/types';

// Query keys for budget
const QUERY_KEYS = {
  budget: ['budget'] as const,
  allocation: (countyId: string, fiscalYear?: string) =>
    ['budget', 'allocation', countyId, fiscalYear] as const,
  comparison: (countyIds: string[], fiscalYear?: string) =>
    ['budget', 'comparison', countyIds, fiscalYear] as const,
  nationalSummary: (fiscalYear?: string) => ['budget', 'national', fiscalYear] as const,
  trends: (countyId: string, years?: number) => ['budget', 'trends', countyId, years] as const,
  sectorAllocation: (sector: string, fiscalYear?: string) =>
    ['budget', 'sector', sector, fiscalYear] as const,
  utilizationSummary: (fiscalYear?: string) => ['budget', 'utilization', fiscalYear] as const,
  overview: ['budget', 'overview'] as const,
  enhanced: ['budget', 'enhanced'] as const,
};

// Selected county account; fiscalYear is a legacy query, not a period selector.
export const useBudgetAllocation = (
  countyId: string,
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<BudgetAllocationResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.allocation(countyId, fiscalYear),
    queryFn: ({ signal }) => getBudgetAllocation(countyId, fiscalYear, signal),
    enabled: !!countyId,
    staleTime: 30 * 60 * 1000, // 30 minutes — budget data rarely changes
    ...options,
  });
};

// Get budget comparison between counties
export const useBudgetComparison = (
  countyIds: string[],
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<BudgetComparisonAllocationResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.comparison(countyIds, fiscalYear),
    queryFn: ({ signal }) => getBudgetComparison(countyIds, fiscalYear, signal),
    enabled: countyIds.length > 0,
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Get national budget summary
export const useNationalBudgetSummary = (
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.nationalSummary(fiscalYear),
    queryFn: ({ signal }) => getNationalBudgetSummary(fiscalYear, signal),
    staleTime: 60 * 60 * 1000, // 1 hour — national budget changes infrequently
    ...options,
  });
};

// Get budget trends for a county
export const useBudgetTrends = (
  countyId: string,
  years?: number,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.trends(countyId, years),
    queryFn: ({ signal }) => getBudgetTrends(countyId, years, signal),
    enabled: !!countyId,
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get sector-wise budget allocation
export const useSectorBudgetAllocation = (
  sector: string,
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.sectorAllocation(sector, fiscalYear),
    queryFn: ({ signal }) => getSectorBudgetAllocation(sector, fiscalYear, signal),
    enabled: !!sector,
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get consolidated budget overview (sectors + fiscal history + county utilization)
export const useBudgetOverview = (options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>) => {
  return useQuery({
    queryKey: QUERY_KEYS.overview,
    queryFn: ({ signal }) => getBudgetOverview(signal),
    staleTime: SSR_HYDRATED_STALE_TIME_MS, // read from SSR state; see ./isr
    ...options,
  });
};

// Get enhanced budget data (revenue by source, economic context, commitment pipeline)
export const useBudgetEnhanced = (options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>) => {
  return useQuery({
    queryKey: QUERY_KEYS.enhanced,
    queryFn: ({ signal }) => getBudgetEnhanced(signal),
    staleTime: SSR_HYDRATED_STALE_TIME_MS, // read from SSR state; see ./isr
    ...options,
  });
};

// Get budget utilization summary
export const useBudgetUtilizationSummary = (
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.utilizationSummary(fiscalYear),
    queryFn: ({ signal }) => getBudgetUtilizationSummary(fiscalYear, signal),
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};
