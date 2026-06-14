/**
 * County Detail — Server Component with SSR data prefetching.
 *
 * Pre-fetches the comprehensive + accountability datasets for this
 * county on the server so the client component hydrates with a fully
 * populated React Query cache — no loading spinner on first paint,
 * no waterfall.
 *
 * Matches the homepage pattern (`app/page.tsx`): Promise.allSettled
 * wrapped in a 5s Promise.race guard so cold-start backends don't
 * block the page render.
 *
 * Query keys MUST match what `useCountyComprehensive` /
 * `useCountyAccountability` use client-side:
 *   • ['counties', id, 'comprehensive', fiscalYear ?? null]
 *   • ['counties', id, 'accountability']
 * Otherwise React Query treats them as cache misses and refetches.
 */
import { Metadata } from 'next';
import { getCountyComprehensive } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { getLatestReportedFiscalYear } from '@/lib/utils';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import CountyDetailClient from './CountyDetailClient';

// Shorter SSR budget — on a cold backend each heavy endpoint is ~3-4 s,
// so a 5 s timeout made the whole page wait half a round-trip. 1.5 s
// lets us bail early, render the shell, and let React Query fill in
// the rest client-side (which is <5 ms once the cache is warm).
const SSR_TIMEOUT_MS = 1500;

/**
 * Generic metadata — we avoid a blocking backend fetch here because
 * `generateMetadata` runs before the page body, and any stall doubles
 * the perceived nav time. The dynamic `${name} County` title was nice
 * but the client-side `<title>` is updated once the page hydrates.
 */
export const metadata: Metadata = {
  title: 'County Detail — AuditGava',
  description:
    'Budget execution, debt, audit findings, and stalled projects for this county.',
};

export default async function CountyDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ fy?: string }>;
}) {
  const { id } = await params;
  const resolvedSearchParams = await searchParams;
  const fiscalYear = resolvedSearchParams.fy || getLatestReportedFiscalYear();
  const queryClient = getQueryClient();

  // Only prefetch the comprehensive payload on SSR — that's what the
  // page-visible hero needs. Accountability is also heavy but drives
  // only the small AUDIT badge, which appears cleanly after hydrate.
  // If we had it here too, a cold backend would double the SSR wait.
  try {
    await Promise.race([
      queryClient.prefetchQuery({
        // Matches useCountyComprehensive's queryKey shape.
        queryKey: ['counties', id, 'comprehensive', fiscalYear ?? null] as const,
        queryFn: () => getCountyComprehensive(id, fiscalYear),
      }),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CountyDetailClient />
    </HydrationBoundary>
  );
}
