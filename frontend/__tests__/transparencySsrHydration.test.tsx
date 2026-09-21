/**
 * `/transparency` must server-render its figures, not swap them in after
 * hydration.
 *
 * `app/transparency/page.tsx` had no prefetch at all — it returned
 * `<TransparencyPageClient />` and nothing else — so the prerendered document
 * carried skeletons and not one figure. The hero waterfall, the four KPI
 * cards and the 47-row county table all arrived client-side and replaced
 * placeholders of a different height, which is the page's CLS (#221 finding
 * #6; measured 0.154 against a 0.1 budget).
 *
 * Two halves had to change together, and both are pinned here:
 *
 *   1. the server has to prefetch the two money-flow queries, under the keys
 *      the hooks read — `transparencySsrQueries()`;
 *   2. the client has to ASK for those keys on its first render. It did not:
 *      `selectedYear` started as `''` and was corrected to the API's default
 *      year by a `useEffect`. An effect does not run during server render, so
 *      the server's own render asked for `''`, both money-flow queries were
 *      `enabled: false`, and the prefetched payload was unreachable however
 *      well its key matched.
 *
 * Because (2) is a server-render property, the first test renders through
 * `react-dom/server` rather than through Testing Library. `render()` flushes
 * effects, so it would report the page working in both states and tell us
 * nothing — the document is what shifts, and the document is what
 * `renderToString` produces.
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
import { renderToString } from 'react-dom/server';

import TransparencyPageClient from '@/app/transparency/TransparencyPageClient';
import { transparencySsrQueries } from '@/lib/react-query/transparencySsrPrefetch';
import { countyFiscalYearsKey, useCountyFiscalYears } from '@/lib/react-query/useCounties';
import {
  allCountiesMoneyFlowKey,
  nationalMoneyFlowKey,
  useAllCountiesMoneyFlow,
  useNationalMoneyFlow,
} from '@/lib/react-query/useMoneyFlow';
import { transparencyYearOptions } from '@/lib/utils';

/* ── fixtures ───────────────────────────────────────────────────────── */

/** What GET /counties/fiscal-years answers with in production, trimmed. */
const FISCAL_YEARS = {
  years: [
    { label: 'FY2025/26', source: 'cra_model' as const, counties: 47 },
    { label: 'FY2024/25', source: 'cob_cbirr' as const, counties: 47 },
  ],
  default: 'FY2024/25',
};
/** The label the page resolves out of that — bare, no "FY" prefix. */
const DEFAULT_YEAR = '2024/25';

const NATIONAL = {
  county_id: null,
  county_name: 'National',
  fiscal_year: DEFAULT_YEAR,
  efficiency_score: 52.4,
  budget_source: 'cob_cbirr',
  stages: [
    { stage: 'Allocated', amount: 633_303_870_000, gap_from_prev: null },
    { stage: 'Spent', amount: 331_600_000_000, gap_from_prev: 301_703_870_000 },
    { stage: 'Flagged', amount: null, gap_from_prev: null },
  ],
};

const ALL_COUNTIES = [
  {
    county_id: '047',
    county_name: 'Nairobi County',
    fiscal_year: DEFAULT_YEAR,
    efficiency_score: 61.2,
    budget_source: 'cob_cbirr',
    stages: [
      { stage: 'Allocated', amount: 41_000_000_000, gap_from_prev: null },
      { stage: 'Spent', amount: 25_000_000_000, gap_from_prev: 16_000_000_000 },
      { stage: 'Flagged', amount: 3_000_000_000, gap_from_prev: null },
    ],
  },
];

const getCountyFiscalYears = jest.fn();
const getNationalMoneyFlow = jest.fn();
const getAllCountiesMoneyFlow = jest.fn();

