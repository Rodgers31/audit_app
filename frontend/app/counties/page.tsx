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
import { countiesFilteredKey } from '@/lib/react-query/useCounties';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import CountyExplorerPage from './CountiesPageClient';

export const metadata: Metadata = {
  title: 'County Explorer — AuditGava',
  description:
    'Compare all 47 Kenyan counties by budget, spending efficiency, audit findings, and financial health. County budget/debt figures are modelled estimates (CRA equitable-share formula); audit findings are from the Office of the Auditor-General.',
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching the homepage.
 *
 * This page's prefetched list is now what actually paints (it previously sat
 * unread in the HTML while the client re-fetched — see `countiesFilteredKey`),
 * so the baked copy is user-visible and has to be kept current. Without a
 * revalidate window it would be prerendered once at deploy time and age until
 * the next deploy. React Query still background-refreshes on the client once
 * the hydrated entry passes its 30min staleTime, so an hour is an upper bound
 * on what the first paint can be behind, not on what the reader ends up with.
 */
export const revalidate = 3600;

export default async function CountiesPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          // Shared factory, not a literal: the client hook reads this exact
          // key, and a hand-written copy is how the two drifted apart before.
          queryKey: countiesFilteredKey(),
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
