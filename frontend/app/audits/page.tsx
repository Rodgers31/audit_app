/**
 * Audit Findings Dashboard — Server Component with SSR data prefetching.
 *
 * Prefetches the four national-dashboard queries `AuditsPageClient` actually
 * reads, so the page renders its content on the server instead of a spinner.
 *
 * It used to prefetch `['audits','federal']` instead — 886KB of national
 * audit findings whose only consumer is `AuditReportsSection`, a component
 * rendered on `/` and nowhere in this route's tree. The route paid for a
 * payload nothing here reads and server-rendered none of the four it does.
 * See #221 finding #2.
 */
import { Metadata } from 'next';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { auditsSsrQueries } from '@/lib/react-query/auditsSsrPrefetch';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import AuditsPageClient from './AuditsPageClient';

export const metadata: Metadata = {
  title: 'Audit Findings — AuditGava',
  description:
    'Dashboard of Kenyan national-government audit findings from the Office of the Auditor-General: trends, recurring issues, worst counties, and detail.',
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching `/` and `/counties`.
 *
 * Required by the change above, not a drive-by. Until now nothing this page
 * prefetched ever painted, so the prerendered document held no audit figures
 * and could age from one deploy to the next without misleading anyone. Now
 * the summary tiles, the trend chart and the first page of findings are baked
 * into the HTML and are what the reader sees first — so they have to be kept
 * current. React Query still background-refreshes on the client once the
 * hydrated entries pass their staleTime (15min for summary/trends/recurring,
 * 5min for findings), so the hour bounds how stale the *first paint* can be,
 * not what the reader ends up with.
 */
export const revalidate = 3600;

export default async function AuditsPage() {
  const queryClient = getQueryClient();

  try {
    await Promise.race([
      // The query list lives in `auditsSsrPrefetch` rather than inline here,
      // and its keys come from the shared factories in `useAudits`. A key
      // written out by hand in a server component is exactly how the
      // /counties prefetch and its hook drifted apart (#222) — and the test
      // hydrates this same list, so it cannot drift from the page either.
      Promise.allSettled(auditsSsrQueries().map((q) => queryClient.prefetchQuery(q))),
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
