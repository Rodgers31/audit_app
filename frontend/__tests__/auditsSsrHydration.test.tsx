/**
 * `/audits` must prefetch the queries it renders — and only those.
 *
 * `app/audits/page.tsx` prefetched exactly one query, `['audits','federal']`:
 * 886KB of national audit findings whose only consumer is
 * `components/dashboard/AuditReportsSection`, which is rendered on `/` and
 * appears nowhere in this route's tree. The four queries `AuditsPageClient`
 * does read —
 *
 *     ['audit','dashboard','summary']
 *     ['audit','dashboard','trends',   undefined]
 *     ['audit','dashboard','recurring']
 *     ['audit','dashboard','findings', {page:1,limit:20}]
 *
 * — were not prefetched at all. So the prerendered document carried 886KB
 * nothing on the page reads, took the `if (summaryLoading)` early return, and
 * shipped a spinner; the four real payloads then arrived over the network
 * after hydration. That is the FCP→LCP gap #221 measured on this route.
 *
 * These tests drive the real transport — a server QueryClient prefetches
 * `auditsSsrQueries()`, the result is dehydrated as it would be into the HTML,
 * and a fresh client QueryClient hydrates it — rather than calling
 * `setQueryData`, because serialisation through the boundary is exactly where
 * a server key and a hook key stop matching.
 *
 * They fail against the pre-fix prefetch list: none of the four hooks finds a
 * hydrated entry, every one reports `isLoading`, and every one hits the
 * network.
 */
import '@testing-library/jest-dom';
import { renderHook } from '@testing-library/react';
import {
  dehydrate,
  hashKey,
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import React from 'react';

import { auditsSsrQueries } from '@/lib/react-query/auditsSsrPrefetch';
import {
  AUDIT_DASHBOARD_KEY_ROOT,
  AUDIT_FINDINGS_INITIAL_FILTERS,
  auditDashboardSummaryKey,
  auditFindingsKey,
  auditRecurringFindingsKey,
  auditTrendsKey,
  federalAuditsKey,
  useAuditDashboardSummary,
  useAuditFindings,
  useAuditTrends,
  useFederalAudits,
  useRecurringFindings,
} from '@/lib/react-query/useAudits';

/* ── fixtures ───────────────────────────────────────────────────────── */

const SUMMARY = { total_findings: 2312, findings_by_type: { Procurement: 12 } };
const TRENDS = { years: [2023, 2024], findings_per_year: { '2023': 10, '2024': 12 } };
const RECURRING = { recurring: [] };
const FINDINGS = { total: 2312, page: 1, limit: 20, findings: [{ id: 1 }] };

const FEDERAL = { report_title: 'Report of the Auditor-General', findings: [{ id: 1 }] };

const getAuditDashboardSummary = jest.fn();
const getAuditTrends = jest.fn();
const getRecurringFindings = jest.fn();
const getAuditFindings = jest.fn();
const getFederalAudits = jest.fn();

jest.mock('@/lib/api/audits', () => ({
  __esModule: true,
  ...jest.requireActual('@/lib/api/audits'),
  getAuditDashboardSummary: (...a: unknown[]) => getAuditDashboardSummary(...a),
  getAuditTrends: (...a: unknown[]) => getAuditTrends(...a),
  getRecurringFindings: (...a: unknown[]) => getRecurringFindings(...a),
  getAuditFindings: (...a: unknown[]) => getAuditFindings(...a),
  getFederalAudits: (...a: unknown[]) => getFederalAudits(...a),
}));

const allFetchers = () => [
  getAuditDashboardSummary,
  getAuditTrends,
  getRecurringFindings,
  getAuditFindings,
  getFederalAudits,
];

beforeEach(() => {
  allFetchers().forEach((f) => f.mockReset());
  getAuditDashboardSummary.mockResolvedValue(SUMMARY);
  getAuditTrends.mockResolvedValue(TRENDS);
  getRecurringFindings.mockResolvedValue(RECURRING);
  getAuditFindings.mockResolvedValue(FINDINGS);
  getFederalAudits.mockResolvedValue(FEDERAL);
});

/**
 * Prefetch exactly what the server component prefetches, dehydrate it the way
 * Next.js embeds it in the document, and hydrate it into a fresh client.
 *
 * `auditsSsrQueries()` is the same array `app/audits/page.tsx` maps over, so
 * this harness cannot drift from the page it is meant to pin.
 */
async function hydratedWrapper() {
  const server = new QueryClient();
  await Promise.all(auditsSsrQueries().map((q) => server.prefetchQuery(q)));
  const state = dehydrate(server);

  // The SSR calls are setup, not the thing under test.
  allFetchers().forEach((f) => f.mockClear());

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 15 * 60 * 1000 } },
  });

  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <HydrationBoundary state={state}>{children}</HydrationBoundary>
    </QueryClientProvider>
  );
  return Wrapper;
}

