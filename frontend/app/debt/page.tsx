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
 * Mirrors the homepage SSR pattern, including its hourly ISR window below.
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
import { prefetchWithTimeout } from '@/lib/react-query/prefetchWithTimeout';
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
    await prefetchWithTimeout(
      queryClient,
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national'],
          queryFn: ({ signal }) => getNationalDebtOverview(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-loans'],
          queryFn: ({ signal }) => getNationalLoans(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'national-timeline'],
          queryFn: ({ signal }) => getDebtTimeline(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['fiscal', 'summary'],
          queryFn: ({ signal }) => getFiscalSummary(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'pending-bills'],
          queryFn: ({ signal }) => getPendingBills(signal),
        }),
        queryClient.prefetchQuery({
          queryKey: ['debt', 'pending-bills-summary'],
          queryFn: ({ signal }) => getPendingBillsSummary(signal),
        }),
      ]),
      SSR_TIMEOUT_MS
    );
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <NationalDebtPage />
    </HydrationBoundary>
  );
}
