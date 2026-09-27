/**
 * A cached page must not re-download, after hydration, the data it shipped.
 *
 * #221 follow-up. OBSERVED on production: `/` served from the Vercel cache
 * (`x-vercel-cache: HIT`, `age: 1467`) re-downloaded `/api/v1/audits/federal`
 * client-side after hydration — 139,329 B gzip — and `/counties` at
 * `age: 2920` re-downloaded `/api/v1/counties`.
 *
 * The mechanism these tests pin: a server-prefetched query is dehydrated with
 * `dataUpdatedAt` = the moment the page was rendered. An ISR document is
 * served unchanged for up to `revalidate` seconds, so the hydrated entry is
 * as old as the document. React Query refetches on mount any entry older than
 * the reading hook's `staleTime`. Every hook below `revalidate` therefore
 * refetches on most visits inside each ISR window, and a route with no
 * `revalidate` at all (a static page, rendered once per deploy) refetches on
 * every visit once the deploy is older than the shortest `staleTime`.
 *
 * The harness drives each real server component (`await Page()`) with the
 * HTTP client mocked, takes the `state` it hands to `HydrationBoundary` —
 * what Next serialises into the document — ages it, hydrates it into the real
 * browser `QueryClient`, mounts the hooks the page's client reads on first
 * render, and records which endpoints are requested. Nothing here is a
 * hand-written copy of a page's prefetch list; the keys come from the page.
 */
import '@testing-library/jest-dom';
import { act, renderHook } from '@testing-library/react';
import {
  DehydratedState,
  hashKey,
  HydrationBoundary,
  QueryClientProvider,
} from '@tanstack/react-query';
import React, { isValidElement, ReactElement, ReactNode } from 'react';

import { useCompareCounties } from '@/app/counties/compare/ComparePageClient';
import { getQueryClient } from '@/lib/react-query/getQueryClient';
import { ISR_REVALIDATE_SECONDS } from '@/lib/react-query/isr';
import {
  AUDIT_FINDINGS_INITIAL_FILTERS,
  auditDashboardSummaryKey,
  auditFindingsKey,
  auditRecurringFindingsKey,
  auditTrendsKey,
  federalAuditsHomeSummaryKey,
  useAuditDashboardSummary,
  useAuditFindings,
  useAuditTrends,
  useFederalAuditsHomeSummary,
  useRecurringFindings,
} from '@/lib/react-query/useAudits';
import {
  useBudgetEnhanced,
  useBudgetOverview,
  useNationalBudgetSummary,
} from '@/lib/react-query/useBudget';
import { useCounties, useCountyFiscalYears } from '@/lib/react-query/useCounties';
import {
  useDebtTimeline,
  useNationalDebtOverview,
  useNationalLoans,
  usePendingBills,
  usePendingBillsSummary,
} from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { useAllCountiesMoneyFlow, useNationalMoneyFlow } from '@/lib/react-query/useMoneyFlow';

/* ── the network ────────────────────────────────────────────────────── */

/**
 * Every fetcher in `lib/api/*` and the compare page's inline `queryFn` go
 * through this one axios instance, so mocking it records every request the
 * hooks make without naming any fetcher.
 */
const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockGet(...args),
  };
  return { __esModule: true, apiClient: client, default: client };
});

// `/debt` and `/budget` import PDFExportButton → AuthProvider, which builds a
// Supabase browser client at module load. Nothing here signs anyone in.
jest.mock('@/lib/supabase/client', () => ({
  __esModule: true,
  createClient: () => ({}),
}));

const FY = 'FY 2024/25';

/** Server phase: answer everything, so every prefetch lands in the state. */
function serveEverything() {
  mockGet.mockImplementation((url: string) =>
    Promise.resolve({
      data: String(url).includes('fiscal-years')
        ? { years: [{ label: FY }], default: FY }
        : // `getCounties` maps over the body; every other fetcher passes it through.
          /^\/counties(\?|$)/.test(String(url))
          ? []
          : { data: [], placeholder: String(url) },
    })
  );
}

/** Client phase: record, never answer — we only care whether it was asked. */
function recordOnly() {
  mockGet.mockReset();
  mockGet.mockImplementation(() => new Promise(() => {}));
}

