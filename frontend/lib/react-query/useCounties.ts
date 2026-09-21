/**
 * Custom React Query hooks for counties data
 */
import { AccountabilityScorecard, CountyComprehensive } from '@/types';
import { useInfiniteQuery, useQuery, UseQueryOptions } from '@tanstack/react-query';
import {
  getCounties,
  getCountyFiscalYears,
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
import type { CountyFiscalYears } from '../utils';

/** Key prefix for the filtered county list. */
export const COUNTIES_FILTERED_KEY_ROOT = ['counties', 'filtered'] as const;

/**
 * Cache key for the filtered county list.
 *
 * Shared by the client hook and by the server components that prefetch the
 * list (`app/page.tsx`, `app/counties/page.tsx`) so the two cannot drift —
 * when they do, the SSR payload is stranded in the HTML under a key nobody
 * reads and the page falls back to a client fetch.
 *
 * Filters are normalised first: React Query hashes keys with JSON.stringify,
 * which renders `undefined` as `null` but an all-undefined object as `{}`, so
 * `getCounties(undefined)` and `getCounties({fiscalYear: undefined})` — which
 * issue the byte-identical request — were landing on two different cache
 * entries. `CountiesPageClient` calls `useCounties({fiscalYear: pickedYear})`
 * with `pickedYear` undefined on first render; without this collapse it never
 * found what `app/counties/page.tsx` had just prefetched for it.
 */
export const countiesFilteredKey = (filters?: CountyFilters) =>
  ['counties', 'filtered', normalizeCountyFilters(filters)] as const;

/**
 * Drop keys whose value is `undefined`, and collapse an object with nothing
 * left onto `undefined`.
 *
 * Only `undefined` is dropped. Every param `getCounties` sends is guarded by a
 * truthiness check on a *defined* value, so this cannot change which request a
 * key stands for — it only stops two spellings of "no filters" from splitting
 * the cache.
 */
function normalizeCountyFilters(filters?: CountyFilters): CountyFilters | undefined {
  if (!filters) return undefined;
  const entries = Object.entries(filters).filter(([, v]) => v !== undefined);
  return entries.length ? (Object.fromEntries(entries) as CountyFilters) : undefined;
}

// Query keys for counties
const QUERY_KEYS = {
  counties: ['counties'] as const,
  county: (id: string) => ['counties', id] as const,
  countyByCode: (code: string) => ['counties', 'code', code] as const,
  countiesFiltered: countiesFilteredKey,
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

/** Shared with the `/transparency` server prefetch — see `nationalMoneyFlowKey`. */
export const countyFiscalYearsKey = () => ['counties', 'fiscal-years'] as const;

/**
 * The picker pool behind `/counties/compare`.
 *
 * Exported so `app/counties/compare/page.tsx` (server), `CompareContent` and
 * the Suspense fallback that reserves its space all name the same entry
 * instead of three literals that can drift.
 */
export const compareCountiesKey = () => ['counties', 'all-for-compare'] as const;

// Which fiscal years county budget data exists for, and the one to show
// first. Long stale time: this only changes when a new report is ingested.
export const useCountyFiscalYears = (
  options?: Omit<UseQueryOptions<CountyFiscalYears>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: countyFiscalYearsKey(),
    queryFn: getCountyFiscalYears,
    staleTime: 30 * 60 * 1000,
    ...options,
  });
};

// Get comprehensive county data (one-stop detail)
export const useCountyComprehensive = (
  id: string,
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<CountyComprehensive>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: ['counties', id, 'comprehensive', fiscalYear ?? null] as const,
    queryFn: () => getCountyComprehensive(id, fiscalYear),
    enabled: !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};
