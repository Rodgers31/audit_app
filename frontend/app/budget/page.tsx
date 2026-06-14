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
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import { Metadata } from 'next';
import BudgetSpendingPage from './BudgetPageClient';

export const metadata: Metadata = {
  title: 'Budget & Spending — AuditGava',
  description:
    "How Kenya spends its national budget. Sector allocations, execution rates, revenue sources, and fiscal trends from official government reports.",
};

const SSR_TIMEOUT_MS = 5000;

export default async function BudgetPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['budget', 'overview'],
          queryFn: () => getBudgetOverview(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['budget', 'enhanced'],
          queryFn: () => getBudgetEnhanced(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['fiscal', 'summary'],
          queryFn: () => getFiscalSummary(),
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <BudgetSpendingPage />
    </HydrationBoundary>
  );
}
