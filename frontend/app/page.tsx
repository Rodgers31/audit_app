/**
 * Homepage — Server Component with SSR data prefetching.
 *
 * Pre-fetches all 7 API calls in parallel on the server, then passes
 * the dehydrated cache to the client component via HydrationBoundary.
 * Result: zero loading spinners on first paint, no waterfall.
 *
 * On subsequent client-side navigations React Query serves from its
 * in-memory cache (staleTime 10min–1hr) so no extra fetches occur.
 *
 * COLD-START NOTE: If the Render backend is sleeping, SSR prefetches
 * will fail within the SSR_TIMEOUT. The page still renders (loading
 * skeletons), and client-side React Query retries will fill in data
 * once the backend wakes up (~2-5s later).
 */
import { Metadata } from 'next';
import { getFederalAudits } from '@/lib/api/audits';

export const metadata: Metadata = {
  title: 'AuditGava — Kenya Public Money Tracker',
  description:
    "Track how Kenya's government spends public money. Real-time data on county budgets, national debt, audit findings, and financial accountability.",
};
import { getNationalBudgetSummary } from '@/lib/api/budget';
import { getCounties } from '@/lib/api/counties';
import { getDebtTimeline, getNationalDebtOverview, getNationalLoans } from '@/lib/api/debt';
import { getFiscalSummary } from '@/lib/api/fiscal';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import HomeDashboardClient from './HomeDashboardClient';

/**
 * If the backend doesn't respond within this window, skip SSR data and
 * let the client hydrate with loading states instead of blocking the
 * entire page render. 5s is generous for a warm backend; cold starts
 * take 10-20s so we intentionally bail early and let React Query
 * retry on the client.
 */
const SSR_TIMEOUT_MS = 5000;

export default async function HomePage() {
  const queryClient = getQueryClient();

  // Prefetch all homepage data in parallel (server → backend is fast, same machine)
  // Uses Promise.allSettled so a single failing endpoint doesn't block others.
  // If the backend is cold-sleeping, these will fail — React Query on the client
  // will retry with loading skeletons.
  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-timeline'],
          queryFn: () => getDebtTimeline(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national'],
          queryFn: () => getNationalDebtOverview(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['fiscal', 'summary'],
          queryFn: () => getFiscalSummary(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['audits', 'federal'],
          queryFn: () => getFederalAudits(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['budget', 'national', undefined],
          queryFn: () => getNationalBudgetSummary(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-loans'],
          queryFn: () => getNationalLoans(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['counties', 'filtered', undefined],
          queryFn: () => getCounties(),
        }),
      ]),
      // Bail after SSR_TIMEOUT_MS so cold starts don't block page render
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or other SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <HomeDashboardClient />
    </HydrationBoundary>
  );
}
