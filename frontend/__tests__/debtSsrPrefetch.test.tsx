/**
 * `/debt` must not ship a query in its HTML that nothing on the page reads.
 *
 * `app/debt/page.tsx` prefetched `['debt','debt-sustainability']` and
 * dehydrated it into the document. Its only reader, `useDebtSustainability()`
 * in `DebtPageClient`, went with the gauges and the peer strip in #148; the
 * prefetch stayed. So every /debt document carried the sustainability payload
 * and every render paid for the request on the server, for no pixel. Same
 * class as #222 (`/counties`) and #224 (`/audits`).
 *
 * The test does not hand-copy either list. It runs the real server component
 * with the HTTP client mocked, takes the `state` it hands to
 * `HydrationBoundary` (what Next serialises into the document), hydrates it
 * into a client QueryClient, mounts the real `DebtPageClient` tree, and asks
 * the cache which of the dehydrated queries has a mounted observer. A key with
 * none is bytes in the document that nothing renders.
 *
 * It fails against the pre-fix page: `["debt","debt-sustainability"]` is
 * dehydrated and has zero observers.
 */
import '@testing-library/jest-dom';
import { act, render } from '@testing-library/react';
import {
  DehydratedState,
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import React, { isValidElement, ReactNode } from 'react';

import DebtPage from '@/app/debt/page';
import NationalDebtPage from '@/app/debt/DebtPageClient';
import { getQueryClient } from '@/lib/react-query/getQueryClient';

/* ── the network ────────────────────────────────────────────────────── */

/**
 * Every fetcher in `lib/api/*` and the inline `queryFn`s on this page go
 * through this one axios instance, so mocking it covers every request
 * without naming any fetcher.
 */
const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockGet(...args),
  };
  return { __esModule: true, apiClient: client, default: client };
});

// PDFExportButton reads `useAuth()`; nothing here signs anyone in.
jest.mock('@/lib/auth/AuthProvider', () => ({
  __esModule: true,
  useAuth: () => ({ isAuthenticated: false }),
}));

jest.mock('next/navigation', () => ({
  __esModule: true,
  usePathname: () => '/debt',
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

/**
 * The smallest bodies that take `DebtPageClient` past its loading and error
 * returns into the full page, so every child that could read a query mounts.
 * Anything not listed gets a placeholder object.
 */
const BODIES: Record<string, unknown> = {
  '/debt/national': {
    total_outstanding: 11_800_000_000_000,
    gdp: 17_000_000_000_000,
    summary: { external_debt: 5_600_000_000_000, domestic_debt: 6_200_000_000_000 },
    categories: {},
  },
  '/debt/loans': { loans: [] },
  '/debt/timeline': { timeline: [] },
  '/fiscal/summary': { history: [] },
  '/pending-bills': { status: 'no_data' },
  '/pending-bills/summary': {},
};

beforeEach(() => {
  // In jsdom `getQueryClient()` is the browser singleton, and the server
  // component uses it too. Left populated, a second `DebtPage()` finds fresh
  // data and prefetches nothing — which would make the request test below
  // pass for the wrong reason.
  getQueryClient().clear();
  mockGet.mockReset();
  mockGet.mockImplementation((url: string) =>
    Promise.resolve({ data: BODIES[String(url)] ?? { placeholder: String(url) } })
  );
});

// framer-motion's `whileInView` sections need it; jsdom does not ship one.
if (typeof globalThis.IntersectionObserver === 'undefined') {
  globalThis.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof IntersectionObserver;
}

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

async function serverState(): Promise<DehydratedState> {
  const state = findHydrationState(await DebtPage());
  if (!state) throw new Error('/debt: no HydrationBoundary state');
  return state;
}

/* ── tests ──────────────────────────────────────────────────────────── */

describe('/debt SSR prefetch', () => {
  it('every query the page dehydrates is read by a component the page mounts', async () => {
    const state = await serverState();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { unmount } = render(
      <QueryClientProvider client={client}>
        <HydrationBoundary state={state}>
          <NationalDebtPage />
        </HydrationBoundary>
      </QueryClientProvider>
    );
    await act(async () => {
      await Promise.resolve();
    });

    const unread = state.queries
      .filter((q) => (client.getQueryCache().get(q.queryHash)?.getObserversCount() ?? 0) === 0)
      .map((q) => q.queryHash);

    unmount();
    client.clear();

    expect(unread).toEqual([]);
  });

  it('control: the harness sees the queries the page does read', async () => {
    // Pins that an empty `unread` above means "all read", not "the tree never
    // mounted" or "nothing was dehydrated": the overview is the page's gate
    // (`backendReady = !!overview`) and must be both shipped and observed.
    const state = await serverState();
    const hashes = state.queries.map((q) => q.queryHash);
    expect(hashes).toEqual(
      expect.arrayContaining(['["debt","national"]', '["debt","national-loans"]'])
    );

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <HydrationBoundary state={state}>
          <NationalDebtPage />
        </HydrationBoundary>
      </QueryClientProvider>
    );
    await act(async () => {
      await Promise.resolve();
    });

    const observed = (hash: string) => client.getQueryCache().get(hash)?.getObserversCount() ?? 0;
    expect(observed('["debt","national"]')).toBeGreaterThan(0);
    expect(observed('["debt","national-loans"]')).toBeGreaterThan(0);
    // A child's own query: the tree got past the loading/error returns and
    // mounted its children, so a child reader would have been counted too.
    expect(observed('["debt","instruments"]')).toBeGreaterThan(0);

    unmount();
    client.clear();
  });

  it('does not request the sustainability endpoint while rendering the page', async () => {
    await serverState();
    const urls = mockGet.mock.calls.map((c) => String(c[0]));
    expect(urls.filter((u) => u.includes('/debt/sustainability'))).toEqual([]);
  });
});