const requested = () => mockGet.mock.calls.map((c) => String(c[0]));

/* ── the routes ─────────────────────────────────────────────────────── */

interface Reader {
  /** What the page's client component calls on its first render. */
  useReader: () => unknown;
}

interface Route {
  path: string;
  load: () => Promise<{
    default: () => Promise<ReactElement>;
    revalidate?: number;
  }>;
  /**
   * The hooks the page's client tree calls on first render, keyed by the
   * serialised query key each one reads. A dehydrated key with no entry here
   * fails the coverage test below rather than being silently skipped.
   */
  readers: Record<string, Reader>;
  /** Dehydrated keys no client component reads. Each needs a reason. */
  unread?: Record<string, string>;
}

const ROUTES: Route[] = [
  {
    path: '/',
    load: () => import('@/app/page') as never,
    readers: {
      [hashKey(federalAuditsHomeSummaryKey())]: {
        useReader: () => useFederalAuditsHomeSummary(),
      },
      '["budget","national",null]': {
        useReader: () => useNationalBudgetSummary(),
      },
      '["counties","filtered",null]': { useReader: () => useCounties() },
      '["debt","national"]': { useReader: () => useNationalDebtOverview() },
      '["debt","national-loans"]': { useReader: () => useNationalLoans() },
      '["debt","national-timeline"]': { useReader: () => useDebtTimeline() },
      '["fiscal","summary"]': { useReader: () => useFiscalSummary() },
    },
  },
  {
    path: '/counties',
    load: () => import('@/app/counties/page') as never,
    readers: {
      '["counties","filtered",null]': {
        useReader: () => useCounties({ fiscalYear: undefined }),
      },
    },
  },
  {
    path: '/audits',
    load: () => import('@/app/audits/page') as never,
    readers: {
      [hashKey(auditDashboardSummaryKey())]: {
        useReader: () => useAuditDashboardSummary(),
      },
      [hashKey(auditTrendsKey())]: { useReader: () => useAuditTrends() },
      [hashKey(auditRecurringFindingsKey())]: {
        useReader: () => useRecurringFindings(),
      },
      [hashKey(auditFindingsKey(AUDIT_FINDINGS_INITIAL_FILTERS))]: {
        useReader: () => useAuditFindings(AUDIT_FINDINGS_INITIAL_FILTERS),
      },
    },
  },
  {
    path: '/transparency',
    load: () => import('@/app/transparency/page') as never,
    readers: {
      '["counties","fiscal-years"]': {
        useReader: () => useCountyFiscalYears(),
      },
      '["money-flow","national","2024/25"]': {
        useReader: () => useNationalMoneyFlow('2024/25'),
      },
      '["money-flow","all-counties","2024/25"]': {
        useReader: () => useAllCountiesMoneyFlow('2024/25'),
      },
    },
  },
  {
    path: '/counties/compare',
    load: () => import('@/app/counties/compare/page') as never,
    readers: {
      '["counties","all-for-compare"]': {
        useReader: () => useCompareCounties(),
      },
    },
  },
  {
    path: '/debt',
    load: () => import('@/app/debt/page') as never,
    readers: {
      '["debt","national"]': { useReader: () => useNationalDebtOverview() },
      // `DebtPageClient` gates these on `backendReady = !!overview`, which is
      // true on first render when the overview is hydrated.
      '["debt","national-loans"]': {
        useReader: () => useNationalLoans({ enabled: true }),
      },
      '["debt","national-timeline"]': {
        useReader: () => useDebtTimeline({ enabled: true }),
      },
      '["fiscal","summary"]': {
        useReader: () => useFiscalSummary({ enabled: true }),
      },
      '["debt","pending-bills"]': {
        useReader: () => usePendingBills({ enabled: true }),
      },
      '["debt","pending-bills-summary"]': {
        useReader: () => usePendingBillsSummary({ enabled: true }),
      },
    },
  },
  {
    path: '/budget',
    load: () => import('@/app/budget/page') as never,
    readers: {
      '["budget","overview"]': { useReader: () => useBudgetOverview() },
      '["budget","enhanced"]': { useReader: () => useBudgetEnhanced() },
      '["fiscal","summary"]': { useReader: () => useFiscalSummary() },
    },
  },
];

/* ── harness ────────────────────────────────────────────────────────── */

