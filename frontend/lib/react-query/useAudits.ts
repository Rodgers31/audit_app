/**
 * Custom React Query hooks for audit data
 */
import { useInfiniteQuery, useQuery, UseQueryOptions } from '@tanstack/react-query';
import type {
  AuditDashboardSummary,
  AuditTrendsData,
  FederalAuditFinding,
  FederalAuditResponse,
  FindingsFilters,
  FindingsListData,
  RecurringFindingsData,
} from '../api/audits';
import {
  getAuditDashboardSummary,
  getAuditFindings,
  getAuditReport,
  getAuditReports,
  getAuditReportsPaginated,
  getAuditStatistics,
  getAuditTrends,
  getAvailableFiscalYears,
  getCountyAuditList,
  getCountyAuditReports,
  getCountyAuditsEnriched,
  getFederalAudits,
  getLatestCountyAudit,
  getRecurringFindings,
} from '../api/audits';
import { AuditFilters, AuditReportResponse } from '../api/types';

/**
 * How many findings the homepage's `AuditReportsSection` lists: the largest
 * ones that state an amount.
 */
export const HOME_TOP_FINDINGS = 4;

/**
 * The findings `AuditReportsSection` lists — the largest STATED figures.
 * Findings that state none (a null amount, or the API's "KES 0") are excluded
 * rather than sorted as 0: with the honest null they would compare as NaN and
 * scramble the order. The sort is stable, so ties keep the API's order.
 *
 * Shared by the component and by `trimFederalAuditsForHome`, so the rows the
 * homepage ships and the rows it renders are one computation, not two.
 */
export function topStatedFindings(
  findings: FederalAuditFinding[],
  n: number = HOME_TOP_FINDINGS
): FederalAuditFinding[] {
  return (
    [...findings]
      .filter((f) => f.amount_involved !== 'KES 0' && f.amount_numeric != null)
      // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- sort comparator
      .sort((a, b) => (b.amount_numeric ?? 0) - (a.amount_numeric ?? 0))
      .slice(0, n)
  );
}

/**
 * The national audit response cut down to what the homepage renders.
 *
 * `/api/v1/audits/federal` is ~886KB, almost all of it `findings` (813 rows
 * averaging ~1.1KB). `AuditReportsSection` reads from that list only the
 * `topStatedFindings` and whether the list is empty; every figure it prints
 * comes from the summary fields, which pass through untouched. Prefetched
 * whole, the list was dehydrated into the homepage document and made it a
 * 1.31MB file (#221 finding #4).
 *
 * Emptiness is preserved on purpose: when findings exist but none states an
 * amount, one is kept, so the section still shows its "no stated figures"
 * list rather than the "nothing can be published yet" empty state, which
 * would be a different — and false — statement.
 */
export function trimFederalAuditsForHome(data: FederalAuditResponse): FederalAuditResponse {
  const top = topStatedFindings(data.findings ?? []);
  const findings = top.length > 0 || !data.findings?.length ? top : data.findings.slice(0, 1);
  return { ...data, findings };
}

/**
 * Cache key for the homepage's TRIMMED national audit summary.
 *
 * Deliberately not the full response's key: a trimmed list cached under a
 * name that promises every finding would hand any future reader 4 rows while
 * `total_findings` says 813. One key, one shape.
 *
 * Exported as a factory because `app/page.tsx` prefetches this query on the
 * server and `useFederalAuditsHomeSummary` reads it on the client — two copies
 * of one contract if the key is written out twice, which is how `/counties`
 * (#222) and `/audits` (#224) drifted.
 */
export const federalAuditsHomeSummaryKey = () => ['audits', 'federal', 'home-summary'] as const;

/**
 * One declaration of the query, for the server prefetch and the hook alike.
 *
 * The backend applies the same selection (`?top_findings`), so a refetch of a
 * stale hydrated copy downloads a few KB rather than the ~886KB list. The
 * result is trimmed again here, which is a no-op on the backend's answer and
 * keeps the document small if the backend predates the parameter (FastAPI
 * ignores query parameters it does not declare).
 */
