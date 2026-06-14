/**
 * National Sector Spending — Server Component with SSR data prefetching.
 *
 * Prefetches the `/sectors/spending` rollup on the server so the client
 * component hydrates with data already in its React Query cache. No loading
 * spinner on first paint; subsequent navigations serve from cache.
 *
 * Mirrors the homepage SSR pattern — see `app/page.tsx`.
 */
import { Metadata } from 'next';
import api from '@/lib/api/axios';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import SectorsPageClient from './SectorsPageClient';

export const metadata: Metadata = {
  title: 'Sector Spending — AuditGava',
  description:
    "How Kenya's devolved budgets flow across Health, Education, Roads, Water and other sectors — with executed-vs-allocated rates per sector.",
};

const SSR_TIMEOUT_MS = 5000;

export default async function SectorsPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['sectors', 'spending'],
          queryFn: async () => (await api.get('/sectors/spending')).data,
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <SectorsPageClient />
    </HydrationBoundary>
  );
}
