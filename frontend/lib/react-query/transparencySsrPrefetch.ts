/**
 * The single declaration of what `/transparency` prefetches on the server.
 *
 * `app/transparency/page.tsx` prefetches exactly this list, and
 * `__tests__/transparencySsrHydration.test.tsx` hydrates exactly this list and
 * then asserts the three hooks `TransparencyPageClient` calls are served from
 * it. Both sides read the same declaration, so the page cannot quietly start
 * prefetching something it does not render — the drift that stranded
 * `/counties`' payload (#222) and `/audits`' (#224) in the HTML.
 *
 * Before this, `app/transparency/page.tsx` prefetched nothing at all: it
 * rendered `<TransparencyPageClient />` and no `HydrationBoundary`, so the
 * waterfall hero, the four KPI cards and the 47-row county table all arrived
 * after hydration and replaced skeletons of a different height. That swap is
 * the page's CLS (#221 finding #6).
 *
 * The two money-flow queries are keyed by fiscal year, and the year the client
 * asks for on its first render is `transparencyYearOptions(...).default` —
 * derived from the fiscal-years payload, which is why that one is fetched
 * first and the other two are built from its answer.
 */
import type { QueryKey } from '@tanstack/react-query';
import { getAllCountiesMoneyFlow, getNationalMoneyFlow } from '../api/moneyFlow';
import { allCountiesMoneyFlowKey, nationalMoneyFlowKey } from './useMoneyFlow';

export interface TransparencySsrQuery {
  queryKey: QueryKey;
  queryFn: () => Promise<unknown>;
}

/** Widens one query's payload type so the list can hold both. */
const ssrQuery = <TData,>(
  queryKey: QueryKey,
  queryFn: () => Promise<TData>
): TransparencySsrQuery => ({ queryKey, queryFn });

/**
 * The year-keyed half of the prefetch.
 *
 * Built fresh on each call rather than held as a module constant: the entries
 * close over `queryFn`s, and a server component must not share query state
 * between requests.
 */
export const transparencySsrQueries = (year: string): TransparencySsrQuery[] => [
  ssrQuery(nationalMoneyFlowKey(year), () => getNationalMoneyFlow(year)),
  ssrQuery(allCountiesMoneyFlowKey(year), () => getAllCountiesMoneyFlow(year)),
];
