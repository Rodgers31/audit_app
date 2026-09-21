/**
 * Follow the Money — Server Component with SSR data prefetching.
 *
 * Mirrors `/counties` (#222) and `/audits` (#224). Before this the route had
 * no prefetch at all: it returned `<TransparencyPage />` and nothing else, so
 * the served document carried skeletons and not one figure — no "Where the
 * money went", no `KES` anywhere in it. The hero, the KPI cards and the 47-row
 * county table all arrived after hydration and replaced placeholders of a
 * different height, which is the page's Cumulative Layout Shift.
 */
import { Metadata } from 'next';
import { getCountyFiscalYears } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { countyFiscalYearsKey } from '@/lib/react-query/useCounties';
import { transparencySsrQueries } from '@/lib/react-query/transparencySsrPrefetch';
import { transparencyYearOptions } from '@/lib/utils';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import TransparencyPage from './TransparencyPageClient';

export const metadata: Metadata = {
  title: 'Follow the Money — AuditGava',
  description:
    'Trace how public funds flow from treasury allocation to county expenditure, and what the Auditor-General has questioned.',
};

const SSR_TIMEOUT_MS = 5000;

/**
 * ISR: regenerate at most once an hour, matching `/`, `/counties` and
 * `/audits`.
 *
 * Required by the change above, not a drive-by. Until now nothing this page
 * prefetched ever painted, so the prerendered document held no money-flow
 * figures and could age from one deploy to the next without misleading
 * anyone. The waterfall and the KPI cards are now what the reader sees first,
 * so they have to be kept current. React Query still background-refreshes
 * past each hook's 10-minute staleTime, so the hour bounds how stale the
 * FIRST PAINT can be, not what the reader ends up with.
 */
export const revalidate = 3600;

export default async function FollowTheMoneyPage() {
  const queryClient = getQueryClient();

  // The money-flow queries are keyed by fiscal year and the client's first
  // render asks for `transparencyYearOptions(meta).default`, so the list of
  // years has to be resolved before the other two can be prefetched under a
  // key the client will look for. Sequential on purpose.
  let defaultYear: string | undefined;
  try {
    const meta = await Promise.race([
      queryClient.fetchQuery({
        queryKey: countyFiscalYearsKey(),
        queryFn: getCountyFiscalYears,
      }),
      new Promise<undefined>((resolve) => setTimeout(() => resolve(undefined), SSR_TIMEOUT_MS)),
    ]);
    defaultYear = transparencyYearOptions(meta).default;
  } catch {
    // Backend unreachable at build/revalidate time — the client hooks still
    // run and the page renders exactly as it did before this change.
  }

  if (defaultYear) {
    try {
      const year = defaultYear;
      await Promise.race([
        Promise.allSettled(
          transparencySsrQueries(year).map((q) => queryClient.prefetchQuery(q))
        ),
        new Promise((resolve) => setTimeout(resolve, SSR_TIMEOUT_MS)),
      ]);
    } catch {
      // Same — a failed prefetch degrades to the previous client-fetch path.
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <TransparencyPage />
    </HydrationBoundary>
  );
}
