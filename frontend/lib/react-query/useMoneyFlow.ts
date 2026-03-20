/**
 * React Query hooks for money flow data
 */
import { MoneyFlowData } from '@/types';
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { getCountyMoneyFlow, getNationalMoneyFlow } from '../api/moneyFlow';

const QUERY_KEYS = {
  countyMoneyFlow: (id: string, year: string) => ['counties', id, 'money-flow', year] as const,
  nationalMoneyFlow: (year: string) => ['money-flow', 'national', year] as const,
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
