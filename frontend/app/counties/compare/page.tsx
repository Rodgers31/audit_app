/**
 * Side-by-side county comparison — Server Component wrapper.
 *
 * Prefetches the counties list used as the picker source so the first
 * paint renders selectors and placeholders with no network waterfall.
 * The actual picker logic stays a client component (uses useSearchParams,
 * useRouter, local state, Suspense).
 */
import { Metadata } from 'next';
import { getCountyList } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { prefetchWithTimeout } from '@/lib/react-query/prefetchWithTimeout';
import { compareCountiesKey } from '@/lib/react-query/useCounties';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import ComparePageClient from './ComparePageClient';

export const metadata: Metadata = {
  title: 'Compare Counties — AuditGava',
  description:
    'Compare Kenyan counties side by side by budget, spending, borrowing, pending bills and published audit findings.',
};

const SSR_TIMEOUT_MS = 5000;

/**
 * Regenerate the prefetched county list at most once an hour. The
 * comparison hook uses the same stale time for the hydrated inventory.
 */
export const revalidate = 3600;

export default async function ComparePage() {
  const queryClient = getQueryClient();

  try {
    await prefetchWithTimeout(
      queryClient,
      Promise.allSettled([
        queryClient.prefetchQuery({
          // Shared factory, not a literal: the client hook and the Suspense
          // fallback that reserves its space both read this exact key.
          queryKey: compareCountiesKey(),
          queryFn: ({ signal }) => getCountyList({ limit: 50 }, signal),
        }),
      ]),
      SSR_TIMEOUT_MS
    );
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ComparePageClient />
    </HydrationBoundary>
  );
}