export const federalAuditsHomeSummaryQuery = () => ({
  queryKey: federalAuditsHomeSummaryKey(),
  queryFn: async () =>
    trimFederalAuditsForHome(await getFederalAudits({ topFindings: HOME_TOP_FINDINGS })),
});

// Query keys for audits
const QUERY_KEYS = {
  audits: ['audits'] as const,
  audit: (id: string) => ['audits', id] as const,
  auditsFiltered: (filters?: AuditFilters) => ['audits', 'filtered', filters] as const,
  countyAudits: (countyId: string, fiscalYear?: string) =>
    ['audits', 'county', countyId, fiscalYear] as const,
  latestCountyAudit: (countyId: string) => ['audits', 'county', countyId, 'latest'] as const,
  countyAuditsEnriched: (countyId: string) => ['audits', 'county', countyId, 'enriched'] as const,
  countyAuditsList: (
    countyId: string,
    params?: { page?: number; limit?: number; year?: string; status?: string; severity?: string }
  ) => ['audits', 'county', countyId, 'list', params] as const,
  statistics: ['audits', 'statistics'] as const,
  fiscalYears: ['audits', 'fiscal-years'] as const,
};

/* ═══════════════════════════════════════════════════════════════════════
   National Audit Dashboard cache keys — shared by the /audits server
   prefetch and the client hooks that read it.

   These are exported factories rather than literals for the reason #222
   found the hard way on /counties: a hand-written key in a server component
   and the hook's own key are two copies of one contract, and when they drift
   the prefetched payload is stranded in the HTML under a key nobody reads.
   The page then renders its `isLoading` spinner and re-fetches over the
   network what the document already contains.

   `app/audits/page.tsx` builds every one of its prefetch keys through these.
   ═══════════════════════════════════════════════════════════════════════ */

/** Root prefix for every national-dashboard query. */
export const AUDIT_DASHBOARD_KEY_ROOT = ['audit', 'dashboard'] as const;

/**
 * Drop keys whose value is `undefined`, and collapse an object with nothing
 * left onto `undefined`.
 *
 * React Query hashes keys with `JSON.stringify`, which renders `undefined` as
 * `null` but an all-undefined object as `{}` — so two spellings of the same
 * request land on two cache entries. Only `undefined` is dropped: every param
 * `getAuditTrends` and `getAuditFindings` send is guarded by a truthiness
 * check on a defined value (`lib/api/audits.ts:338-365`), so this cannot
 * change which request a key stands for.
 */
function normalizeParams<T extends object>(params?: T): T | undefined {
  if (!params) return undefined;
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  return entries.length ? (Object.fromEntries(entries) as T) : undefined;
}

export const auditDashboardSummaryKey = () => ['audit', 'dashboard', 'summary'] as const;

export const auditRecurringFindingsKey = () => ['audit', 'dashboard', 'recurring'] as const;

export const auditTrendsKey = (params?: { county_id?: number; query_type?: string }) =>
  ['audit', 'dashboard', 'trends', normalizeParams(params)] as const;

export const auditFindingsKey = (filters?: FindingsFilters) =>
  ['audit', 'dashboard', 'findings', normalizeParams(filters)] as const;

/**
 * The findings filter state `AuditsPageClient` renders with before the reader
 * touches anything — and therefore the only filter shape the server can
 * usefully prefetch.
 *
 * Shared so the two sides cannot drift: the client seeds `useState` from it
 * and resets to it, and `app/audits/page.tsx` prefetches
 * `auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS)`. Frozen because the
 * same object reference is handed to every mount.
 */
export const AUDIT_FINDINGS_INITIAL_FILTERS: FindingsFilters = Object.freeze({
  page: 1,
  limit: 20,
});