// `PageShell` reads the route for its breadcrumb; outside the app router
// `usePathname()` is null and it throws before the page renders at all.
jest.mock('next/navigation', () => ({
  __esModule: true,
  usePathname: () => '/transparency',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

jest.mock('@/lib/api/counties', () => ({
  __esModule: true,
  ...jest.requireActual('@/lib/api/counties'),
  getCountyFiscalYears: (...a: unknown[]) => getCountyFiscalYears(...a),
}));

jest.mock('@/lib/api/moneyFlow', () => ({
  __esModule: true,
  ...jest.requireActual('@/lib/api/moneyFlow'),
  getNationalMoneyFlow: (...a: unknown[]) => getNationalMoneyFlow(...a),
  getAllCountiesMoneyFlow: (...a: unknown[]) => getAllCountiesMoneyFlow(...a),
}));

const allFetchers = () => [getCountyFiscalYears, getNationalMoneyFlow, getAllCountiesMoneyFlow];

beforeEach(() => {
  allFetchers().forEach((f) => f.mockReset());
  getCountyFiscalYears.mockResolvedValue(FISCAL_YEARS);
  getNationalMoneyFlow.mockResolvedValue(NATIONAL);
  getAllCountiesMoneyFlow.mockResolvedValue(ALL_COUNTIES);
});

/**
 * Do exactly what `app/transparency/page.tsx` does — resolve the fiscal-year
 * list, derive the default from it with the shared helper, prefetch
 * `transparencySsrQueries(thatYear)` — then dehydrate it the way Next embeds
 * it in the document.
 *
 * The page and this harness read the same declaration and the same helper, so
 * neither can drift from the other.
 */
async function serverState() {
  const server = new QueryClient();
  const meta = await server.fetchQuery({
    queryKey: countyFiscalYearsKey(),
    queryFn: getCountyFiscalYears as () => Promise<typeof FISCAL_YEARS>,
  });
  const year = transparencyYearOptions(meta).default as string;
  await Promise.all(transparencySsrQueries(year).map((q) => server.prefetchQuery(q)));
  const state = dehydrate(server);
  // The SSR calls are setup, not the thing under test.
  allFetchers().forEach((f) => f.mockClear());
  return state;
}

function hydratedWrapper(state: ReturnType<typeof dehydrate>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 10 * 60 * 1000 } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <HydrationBoundary state={state}>{children}</HydrationBoundary>
    </QueryClientProvider>
  );
  Wrapper.displayName = 'HydratedWrapper';
  return Wrapper;
}

/* ── the document ───────────────────────────────────────────────────── */

describe('/transparency — what the prerendered document contains', () => {
  it('server-renders the waterfall hero with its figures, not a skeleton', async () => {
    const state = await serverState();
    const Wrapper = hydratedWrapper(state);

    const html = renderToString(
      <Wrapper>
        <TransparencyPageClient />
      </Wrapper>
    );

    // The hero. Pre-fix the document took the `nationalLoading` branch.
    expect(html).toContain('Where the money went');
    expect(html).not.toContain('Loading money-flow waterfall');
    // A figure, in the document, before any client fetch. #221 observed the
    // served HTML contained no occurrence of "KES" at all.
    expect(html).toContain('KES');
    expect(html).toContain('633.30B');
  });

  it('server-renders the county table rather than its spinner', async () => {
    const state = await serverState();
    const Wrapper = hydratedWrapper(state);

    const html = renderToString(
      <Wrapper>
        <TransparencyPageClient />
      </Wrapper>
    );

    expect(html).not.toContain('Loading county data');
    expect(html).toContain('Nairobi');
    expect(html).toContain('1 of 47 counties');
  });

  it('server-renders the KPI cards, which the page hides until data arrives', async () => {
    const state = await serverState();
    const Wrapper = hydratedWrapper(state);

    const html = renderToString(
      <Wrapper>
        <TransparencyPageClient />
      </Wrapper>
    );

    // `{insights && insights.allocated != null && ...}` — an entire section
    // that appears out of nothing once the fetch lands, shoving everything
    // below it down. That insertion is the shift.
    expect(html).toContain('Total allocated');
    expect(html).toContain('National efficiency');
  });

  it('picks the fiscal year on the FIRST render, with no effect having run', async () => {
    const state = await serverState();
    const Wrapper = hydratedWrapper(state);

    const html = renderToString(
      <Wrapper>
        <TransparencyPageClient />
      </Wrapper>
    );

    // The picker pill for the API's default year is the selected one. If the
    // year were still being corrected by an effect this would be unselected
    // and the two money-flow queries would be disabled.
    expect(html).toContain('FY 2024/25');
  });
});

/* ── the hooks, served from the hydrated cache ──────────────────────── */

describe('/transparency SSR hydration — the queries the page reads', () => {
  it('serves the national money flow to the first client render', async () => {
    const wrapper = hydratedWrapper(await serverState());

    const { result } = renderHook(() => useNationalMoneyFlow(DEFAULT_YEAR), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(NATIONAL);
  });

  it('serves the all-counties money flow to the first client render', async () => {
    const wrapper = hydratedWrapper(await serverState());

    const { result } = renderHook(() => useAllCountiesMoneyFlow(DEFAULT_YEAR), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(ALL_COUNTIES);
  });

  it('serves the fiscal-year list, which is what chooses the other two keys', async () => {
    const wrapper = hydratedWrapper(await serverState());

    const { result } = renderHook(() => useCountyFiscalYears(), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(transparencyYearOptions(result.current.data).default).toBe(DEFAULT_YEAR);
  });

  it('does not re-fetch over the network what the server already sent', async () => {
    const wrapper = hydratedWrapper(await serverState());

    renderHook(
      () => {
        useCountyFiscalYears();
        useNationalMoneyFlow(DEFAULT_YEAR);
        useAllCountiesMoneyFlow(DEFAULT_YEAR);
        return null;
      },
      { wrapper }
    );

    expect(getCountyFiscalYears).not.toHaveBeenCalled();
    expect(getNationalMoneyFlow).not.toHaveBeenCalled();
    expect(getAllCountiesMoneyFlow).not.toHaveBeenCalled();
  });

  it('NEGATIVE CONTROL: a year the server did not prefetch is not served from the cache', async () => {
    const wrapper = hydratedWrapper(await serverState());

    const { result } = renderHook(() => useNationalMoneyFlow('2022/23'), { wrapper });

    // Proves the assertions above are about a key match and not about the
    // cache answering everything.
    expect(result.current.isLoading).toBe(true);
  });
});

/* ── the prefetch list itself ───────────────────────────────────────── */

describe('transparencySsrQueries', () => {
  it('pins the serialised keys the SSR prefetch writes into the HTML', () => {
    const keys = transparencySsrQueries(DEFAULT_YEAR).map((q) => hashKey(q.queryKey));

    expect(keys).toEqual([
      hashKey(nationalMoneyFlowKey(DEFAULT_YEAR)),
      hashKey(allCountiesMoneyFlowKey(DEFAULT_YEAR)),
    ]);
    expect(keys).toEqual([
      '["money-flow","national","2024/25"]',
      '["money-flow","all-counties","2024/25"]',
    ]);
  });

  it('keys on the year it is given, so the server cannot prefetch the wrong one', () => {
    const keys = transparencySsrQueries('2022/23').map((q) => hashKey(q.queryKey));

    expect(keys).toEqual([
      '["money-flow","national","2022/23"]',
      '["money-flow","all-counties","2022/23"]',
    ]);
  });
});
