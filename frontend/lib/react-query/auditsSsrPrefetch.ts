/**
 * The single declaration of what `/audits` prefetches on the server.
 *
 * `app/audits/page.tsx` prefetches exactly this list, and
 * `__tests__/auditsSsrHydration.test.tsx` hydrates exactly this list and then
 * asserts the four hooks `AuditsPageClient` calls are served from it. Because
 * both sides read the same array, the page cannot quietly start prefetching
 * something the page does not render — which is the defect this replaces.
 *
 * Before this, `app/audits/page.tsx` prefetched one query, `['audits',
 * 'federal']`: 886KB of national audit findings whose only consumer is
 * `components/dashboard/AuditReportsSection`, which `/audits` does not render
 * anywhere in its tree. Meanwhile all four queries the page does read were
 * fetched client-side after hydration. #221 finding #2.
 */
import type { QueryKey } from '@tanstack/react-query';
import {
  getAuditDashboardSummary,
  getAuditFindings,
  getAuditTrends,
  getRecurringFindings,
} from '../api/audits';
import {
  AUDIT_FINDINGS_INITIAL_FILTERS,
  auditDashboardSummaryKey,
  auditFindingsKey,
  auditRecurringFindingsKey,
  auditTrendsKey,
} from './useAudits';

export interface AuditsSsrQuery {
  queryKey: QueryKey;
  queryFn: () => Promise<unknown>;
}

/** Widens one query's payload type so the four can share a list. */
const ssrQuery = <TData,>(queryKey: QueryKey, queryFn: () => Promise<TData>): AuditsSsrQuery => ({
  queryKey,
  queryFn,
});

/**
 * Built fresh on each call rather than held as a module constant: the entries
 * close over `queryFn`s, and a server component should not share query state
 * between requests.
 */
export const auditsSsrQueries = (): AuditsSsrQuery[] => [
  ssrQuery(auditDashboardSummaryKey(), getAuditDashboardSummary),
  // `useAuditTrends()` is called with no params by the page.
  ssrQuery(auditTrendsKey(), () => getAuditTrends()),
  ssrQuery(auditRecurringFindingsKey(), getRecurringFindings),
  // The client seeds `useState` from this same constant, so its first render
  // asks for exactly the page of findings prefetched here.
  ssrQuery(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS), () =>
    getAuditFindings(AUDIT_FINDINGS_INITIAL_FILTERS)
  ),
];
