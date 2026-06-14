/**
 * Side-by-side county comparison — Server Component wrapper.
 *
 * Prefetches the counties list used as the picker source so the first
 * paint renders selectors and placeholders with no network waterfall.
 * The actual picker logic stays a client component (uses useSearchParams,
 * useRouter, local state, Suspense).
 */
import { Metadata } from 'next';
import api from '@/lib/api/axios';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import ComparePageClient from './ComparePageClient';

export const metadata: Metadata = {
  title: 'Compare Counties — AuditGava',
  description:
    'Compare two or three Kenyan counties side-by-side: budget, execution rate, debt, pending bills, and sector mix.',
};

const SSR_TIMEOUT_MS = 5000;

export default async function ComparePage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['counties', 'all-for-compare'],
          queryFn: async () => (await api.get('/counties?limit=50')).data,
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ComparePageClient />
    </HydrationBoundary>
  );
}
