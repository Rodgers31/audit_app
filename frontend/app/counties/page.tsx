/**
 * County Explorer — Server Component with SSR data prefetching.
 *
 * Pre-fetches the counties list on the server so the page renders
 * immediately with data — no loading spinner on first paint.
 *
 * Mirrors the homepage SSR pattern. On subsequent client-side navigations
 * React Query serves from its in-memory cache (staleTime 30min).
 */
import { Metadata } from 'next';
import { getCounties } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import CountyExplorerPage from './CountiesPageClient';

export const metadata: Metadata = {
  title: 'County Explorer — AuditGava',
  description:
    'Compare all 47 Kenyan counties by budget, spending efficiency, audit findings, and financial health. Data from Controller of Budget and OAG.',
};

const SSR_TIMEOUT_MS = 5000;

export default async function CountiesPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['counties', 'filtered', undefined],
          queryFn: () => getCounties(),
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CountyExplorerPage />
    </HydrationBoundary>
  );
}
