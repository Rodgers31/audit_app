/**
 * National Debt — Server Component with SSR data prefetching.
 *
 * Pre-fetches all 7 debt-related API calls in parallel on the server,
 * then passes the dehydrated cache to the client component via
 * HydrationBoundary. Result: zero loading spinners on first paint.
 *
 * Mirrors the homepage SSR pattern, including its hourly ISR window below.
 */
import {
  getDebtSustainability,
  getDebtTimeline,
  getNationalDebtOverview,
  getNationalLoans,
  getPendingBills,
  getPendingBillsSummary,
} from '@/lib/api/debt';
import { getFiscalSummary } from '@/lib/api/fiscal';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import { Metadata } from 'next';
import NationalDebtPage from './DebtPageClient';

export const metadata: Metadata = {
  title: 'National Debt — AuditGava',
  description:
    "Track Kenya's public debt, external vs domestic debt, debt-to-GDP ratio, loan details, and sustainability indicators.",
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching every other route that
 * server-prefetches (`/`, `/counties`, `/audits`, `/transparency`,
 * `/counties/compare`).
 *
 * Without it this page was static: rendered once at deploy and served until
 * the next one. OBSERVED on production 2026-09-27: `x-vercel-cache: HIT` at
 * `age: 400532` (4.6 days). The figures baked into that HTML were as old as the
 * deploy, and because each hydrated query was older than its hook's
 * `staleTime`, every visit re-requested all six of them after hydration and
 * swapped the numbers in. With a window, the document is at most an hour old,
 * which is also what `SSR_HYDRATED_STALE_TIME_MS` (lib/react-query/isr.ts)
 * assumes when it lets the hooks trust hydrated data for that long.
 */
export const revalidate = 3600;


export default async function DebtPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national'],
          queryFn: () => getNationalDebtOverview(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-loans'],
          queryFn: () => getNationalLoans(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-timeline'],
          queryFn: () => getDebtTimeline(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['fiscal', 'summary'],
          queryFn: () => getFiscalSummary(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'pending-bills'],
          queryFn: () => getPendingBills(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'pending-bills-summary'],
          queryFn: () => getPendingBillsSummary(),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'debt-sustainability'],
          queryFn: () => getDebtSustainability(),
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <NationalDebtPage />
    </HydrationBoundary>
  );
}