/* ── the defect: the four hooks the page renders ────────────────────── */

describe('/audits SSR hydration — the queries AuditsPageClient actually reads', () => {
  it('serves the dashboard summary to the first client render — no loading state', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(() => useAuditDashboardSummary(), { wrapper });

    // `AuditsPageClient` gates its whole page on exactly this: `if
    // (summaryLoading) return <spinner/>`. True on first render means the
    // prerendered HTML is a spinner and nothing else.
    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(SUMMARY);
  });

  it('serves the trends series to the first client render', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(() => useAuditTrends(), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(TRENDS);
  });

  it('serves the recurring findings to the first client render', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(() => useRecurringFindings(), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(RECURRING);
  });

  it('serves the first page of findings to the first client render', async () => {
    const wrapper = await hydratedWrapper();

    // Exactly what the client renders with before the reader touches a filter.
    const { result } = renderHook(() => useAuditFindings(AUDIT_FINDINGS_INITIAL_FILTERS), {
      wrapper,
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(FINDINGS);
  });

  it('does not re-fetch over the network what the server already sent', async () => {
    const wrapper = await hydratedWrapper();

    renderHook(
      () => {
        useAuditDashboardSummary();
        useAuditTrends();
        useRecurringFindings();
        useAuditFindings(AUDIT_FINDINGS_INITIAL_FILTERS);
        return null;
      },
      { wrapper }
    );

    expect(getAuditDashboardSummary).not.toHaveBeenCalled();
    expect(getAuditTrends).not.toHaveBeenCalled();
    expect(getRecurringFindings).not.toHaveBeenCalled();
    expect(getAuditFindings).not.toHaveBeenCalled();
  });
});

/* ── the prefetch list itself ───────────────────────────────────────── */

describe('auditsSsrQueries', () => {
  it('prefetches every key the page reads, and nothing it does not', () => {
    const keys = auditsSsrQueries().map((q) => hashKey(q.queryKey));

    expect(keys).toEqual([
      hashKey(auditDashboardSummaryKey()),
      hashKey(auditTrendsKey()),
      hashKey(auditRecurringFindingsKey()),
      hashKey(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS)),
    ]);

    // The 886KB blob whose only consumer, AuditReportsSection, this route
    // does not render. Paying for it here bought nothing.
    expect(keys).not.toContain(hashKey(['audits', 'federal']));
  });
});

/* ── the key rules the fix rests on ─────────────────────────────────── */

