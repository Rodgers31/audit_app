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
import { compareCountiesKey } from '@/lib/react-query/useCounties';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import ComparePageClient from './ComparePageClient';

export const metadata: Metadata = {
  title: 'Compare Counties — AuditGava',
  description:
    'Compare two or three Kenyan counties side-by-side: budget, execution rate, debt, pending bills, and sector mix.',
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching `/`, `/counties`, `/audits`
 * and `/transparency`.
 *
 * Required by the change to `ComparePageClient`, not a drive-by. The
 * prefetched list used to sit unread in the HTML — the whole page was
 * client-rendered behind a Suspense fallback — so the prerendered document
 * made no claim and could age until the next deploy. The boundary's fallback
 * now renders the provenance note off that same payload, so a reader sees it,
 * and it has to be kept current. React Query still background-refreshes past
 * the hook's 15-minute staleTime.
 */
export const revalidate = 3600;

export default async function ComparePage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          // Shared factory, not a literal: the client hook and the Suspense
          // fallback that reserves its space both read this exact key.
          queryKey: compareCountiesKey(),
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
