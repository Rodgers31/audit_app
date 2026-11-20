/**
 * County Detail — Server Component with SSR data prefetching.
 *
 * Pre-fetches the comprehensive + accountability datasets for this
 * county on the server so the client component hydrates with a fully
 * populated React Query cache — no loading spinner on first paint,
 * no waterfall.
 *
 * Matches the homepage pattern (`app/page.tsx`): Promise.allSettled
 * with a 5s prefetch guard so cold-start backends don't
 * block the page render.
 *
 * Query keys MUST match what `useCountyComprehensive` /
 * `useCountyAccountability` use client-side:
 *   • ['counties', id, 'comprehensive', fiscalYear ?? null]
 *   • ['counties', id, 'accountability']
 * Otherwise React Query treats them as cache misses and refetches.
 */
import type { Metadata, ResolvingMetadata } from 'next';
import { getCountyComprehensive } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { prefetchWithTimeout } from '@/lib/react-query/prefetchWithTimeout';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import CountyDetailClient from './CountyDetailClient';
import { resolveCountyMetadataRoute } from './countyMetadata';

// Shorter SSR budget — on a cold backend each heavy endpoint is ~3-4 s,
// so a 5 s timeout made the whole page wait half a round-trip. 1.5 s
// lets us bail early, render the shell, and let React Query fill in
// the rest client-side (which is <5 ms once the cache is warm).
const SSR_TIMEOUT_MS = 1500;

export async function generateMetadata(
  { params }: { params: Promise<{ id: string }> },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const [{ id }, { openGraph, twitter }] = await Promise.all([params, parent]);
  const county = resolveCountyMetadataRoute(id);
  const title = county
    ? `${county.name} County: budget, debt and audits — AuditGava`
    : 'County detail — AuditGava';
  const description = county
    ? `Explore ${county.name} County’s budget execution, debt, audit findings and accountability.`
    : 'Explore budget execution, debt, audit findings and accountability for Kenya’s counties.';
  const site = process.env.NEXT_PUBLIC_BASE_URL || 'https://www.auditgava.com';
  const canonical = county ? new URL(`/counties/${county.slug}`, site).href : undefined;

  return {
    title: { absolute: title },
    description,
    ...(canonical && { alternates: { canonical } }),
    openGraph: {
      type: 'website',
      title,
      description,
      url: canonical,
      siteName: openGraph?.siteName,
      locale: openGraph?.locale,
      images: openGraph?.images,
    },
    twitter: { card: 'summary_large_image', title, description, images: twitter?.images },
  };
}

export default async function CountyDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ fy?: string }>;
}) {
  const { id } = await params;
  const resolvedSearchParams = await searchParams;
  // Must match CountyDetailClient exactly, or the SSR prefetch populates a
  // different query key than the client reads and the page refetches with
  // different numbers. See the note there.
  const fiscalYear = resolvedSearchParams.fy || undefined;
  const queryClient = getQueryClient();

  // Only prefetch the comprehensive payload on SSR — that's what the
  // page-visible hero needs. Accountability is also heavy but drives
  // only the small AUDIT badge, which appears cleanly after hydrate.
  // If we had it here too, a cold backend would double the SSR wait.
  try {
    await prefetchWithTimeout(
      queryClient,
      queryClient.prefetchQuery({
        // Matches useCountyComprehensive's queryKey shape.
        queryKey: ['counties', id, 'comprehensive', fiscalYear ?? null] as const,
        queryFn: ({ signal }) => getCountyComprehensive(id, fiscalYear, signal),
      }),
      SSR_TIMEOUT_MS
    );
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CountyDetailClient />
    </HydrationBoundary>
  );
}