/** The `state` a server component hands to `HydrationBoundary`. */
function findHydrationState(node: ReactNode): DehydratedState | undefined {
  if (!isValidElement(node)) return undefined;
  const props = node.props as { state?: DehydratedState; children?: ReactNode };
  if (node.type === HydrationBoundary) return props.state;
  for (const child of React.Children.toArray(props.children)) {
    const found = findHydrationState(child);
    if (found) return found;
  }
  return undefined;
}

async function renderServerState(route: Route) {
  serveEverything();
  const mod = await route.load();
  const state = findHydrationState(await mod.default());
  if (!state) throw new Error(`${route.path}: no HydrationBoundary state`);
  return { state, revalidate: mod.revalidate };
}

/** The document as it is served `ageMs` after it was rendered. */
function aged(state: DehydratedState, ageMs: number): DehydratedState {
  const copy: DehydratedState = JSON.parse(JSON.stringify(state));
  for (const q of copy.queries) q.state.dataUpdatedAt = Date.now() - ageMs;
  return copy;
}

/**
 * Hydrate `state` into the real browser QueryClient (the `getQueryClient()`
 * singleton `QueryProvider` uses, with its real defaults), mount every reader,
 * and return the endpoints the mount asked for.
 */
async function refetchesOnMount(route: Route, state: DehydratedState): Promise<string[]> {
  const client = getQueryClient();
  client.clear();
  recordOnly();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <HydrationBoundary state={state}>{children}</HydrationBoundary>
    </QueryClientProvider>
  );
  const readers = Object.values(route.readers);
  const { unmount } = renderHook(() => readers.map((r) => r.useReader()), {
    wrapper,
  });
  await act(async () => {
    await Promise.resolve();
  });
  unmount();
  client.clear();
  return requested();
}

const MIN = 60 * 1000;

/* ── 1. the key inventory comes from the page, and is fully covered ──── */

describe.each(ROUTES)('$path', (route) => {
  it('every query the page dehydrates is read by a mounted hook, or its absence is explained', async () => {
    const { state } = await renderServerState(route);
    const dehydrated = state.queries.map((q) => q.queryHash).sort();
    const accounted = [...Object.keys(route.readers), ...Object.keys(route.unread ?? {})].sort();
    expect(dehydrated).toEqual(accounted);
  });

  /* ── 2. control: the mechanism, both ways ─────────────────────────── */

  it('control: a freshly rendered document hydrates with no request', async () => {
    const { state } = await renderServerState(route);
    expect(await refetchesOnMount(route, aged(state, 0))).toEqual([]);
  });

  it('control: a document older than a day re-requests every query it hydrated', async () => {
    // Pins that hydrated data does go stale — the fix must not be
    // `staleTime: Infinity`. A day is past any revalidate window here.
    const { state } = await renderServerState(route);
    const reqs = await refetchesOnMount(route, aged(state, 24 * 60 * MIN));
    expect(reqs).toHaveLength(Object.keys(route.readers).length);
  });

  /* ── 3. the defect ────────────────────────────────────────────────── */

  it('declares an ISR window, so the document it hydrates from has a bounded age', async () => {
    // Without `revalidate`, the page is static: rendered once at build and
    // served until the next deploy. OBSERVED on production 2026-09-27:
    // `/debt` at `age: 400136` (4.6 days), `/budget` at `age: 510573`.
    const { revalidate } = await renderServerState(route);
    expect(typeof revalidate).toBe('number');
    // Next needs the export to be a literal, so the pages cannot import the
    // constant the hooks' staleTime is built from. This is the link instead.
    expect(revalidate).toBe(ISR_REVALIDATE_SECONDS);
  });

  it('a document served inside its ISR window hydrates with no request', async () => {
    const { state, revalidate } = await renderServerState(route);
    // The oldest a document can be while still inside the window. (Past it,
    // Vercel serves it STALE while regenerating — the day-old control covers
    // that the client then does refetch.)
    const ageMs = (revalidate ?? Number.POSITIVE_INFINITY) * 1000 - MIN;
    const probe = Number.isFinite(ageMs) ? ageMs : 24 * 60 * MIN;
    expect(await refetchesOnMount(route, aged(state, probe))).toEqual([]);
  });
});
