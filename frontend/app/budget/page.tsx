/**
 * Budget & Spending — Server Component with SSR data prefetching.
 *
 * Pre-fetches the 3 budget endpoints in parallel on the server, then
 * passes the dehydrated cache to the client component via HydrationBoundary.
 * Zero loading spinners on first paint. Mirrors the /debt SSR pattern.
 */
import { getBudgetEnhanced, getBudgetOverview } from '@/lib/api/budget';
import { getFiscalSummary } from '@/lib/api/fiscal';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { prefetchWithTimeout } from '@/lib/react-query/prefetchWithTimeout';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import { Metadata } from 'next';
import BudgetSpendingPage from './BudgetPageClient';

export const metadata: Metadata = {
  title: 'Budget & Spending — AuditGava',
  description:
    "How Kenya spends its national budget. Sector allocations, execution rates, revenue sources, and fiscal trends from official government reports.",
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching every other route that
 * server-prefetches (`/`, `/counties`, `/audits`, `/transparency`,
 * `/counties/compare`).
 *
 * Without it this page was static: rendered once at deploy and served until
 * the next one. OBSERVED on production 2026-09-27: `x-vercel-cache: HIT` at
 * `age: 510974` (5.9 days). The figures baked into that HTML were as old as the
 * deploy, and because each hydrated query was older than its hook's
 * `staleTime`, every visit re-requested all three of them after hydration and
 * swapped the numbers in. With a window, the document is at most an hour old,
 * which is also what `SSR_HYDRATED_STALE_TIME_MS` (lib/react-query/isr.ts)
 * assumes when it lets the hooks trust hydrated data for that long.
 */
export const revalidate = 3600;


export default async function BudgetPage() {
  const queryClient = getQueryClient();

  try {
    await prefetchWithTimeout(
      queryClient,
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['budget', 'overview'],
          queryFn: ({ signal }) => getBudgetOverview(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['budget', 'enhanced'],
          queryFn: ({ signal }) => getBudgetEnhanced(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['fiscal', 'summary'],
          queryFn: ({ signal }) => getFiscalSummary(signal),
        }),
      ]),
      SSR_TIMEOUT_MS
    );
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <BudgetSpendingPage />
    </HydrationBoundary>
  );
}
