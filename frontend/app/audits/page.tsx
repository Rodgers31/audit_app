/**
 * Audit Findings Dashboard — Server Component with SSR data prefetching.
 *
 * Prefetches the federal audit summary on the server so the page renders
 * immediately with data. Mirrors the homepage SSR pattern.
 */
import { Metadata } from 'next';
import { getFederalAudits } from '@/lib/api/audits';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import AuditsPageClient from './AuditsPageClient';

export const metadata: Metadata = {
  title: 'Audit Findings — AuditGava',
  description:
    'Dashboard of Kenyan national-government audit findings from the Office of the Auditor-General: trends, recurring issues, worst counties, and detail.',
};

const SSR_TIMEOUT_MS = 5000;

export default async function AuditsPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['audits', 'federal'],
          queryFn: () => getFederalAudits(),
        }),
      ]),
      new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
    ]);
  } catch {
    // Timeout or SSR error — client React Query will handle it
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AuditsPageClient />
    </HydrationBoundary>
  );
}
