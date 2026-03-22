/**
 * Custom React Query hooks for debt data
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import {
  CountyPendingBillsResponse,
  DebtSustainabilityResponse,
  DebtTimelineResponse,
  getCountyDebtData,
  getCountyDebtTimeline,
  getCountyPendingBills,
  getDebtBreakdown,
  getDebtComparison,
  getDebtRiskAssessment,
  getDebtSustainability,
  getDebtSustainabilityIndicators,
  getDebtTimeline,
  getNationalDebtOverview,
  getNationalLoans,
  getPendingBills,
  getPendingBillsSummary,
  getTopLoans,
  PendingBillsResponse,
  PendingBillsSummaryResponse,
} from '../api/debt';
import { DebtDataResponse } from '../api/types';

// Query keys for debt
const QUERY_KEYS = {
  debt: ['debt'] as const,
  countyDebt: (countyId: string) => ['debt', 'county', countyId] as const,
  nationalOverview: ['debt', 'national'] as const,
  breakdown: (countyId?: string) => ['debt', 'breakdown', countyId] as const,
  timeline: (countyId?: string, years?: number) => ['debt', 'timeline', countyId, years] as const,
  nationalTimeline: ['debt', 'national-timeline'] as const,
  comparison: (countyIds: string[]) => ['debt', 'comparison', countyIds] as const,
  topLoans: (limit: number) => ['debt', 'top-loans', limit] as const,
  nationalLoans: ['debt', 'national-loans'] as const,
  pendingBills: ['debt', 'pending-bills'] as const,
  pendingBillsSummary: ['debt', 'pending-bills-summary'] as const,
  countyPendingBills: (countyId: string) => ['debt', 'pending-bills', 'county', countyId] as const,
  sustainability: (countyId?: string) => ['debt', 'sustainability', countyId] as const,
  debtSustainability: ['debt', 'debt-sustainability'] as const,
  riskAssessment: ['debt', 'risk-assessment'] as const,
};

// Get debt data for a county
export const useCountyDebtData = (
  countyId: string,
  options?: Omit<UseQueryOptions<DebtDataResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyDebt(countyId),
    queryFn: () => getCountyDebtData(countyId),
    enabled: !!countyId,
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Get national debt overview
export const useNationalDebtOverview = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.nationalOverview,
    queryFn: getNationalDebtOverview,
    staleTime: 60 * 60 * 1000, // 1 hour — national debt overview rarely changes
    ...options,
  });
};

// Get debt breakdown by category
export const useDebtBreakdown = (
  countyId?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.breakdown(countyId),
    queryFn: () => getDebtBreakdown(countyId),
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Get county debt timeline data
export const useCountyDebtTimeline = (
  countyId?: string,
  years?: number,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.timeline(countyId, years),
    queryFn: () => getCountyDebtTimeline(countyId, years),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get national debt timeline (historical year-by-year external/domestic breakdown)
export const useDebtTimeline = (
  options?: Omit<UseQueryOptions<DebtTimelineResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.nationalTimeline,
    queryFn: getDebtTimeline,
    staleTime: 60 * 60 * 1000, // 1 hour (historical data rarely changes)
    ...options,
  });
};

// Get debt comparison between counties
export const useDebtComparison = (
  countyIds: string[],
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.comparison(countyIds),
    queryFn: () => getDebtComparison(countyIds),
    enabled: countyIds.length > 0,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get top loans/debt sources
export const useTopLoans = (
  limit: number = 10,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.topLoans(limit),
    queryFn: () => getTopLoans(limit),
    staleTime: 60 * 60 * 1000, // 1 hour
    ...options,
  });
};

// Get debt sustainability indicators
export const useDebtSustainabilityIndicators = (
  countyId?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.sustainability(countyId),
    queryFn: () => getDebtSustainabilityIndicators(countyId),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get debt risk assessment
export const useDebtRiskAssessment = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.riskAssessment,
    queryFn: getDebtRiskAssessment,
    staleTime: 20 * 60 * 1000, // 20 minutes
    ...options,
  });
};

// Get national government individual loans
export const useNationalLoans = (options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>) => {
  return useQuery({
    queryKey: QUERY_KEYS.nationalLoans,
    queryFn: getNationalLoans,
    staleTime: 60 * 60 * 1000, // 1 hour — loan records rarely change
    ...options,
  });
};

// Get government pending bills (from COB reports)
// May return 503 if pending bills data not yet seeded — don't retry aggressively
export const usePendingBills = (
  options?: Omit<UseQueryOptions<PendingBillsResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.pendingBills,
    queryFn: getPendingBills,
    staleTime: 60 * 60 * 1000, // 1 hour — pending bills data updated quarterly
    retry: 1,
    ...options,
  });
};

// Enhanced pending bills summary with breakdown, aging, top counties, trend
// May fail if PendingBill table not populated — graceful degradation
export const usePendingBillsSummary = (
  options?: Omit<UseQueryOptions<PendingBillsSummaryResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.pendingBillsSummary,
    queryFn: getPendingBillsSummary,
    staleTime: 60 * 60 * 1000,
    retry: 1,
    ...options,
  });
};

// County-level pending bills breakdown
export const useCountyPendingBills = (
  countyId: string,
  options?: Omit<UseQueryOptions<CountyPendingBillsResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyPendingBills(countyId),
    queryFn: () => getCountyPendingBills(countyId),
    enabled: !!countyId,
    staleTime: 30 * 60 * 1000,
    ...options,
  });
};

// National debt sustainability indicators (GDP ratio, projections, regional peers)
export const useDebtSustainability = (
  options?: Omit<UseQueryOptions<DebtSustainabilityResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.debtSustainability,
    queryFn: getDebtSustainability,
    staleTime: 60 * 60 * 1000,
    ...options,
  });
};