describe('audit dashboard cache keys', () => {
  it('pins the serialised keys the SSR prefetch writes into the HTML', () => {
    // The dehydrated cache in the document is keyed by these exact strings. A
    // change here silently orphans the server prefetch all over again.
    expect(hashKey(auditDashboardSummaryKey())).toBe('["audit","dashboard","summary"]');
    expect(hashKey(auditTrendsKey())).toBe('["audit","dashboard","trends",null]');
    expect(hashKey(auditRecurringFindingsKey())).toBe('["audit","dashboard","recurring"]');
    expect(hashKey(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS))).toBe(
      '["audit","dashboard","findings",{"limit":20,"page":1}]'
    );
    expect(AUDIT_DASHBOARD_KEY_ROOT).toEqual(['audit', 'dashboard']);
  });

  it('NEGATIVE CONTROL: a real filter keeps its own key, so picking one still refetches', () => {
    const base = hashKey(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS));

    expect(hashKey(auditFindingsKey({ ...AUDIT_FINDINGS_INITIAL_FILTERS, year: 2023 }))).not.toBe(
      base
    );
    expect(
      hashKey(auditFindingsKey({ ...AUDIT_FINDINGS_INITIAL_FILTERS, query_type: 'Procurement' }))
    ).not.toBe(base);
    expect(hashKey(auditFindingsKey({ ...AUDIT_FINDINGS_INITIAL_FILTERS, page: 2 }))).not.toBe(base);
    expect(hashKey(auditTrendsKey({ county_id: 47 }))).not.toBe(hashKey(auditTrendsKey()));
  });

  it('NEGATIVE CONTROL: a real filter is not served from the hydrated cache', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(
      () => useAuditFindings({ ...AUDIT_FINDINGS_INITIAL_FILTERS, year: 2023 }),
      { wrapper }
    );

    // The server prefetched page 1 unfiltered; a year filter is a different
    // question and must go to the API.
    expect(result.current.isLoading).toBe(true);
    expect(getAuditFindings).toHaveBeenCalledWith({ page: 1, limit: 20, year: 2023 });
  });

  it('clearing one filter returns to the prefetched key instead of splitting the cache', () => {
    // `updateFilter` writes `{...prev, [key]: value || undefined}`, so
    // clearing a year leaves `{page:1, limit:20, year: undefined}`. Without
    // normalisation that hashes to a THIRD entry — same request, third fetch.
    expect(
      hashKey(auditFindingsKey({ ...AUDIT_FINDINGS_INITIAL_FILTERS, year: undefined }))
    ).toBe(hashKey(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS)));

    expect(hashKey(auditTrendsKey({ county_id: undefined }))).toBe(hashKey(auditTrendsKey()));
  });
});

/* ── the homepage's federal prefetch — the last hand-written SSR key ─── */

/**
 * `/audits` no longer prefetches `['audits','federal']`, but `/` still does,
 * and that prefetch is the one carrying the 886KB payload.
 *
 * `app/page.tsx` used to write the key out as a literal while
 * `useFederalAudits` read `QUERY_KEYS.federal`. The two matched only because
 * they happened to be equal — the same coincidence that stopped holding on
 * `/counties` (#222). Both now resolve to `federalAuditsKey()`.
 */
describe('homepage federal audits prefetch', () => {
  /** Exactly what `app/page.tsx` passes to `prefetchQuery`. */
  const homepagePrefetchKey = () => federalAuditsKey();

  it('serves the SSR-prefetched federal payload to AuditReportsSection — no loading state', async () => {
    const server = new QueryClient();
    await server.prefetchQuery({
      queryKey: homepagePrefetchKey(),
      queryFn: () => getFederalAudits(),
    });
    const state = dehydrate(server);
    getFederalAudits.mockClear();

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 15 * 60 * 1000 } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>
        <HydrationBoundary state={state}>{children}</HydrationBoundary>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useFederalAudits(), { wrapper });

    // `AuditReportsSection` gates on this. If the homepage prefetch key ever
    // drifts from the hook's, 886KB sits unread in a 1.32MB document and the
    // component re-fetches all of it over the network.
    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(FEDERAL);
    expect(getFederalAudits).not.toHaveBeenCalled();
  });

  it('pins the serialised key, which the hook and the prefetch must share', () => {
    expect(hashKey(federalAuditsKey())).toBe('["audits","federal"]');
  });
});
