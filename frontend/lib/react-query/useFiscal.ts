/**
 * Custom React Query hook for fiscal data
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { FiscalSummaryResponse, getFiscalSummary } from '../api/fiscal';

const QUERY_KEYS = {
  fiscalSummary: ['fiscal', 'summary'] as const,
};

/** Get national fiscal summary (budget, revenue, borrowing, debt service, ceiling) */
export const useFiscalSummary = (
  options?: Omit<UseQueryOptions<FiscalSummaryResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.fiscalSummary,
    queryFn: ({ signal }) => getFiscalSummary(signal),
    staleTime: 60 * 60 * 1000, // 1 hour — fiscal data changes infrequently
    ...options,
  });
};
