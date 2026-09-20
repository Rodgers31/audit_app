/**
 * The County Explorer's SSR prefetch must actually be readable by the hook
 * that renders the page.
 *
 * `app/counties/page.tsx` prefetches the county list on the server and ships
 * it in the HTML. `CountiesPageClient` then reads it with
 * `useCounties({ fiscalYear: pickedYear })`, where `pickedYear` is `undefined`
 * on first render. Those two sides built DIFFERENT React Query cache keys:
 *
 *     server: ['counties', 'filtered', undefined]        → ["counties","filtered",null]
 *     client: ['counties', 'filtered', {fiscalYear: undefined}] → ["counties","filtered",{}]
 *
 * so the hydrated entry was never found. The hook reported `isLoading`, the
 * page took its `if (isLoading)` early return, and the prerendered HTML was a
 * spinner — with all 47 counties sitting unused in the same document. The
 * real content only appeared after hydration re-fetched the identical list
 * over the network, which is what pushed LCP 4.6s past FCP in production.
 *
 * `getCounties(undefined)` and `getCounties({fiscalYear: undefined})` issue
 * the byte-identical request (see `lib/api/counties.ts` — every param is
 * guarded by a truthiness check), so collapsing them onto one cache key
 * cannot change what is fetched. It only lets the page find what the server
 * already paid for.
 *
 * These tests fail against the pre-fix hook: the seeded cache is not found
 * and `useCounties` comes back loading.
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

import { COUNTIES_FILTERED_KEY_ROOT, countiesFilteredKey, useCounties } from '@/lib/react-query/useCounties';
import type { County } from '@/types';

/* ── fixtures ───────────────────────────────────────────────────────── */

const COUNTY_LIST = [
  { id: '047', name: 'Mombasa', code: '047', budget_2025: 14_630_000_000 },
  { id: '001', name: 'Nairobi', code: '001', budget_2025: 41_000_000_000 },
] as unknown as County[];

/** Exactly what `app/counties/page.tsx` passes to `prefetchQuery`. */
const ssrPrefetchKey = () => countiesFilteredKey();

/** Exactly what `CountiesPageClient` renders with before a year is picked. */
const FIRST_RENDER_FILTERS = { fiscalYear: undefined };

const getCounties = jest.fn();
jest.mock('@/lib/api/counties', () => ({
  __esModule: true,
  ...jest.requireActual('@/lib/api/counties'),
  getCounties: (...args: unknown[]) => getCounties(...args),
}));

beforeEach(() => {
  getCounties.mockReset();
  getCounties.mockResolvedValue(COUNTY_LIST);
});

/**
 * Reproduce the real transport: a server QueryClient prefetches, the result is
 * dehydrated into the HTML, and a fresh client QueryClient hydrates it. Going
 * through dehydrate/HydrationBoundary rather than `setQueryData` is the point
 * — the key is serialised on the way through, which is where the two shapes
 * stopped matching.
 */
async function hydratedWrapper() {
  const server = new QueryClient();
  await server.prefetchQuery({
    queryKey: ssrPrefetchKey(),
    queryFn: async () => COUNTY_LIST,
  });
  const state = dehydrate(server);

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30 * 60 * 1000 } },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <HydrationBoundary state={state}>{children}</HydrationBoundary>
      </QueryClientProvider>
    );
  };
}

/* ── the defect ─────────────────────────────────────────────────────── */

describe('County Explorer SSR hydration', () => {
  it('serves the SSR-prefetched list to the first client render — no loading state', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(() => useCounties(FIRST_RENDER_FILTERS), { wrapper });

    // The page's `if (isLoading) return <spinner/>` branch keys off exactly
    // this. If it is true on first render, the prerendered HTML is a spinner.
    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(COUNTY_LIST);
  });

  it('does not re-fetch over the network what the server already sent', async () => {
    const wrapper = await hydratedWrapper();

    renderHook(() => useCounties(FIRST_RENDER_FILTERS), { wrapper });

    expect(getCounties).not.toHaveBeenCalled();
  });

  it('still serves the homepage shape, which passes no filters at all', async () => {
    const wrapper = await hydratedWrapper();

    const { result } = renderHook(() => useCounties(), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual(COUNTY_LIST);
  });
});

/* ── the key rule the fix rests on ──────────────────────────────────── */

describe('countiesFilteredKey', () => {
  it('hashes an all-undefined filter object the same as no filters', () => {
    expect(hashKey(countiesFilteredKey(FIRST_RENDER_FILTERS))).toBe(
      hashKey(countiesFilteredKey())
    );
  });

  it('keeps a real fiscal year on its own key, so picking a year still refetches', () => {
    expect(hashKey(countiesFilteredKey({ fiscalYear: '2023/24' }))).not.toBe(
      hashKey(countiesFilteredKey())
    );
    expect(hashKey(countiesFilteredKey({ fiscalYear: '2023/24' }))).not.toBe(
      hashKey(countiesFilteredKey({ fiscalYear: '2024/25' }))
    );
  });

  it('pins the serialised key the SSR prefetch writes into the HTML', () => {
    // The dehydrated cache in the document is keyed by this exact string. A
    // change here silently orphans every server prefetch of the county list.
    expect(hashKey(countiesFilteredKey())).toBe('["counties","filtered",null]');
    expect(COUNTIES_FILTERED_KEY_ROOT).toEqual(['counties', 'filtered']);
  });
});
