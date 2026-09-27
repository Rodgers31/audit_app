/**
 * National Debt — Server Component with SSR data prefetching.
 *
 * Pre-fetches the 6 queries `DebtPageClient` reads, in parallel on the
 * server, then passes the dehydrated cache to the client component via
 * HydrationBoundary. Result: zero loading spinners on first paint.
 *
 * Only what the client reads: every key here is serialised into the HTML.
 * `['debt','debt-sustainability']` used to be prefetched too, after its only
 * reader went in #148, so it rode in every /debt document unread.
 * `__tests__/debtSsrPrefetch.test.tsx` fails if a prefetched key has no
 * mounted reader.
 *
 * Mirrors the homepage SSR pattern. On subsequent client-side navigations
 * React Query serves from its in-memory cache (staleTime 10min–1hr).
 */
import {
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
