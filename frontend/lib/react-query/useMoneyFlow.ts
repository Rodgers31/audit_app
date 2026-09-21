/**
 * React Query hooks for money flow data
 */
import { MoneyFlowData } from '@/types';
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { getAllCountiesMoneyFlow, getCountyMoneyFlow, getNationalMoneyFlow } from '../api/moneyFlow';

/**
 * Cache keys, exported so a server component can prefetch under exactly the
 * key the hook below reads.
 *
 * `/counties` (#222) and `/audits` (#224) both shipped a spinner wrapped
 * around data nothing could find, because a server component hand-wrote a key
 * literal that drifted from the hook's. `lib/react-query/transparencySsrPrefetch.ts`
 * builds `/transparency`'s prefetch list from these same factories.
 */
export const nationalMoneyFlowKey = (year: string) =>
  ['money-flow', 'national', year] as const;

export const allCountiesMoneyFlowKey = (year: string) =>
  ['money-flow', 'all-counties', year] as const;

export const countyMoneyFlowKey = (id: string, year: string) =>
  ['counties', id, 'money-flow', year] as const;

const QUERY_KEYS = {
  countyMoneyFlow: countyMoneyFlowKey,
  nationalMoneyFlow: nationalMoneyFlowKey,
};

export const useCountyMoneyFlow = (
  countyId: string,
  year: string,
  options?: Omit<UseQueryOptions<MoneyFlowData>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyMoneyFlow(countyId, year),
    queryFn: () => getCountyMoneyFlow(countyId, year),
    enabled: !!countyId && !!year,
    staleTime: 10 * 60 * 1000,
    ...options,
  });
};

export const useAllCountiesMoneyFlow = (year: string) => {
  return useQuery({
    queryKey: allCountiesMoneyFlowKey(year),
    queryFn: () => getAllCountiesMoneyFlow(year),
    enabled: !!year,
    staleTime: 10 * 60 * 1000,
  });
};

export const useNationalMoneyFlow = (
  year: string,
  options?: Omit<UseQueryOptions<MoneyFlowData>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.nationalMoneyFlow(year),
    queryFn: () => getNationalMoneyFlow(year),
    enabled: !!year,
    staleTime: 10 * 60 * 1000,
    ...options,
  });
};
