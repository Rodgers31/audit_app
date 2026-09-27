/**
 * Homepage — Server Component with SSR data prefetching.
 *
 * Pre-fetches all 7 API calls in parallel on the server, then passes
 * the dehydrated cache to the client component via HydrationBoundary.
 * Result: zero loading spinners on first paint, no waterfall.
 *
 * Every hook reading this state keeps it fresh for at least the ISR window
 * (`SSR_HYDRATED_STALE_TIME_MS`, lib/react-query/isr.ts), so a cached copy of
 * this page does not re-download after hydration what it just rendered.
 *
 * COLD-START NOTE: If the Render backend is sleeping, SSR prefetches
 * will fail within the SSR_TIMEOUT. The page still renders (loading
 * skeletons), and client-side React Query retries will fill in data
 * once the backend wakes up (~2-5s later).
 */
import { Metadata } from 'next';

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
import { federalAuditsHomeSummaryQuery } from '@/lib/react-query/useAudits';
import { countiesFilteredKey } from '@/lib/react-query/useCounties';
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

/**
 * ISR: regenerate the page in the background at most once an hour.
 * Without this the page is prerendered ONCE at deploy time and the
 * baked data ages until the next deploy — while the hero claims
 * "updated nightly". Hourly revalidation keeps the static-CDN speed
 * (visitors always get the cached copy; regeneration is background)
 * and caps homepage data staleness at ~1h behind the backend.
 */
export const revalidate = 3600;

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
        // The trimmed summary `AuditReportsSection` renders, not the full
        // ~886KB response: the section lists 4 of its 813 findings, and the
        // rest were dehydrated into this document for nothing.
        queryClient.prefetchQuery(federalAuditsHomeSummaryQuery()),
        queryClient.prefetchQuery({
          queryKey: ['budget', 'national', undefined],
          queryFn: () => getNationalBudgetSummary(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-loans'],
          queryFn: () => getNationalLoans(),
        }),
        queryClient.prefetchQuery({
          queryKey: countiesFilteredKey(),
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
