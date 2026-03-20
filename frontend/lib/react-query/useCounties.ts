/**
 * Custom React Query hooks for counties data
 */
import { AccountabilityScorecard, CountyComprehensive } from '@/types';
import { useInfiniteQuery, useQuery, UseQueryOptions } from '@tanstack/react-query';
import {
  getCounties,
  getCountiesPaginated,
  getCounty,
  getCountyByCode,
  getCountyComprehensive,
  getCountyAccountability,
  getCountyFinancialSummary,
  getFlaggedCounties,
  getTopPerformingCounties,
  searchCounties,
} from '../api/counties';
import { CountyFilters, CountyResponse } from '../api/types';

// Query keys for counties
const QUERY_KEYS = {
  counties: ['counties'] as const,
  county: (id: string) => ['counties', id] as const,
  countyByCode: (code: string) => ['counties', 'code', code] as const,
  countiesFiltered: (filters?: CountyFilters) => ['counties', 'filtered', filters] as const,
  countiesSearch: (query: string) => ['counties', 'search', query] as const,
  topPerforming: (limit: number) => ['counties', 'top-performing', limit] as const,
  flagged: ['counties', 'flagged'] as const,
  financialSummary: (id: string) => ['counties', id, 'financial-summary'] as const,
  accountability: (id: string) => ['counties', id, 'accountability'] as const,
};

// Get all counties
export const useCounties = (
  filters?: CountyFilters,
  options?: Omit<UseQueryOptions<CountyResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countiesFiltered(filters),
    queryFn: () => getCounties(filters),
    staleTime: 30 * 60 * 1000, // 30 minutes — county list rarely changes
    ...options,
  });
};

// Get single county by ID
export const useCounty = (
  id: string,
  options?: Omit<UseQueryOptions<CountyResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.county(id),
    queryFn: () => getCounty(id),
    enabled: !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get county by code
export const useCountyByCode = (
  code: string,
  options?: Omit<UseQueryOptions<CountyResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyByCode(code),
    queryFn: () => getCountyByCode(code),
    enabled: !!code,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Infinite query for paginated counties
export const useCountiesInfinite = (
  limit: number = 20,
  filters?: Omit<CountyFilters, 'page' | 'limit'>
) => {
  return useInfiniteQuery({
    queryKey: ['counties', 'infinite', limit, filters],
    queryFn: ({ pageParam = 1 }) => getCountiesPaginated(pageParam, limit, filters),
    getNextPageParam: (lastPage) => {
      if (lastPage.pagination.page < lastPage.pagination.totalPages) {
        return lastPage.pagination.page + 1;
      }
      return undefined;
    },
    initialPageParam: 1,
    staleTime: 5 * 60 * 1000,
  });
};

// Search counties
export const useCountiesSearch = (
  query: string,
  options?: Omit<UseQueryOptions<CountyResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countiesSearch(query),
    queryFn: () => searchCounties(query),
    enabled: query.length > 2, // Only search if query is longer than 2 characters
    staleTime: 2 * 60 * 1000, // 2 minutes for search results
    ...options,
  });
};

// Get top performing counties
export const useTopPerformingCounties = (
  limit: number = 10,
  options?: Omit<UseQueryOptions<CountyResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.topPerforming(limit),
    queryFn: () => getTopPerformingCounties(limit),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get flagged counties
export const useFlaggedCounties = (
  options?: Omit<UseQueryOptions<CountyResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.flagged,
    queryFn: getFlaggedCounties,
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
};

// Get county financial summary
export const useCountyFinancialSummary = (
  id: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.financialSummary(id),
    queryFn: () => getCountyFinancialSummary(id),
    enabled: !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get county accountability scorecard
export const useCountyAccountability = (
  id: string,
  options?: Omit<UseQueryOptions<AccountabilityScorecard>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.accountability(id),
    queryFn: () => getCountyAccountability(id),
    enabled: !!id,
    staleTime: 10 * 60 * 1000,
    ...options,
  });
};

// Get comprehensive county data (one-stop detail)
export const useCountyComprehensive = (
  id: string,
  options?: Omit<UseQueryOptions<CountyComprehensive>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: ['counties', id, 'comprehensive'] as const,
    queryFn: () => getCountyComprehensive(id),
    enabled: !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};
