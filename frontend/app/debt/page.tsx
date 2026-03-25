/**
 * National Debt — Server Component with SSR data prefetching.
 *
 * Pre-fetches all 7 debt-related API calls in parallel on the server,
 * then passes the dehydrated cache to the client component via
 * HydrationBoundary. Result: zero loading spinners on first paint.
 *
 * Mirrors the homepage SSR pattern. On subsequent client-side navigations
 * React Query serves from its in-memory cache (staleTime 10min–1hr).
 */
import { Metadata } from 'next';
import {
  getDebtTimeline,
  getDebtSustainability,
  getNationalDebtOverview,
  getNationalLoans,
  getPendingBills,
  getPendingBillsSummary,
} from '@/lib/api/debt';
import { getFiscalSummary } from '@/lib/api/fiscal';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import NationalDebtPage from './DebtPageClient';

export const metadata: Metadata = {
  title: 'National Debt — AuditGava',
  description:
    "Kenya's public debt stands at KES 12.5 trillion. Track external vs domestic debt, debt-to-GDP ratio, loan details, and sustainability indicators.",
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