// Get all audit reports
export const useAuditReports = (
  filters?: AuditFilters,
  options?: Omit<UseQueryOptions<AuditReportResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.auditsFiltered(filters),
    queryFn: () => getAuditReports(filters),
    staleTime: 30 * 60 * 1000, // 30 minutes — audit reports rarely change
    ...options,
  });
};

// Get single audit report by ID
export const useAuditReport = (
  id: string,
  options?: Omit<UseQueryOptions<AuditReportResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.audit(id),
    queryFn: () => getAuditReport(id),
    enabled: !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get audit reports for a specific county
export const useCountyAuditReports = (
  countyId: string,
  fiscalYear?: string,
  options?: Omit<UseQueryOptions<AuditReportResponse[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyAudits(countyId, fiscalYear),
    queryFn: () => getCountyAuditReports(countyId, fiscalYear),
    enabled: !!countyId,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get latest audit report for a county
export const useLatestCountyAudit = (
  countyId: string,
  options?: Omit<UseQueryOptions<AuditReportResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.latestCountyAudit(countyId),
    queryFn: () => getLatestCountyAudit(countyId),
    enabled: !!countyId,
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Infinite query for paginated audit reports
export const useAuditReportsInfinite = (
  limit: number = 20,
  filters?: Omit<AuditFilters, 'page' | 'limit'>
) => {
  return useInfiniteQuery({
    queryKey: ['audits', 'infinite', limit, filters],
    queryFn: ({ pageParam = 1 }) => getAuditReportsPaginated(pageParam, limit, filters),
    getNextPageParam: (lastPage) => {
      if (lastPage.pagination.page < lastPage.pagination.totalPages) {
        return lastPage.pagination.page + 1;
      }
      return undefined;
    },
    initialPageParam: 1,
    staleTime: 5 * 60 * 1000,
  });
};

// Get audit statistics
export const useAuditStatistics = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.statistics,
    queryFn: getAuditStatistics,
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get available fiscal years
export const useAvailableFiscalYears = (
  options?: Omit<UseQueryOptions<string[]>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.fiscalYears,
    queryFn: getAvailableFiscalYears,
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Get enriched county audits aggregation for a county
export const useCountyAuditsEnriched = (
  countyId: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyAuditsEnriched(countyId),
    queryFn: () => getCountyAuditsEnriched(countyId),
    enabled: !!countyId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
};

// New: list audits with provenance for a county
export const useCountyAuditList = (
  countyId: string,
  params?: { page?: number; limit?: number; year?: string; status?: string; severity?: string },
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.countyAuditsList(countyId, params),
    queryFn: () => getCountyAuditList(countyId, params),
    enabled: !!countyId,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
};

// The homepage's national audit summary — see `trimFederalAuditsForHome`.
export const useFederalAuditsHomeSummary = (
  options?: Omit<UseQueryOptions<FederalAuditResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    ...federalAuditsHomeSummaryQuery(),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// ===== National Audit Dashboard Hooks =====

export const useAuditDashboardSummary = (
  options?: Omit<UseQueryOptions<AuditDashboardSummary>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: auditDashboardSummaryKey(),
    queryFn: getAuditDashboardSummary,
    staleTime: 15 * 60 * 1000,
    ...options,
  });
};

export const useAuditTrends = (
  params?: { county_id?: number; query_type?: string },
  options?: Omit<UseQueryOptions<AuditTrendsData>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: auditTrendsKey(params),
    queryFn: () => getAuditTrends(params),
    staleTime: 15 * 60 * 1000,
    ...options,
  });
};

export const useRecurringFindings = (
  options?: Omit<UseQueryOptions<RecurringFindingsData>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: auditRecurringFindingsKey(),
    queryFn: getRecurringFindings,
    staleTime: 15 * 60 * 1000,
    ...options,
  });
};

export const useAuditFindings = (
  filters?: FindingsFilters,
  options?: Omit<UseQueryOptions<FindingsListData>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: auditFindingsKey(filters),
    queryFn: () => getAuditFindings(filters),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
};
