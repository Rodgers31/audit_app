/**
 * `/counties` must server-render its content, and its URL state must keep
 * working when it does.
 *
 * #221 finding #3. `CountyRankingsTable` called `useSearchParams()` for one
 * purpose — as a `useEffect` dependency, to re-read `?p=` / `?view=all` from
 * `window.location` when a Next.js navigation changed them. On a statically
 * prerendered route that hook bails the render out to the client: Next throws
 * `BailoutToCSRError` during the build's prerender, and the nearest Suspense
 * boundary — here the one `app/counties/loading.tsx` puts around the page —
 * ships its fallback instead. The whole explorer, not just the table, was
 * therefore absent from the served HTML, including the page's LCP element
 * (the provenance note, `components/ModelledDataNote.tsx`):
 *
 *   $ curl -s https://www.auditgava.com/counties | grep -c 'text-amber-900/90'
 *   0
 *
 * The hook stays, but it now lives in a leaf that renders nothing, behind its
 * own `<Suspense fallback={null}>`, so only that empty leaf is client-rendered.
 * The rest of this file is the price of that: once the table is in the HTML,
 * the server's render and the browser's first render have to agree, and the
 * server of a static page cannot see the query string.
 *
 * Three groups:
 *
 *   1. REGRESSION GUARDS for the URL state as it already works — deep links,
 *      pagination, View All, back/forward, a Next navigation that changes the
 *      query, and a filter that empties the current page. Written against the
 *      pre-fix code first and seen GREEN there: they pin behaviour the fix
 *      must not change, not the defect.
 *   2. THE DEFECT — what a static prerender of the page contains.
 *   3. THE HAZARD the fix creates — hydrating server HTML (rendered without a
 *      query) in a browser whose URL has one.
 *
 * Round17 (#291) aligns normalization with the original browser contract:
 * an out-of-range page clamps to the last page. The added normalization and
 * simultaneous-navigation cases were seen red before their respective fixes.
 *
 * `useSearchParams` is mocked because the real one needs Next's app-router
 * context. The static-prerender mock throws an error carrying the same
 * `digest` Next's `BailoutToCSRError` carries; that it reproduces the real
 * build's behaviour is checked separately, against the prerendered
 * `.next/server/app/counties.html` (see the PR).
 */
import '@testing-library/jest-dom';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React, { Suspense } from 'react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';

import type { County } from '@/types';

/* ── fixtures ───────────────────────────────────────────────────────── */

/**
 * 25 counties — three pages of ten — with strictly descending budgets, so
 * the page opens (budget high → low) in name order and a page is a known
 * slice of names.
 */
const NAMES = Array.from({ length: 25 }, (_, i) => `Testcounty ${String(i + 1).padStart(2, '0')}`);
const COUNTIES: County[] = NAMES.map(
  (name, i) =>
    ({
      id: String(i + 1).padStart(3, '0'),
      name,
      code: String(i + 1).padStart(3, '0'),
      population: 100_000 + i,
      budget: (30 - i) * 1e9,
      totalBudget: (30 - i) * 1e9,
      budgetSource: 'cob_cbirr',
      debt: 1e8,
      totalDebt: 1e8,
      budgetUtilization: 70,
      financial_health_score: 50,
      audit_rating: '',
      auditStatus: 'pending',
    }) as County
);
const PAGE_1 = NAMES.slice(0, 10);
const PAGE_2 = NAMES.slice(10, 20);
const PAGE_3 = NAMES.slice(20, 25);

/** First words of the LCP element's text for a CBIRR-sourced list. */
const PROVENANCE_NOTE = 'County budget figures are the Controller of Budget';
const LOADING_FALLBACK = 'LOADING-SKELETON';

/* ── harness ────────────────────────────────────────────────────────── */

/**
 * The navigation mock. `replace` really moves `window.location`, as Next's
 * does. `useSearchParams` returns one object per distinct query string —
 * identity changes only when the query does — which is the property the
 * page's resync effect depends on.
 */
const mockNavigation = {
  staticPrerender: false,
  replace: jest.fn((url: string) => window.history.replaceState(null, '', url)),
  push: jest.fn(),
  cache: null as { key: string; value: URLSearchParams } | null,
};

// Simulated external navigations bypass the observer. Product list changes
// are observed through the native History API, which Next integrates without
// a server navigation. Keep the original implementation for harness inputs.
const replaceHistoryInput = window.history.replaceState.bind(window.history);
let listHistoryReplace: jest.SpyInstance;

jest.mock('next/navigation', () => ({
  usePathname: () => '/counties',
  useRouter: () => ({ replace: mockNavigation.replace, push: mockNavigation.push }),
  useSearchParams: () => {
    if (mockNavigation.staticPrerender) {
      // What Next does in a static prerender: `bailoutToClientRendering`
      // throws `BailoutToCSRError`, whose digest this is.
      const err = new Error('Bail out to client-side rendering: useSearchParams()');
      (err as Error & { digest: string }).digest = 'BAILOUT_TO_CLIENT_SIDE_RENDERING';
      throw err;
    }
    const key = window.location.search;
    if (!mockNavigation.cache || mockNavigation.cache.key !== key) {
      mockNavigation.cache = { key, value: new URLSearchParams(key) };
    }
    return mockNavigation.cache.value;
  },
}));

jest.mock('@/lib/react-query', () => ({
  useCounties: () => ({
    data: (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__,
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
  useCountyFiscalYears: () => ({ data: undefined, isLoading: false, error: null }),
}));

// Freshness is an independent API-backed widget; pagination fixtures must not
// start unrelated HTTP reads or query retry timers while rendering the page.
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));

// eslint-disable-next-line import/first
import CountiesPageClient from '@/app/counties/CountiesPageClient';

(global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = COUNTIES;

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** The page as `app/counties/page.tsx` + `loading.tsx` mount it. */
function Page({ client }: { client: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <Suspense fallback={<div>{LOADING_FALLBACK}</div>}>
        <CountiesPageClient />
      </Suspense>
    </QueryClientProvider>
  );
}

function renderExplorer() {
  return render(
    <React.StrictMode>
      <Page client={newClient()} />
    </React.StrictMode>
  );
}

function goTo(url: string) {
  replaceHistoryInput(null, '', url);
}

function rankingTable(root: ParentNode = document): HTMLTableElement {
  const table = Array.from(root.querySelectorAll('table')).find((t) =>
    Array.from(t.querySelectorAll('th')).some((th) => /population/i.test(th.textContent ?? ''))
  );
  if (!table) throw new Error('ranking table not rendered');
  return table;
}

/** County names in the ranking table, in render order. */
function rankedNames(root: ParentNode = document): string[] {
  return Array.from(rankingTable(root).querySelectorAll('tbody tr')).map((tr) =>
    (tr.querySelectorAll('td')[1]?.querySelector('a span:last-child')?.textContent ?? '').trim()
  );
}

function pageButton(n: number): HTMLElement {
  return screen.getByRole('button', { name: String(n) });
}

beforeEach(() => {
  (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = COUNTIES;
  mockNavigation.staticPrerender = false;
  mockNavigation.replace.mockClear();
  mockNavigation.push.mockClear();
  mockNavigation.cache = null;
  goTo('/counties');
  listHistoryReplace = jest.spyOn(window.history, 'replaceState').mockImplementation(() => undefined);
});

afterEach(() => listHistoryReplace.mockRestore());

/* ── 1. regression guards: the URL state as it already works ────────── */

describe('/counties URL state — normalization and regression guards', () => {
  it('opens on page 1 when the URL carries no query', () => {
    renderExplorer();
    expect(rankedNames()).toEqual(PAGE_1);
  });

  it('opens a ?p=2 deep link on page 2', () => {
    goTo('/counties?p=2');
    renderExplorer();
    expect(rankedNames()).toEqual(PAGE_2);
  });

  it('opens a ?view=all deep link with every county listed', () => {
    goTo('/counties?view=all');
    renderExplorer();
    expect(rankedNames()).toEqual(NAMES);
  });

  it('clamps an out-of-range ?p= to the last page and preserves other query parameters', () => {
    goTo('/counties?p=99&from=test');
    renderExplorer();
    expect(rankedNames()).toEqual(PAGE_3);
    expect(listHistoryReplace).toHaveBeenLastCalledWith(null, '', '/counties?p=3&from=test');
    expect(window.location.search).toBe('?p=3&from=test');
  });

  it('clamps to the last remaining page when a new county list has only two pages', () => {
    goTo('/counties?p=3');
    const { rerender } = renderExplorer();
    (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = COUNTIES.slice(0, 15);
    rerender(<React.StrictMode><Page client={newClient()} /></React.StrictMode>);
    expect(rankedNames()).toEqual(NAMES.slice(10, 15));
    expect(window.location.search).toBe('?p=2');
  });

  it.each([1, 2])('preserves a new valid page %s when navigation and a smaller list arrive together', (next) => {
    goTo('/counties?p=3');
    const { rerender } = renderExplorer();
    // Next navigation updates searchParams without a popstate. Its sync
    // effect and the smaller list's normalization effect share this commit.
    goTo(`/counties?p=${next}&from=navigation`);
    (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = COUNTIES.slice(0, 15);
    rerender(<React.StrictMode><Page client={newClient()} /></React.StrictMode>);
    expect(rankedNames()).toEqual(NAMES.slice((next - 1) * 10, Math.min(next * 10, 15)));
    expect(window.location.search).toBe(`?p=${next}&from=navigation`);
    expect(listHistoryReplace).not.toHaveBeenCalled();
  });

  it('preserves a new View All navigation when a smaller list arrives in the same commit', () => {
    goTo('/counties?p=3');
    const { rerender } = renderExplorer();
    goTo('/counties?view=all&from=navigation');
    (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = COUNTIES.slice(0, 15);
    rerender(<React.StrictMode><Page client={newClient()} /></React.StrictMode>);
    expect(rankedNames()).toEqual(NAMES.slice(0, 15));
    expect(window.location.search).toBe('?view=all&from=navigation');
    expect(listHistoryReplace).not.toHaveBeenCalled();
  });

  it('keeps the requested page while search has zero matches, then restores it when cleared', () => {
    goTo('/counties?p=3');
    renderExplorer();
    const search = screen.getByRole('searchbox', { name: 'Search County' });
    fireEvent.change(search, { target: { value: 'no-such-county' } });
    expect(rankedNames()).toEqual([]);
    expect(window.location.search).toBe('?p=3');
    expect(listHistoryReplace).not.toHaveBeenCalled();
    fireEvent.change(search, { target: { value: '' } });
    expect(rankedNames()).toEqual(PAGE_3);
  });

  it('does not normalize an irrelevant page in View All mode', () => {
    goTo('/counties?view=all&p=99');
    renderExplorer();
    expect(rankedNames()).toEqual(NAMES);
    expect(listHistoryReplace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /show paginated/i }));
    expect(rankedNames()).toEqual(PAGE_3);
    expect(window.location.search).toBe('?p=3');
  });

  it('writes ?p=N with native replaceState when a page is picked, and shows that page', () => {
    renderExplorer();
    fireEvent.click(pageButton(2));
    expect(listHistoryReplace).toHaveBeenLastCalledWith(null, '', '/counties?p=2');
    expect(window.location.search).toBe('?p=2');
    expect(mockNavigation.replace).not.toHaveBeenCalled();
    expect(rankedNames()).toEqual(PAGE_2);
  });

  it('writes ?view=all and strips ?p= when View All is toggled on', () => {
    goTo('/counties?p=2');
    renderExplorer();
    fireEvent.click(screen.getByRole('button', { name: /view all counties/i }));
    expect(listHistoryReplace).toHaveBeenLastCalledWith(null, '', '/counties?view=all');
    expect(window.location.search).toBe('?view=all');
    expect(rankedNames()).toEqual(NAMES);

    fireEvent.click(screen.getByRole('button', { name: /show paginated/i }));
    expect(listHistoryReplace).toHaveBeenLastCalledWith(null, '', '/counties');
    expect(window.location.search).toBe('');
    expect(mockNavigation.replace).not.toHaveBeenCalled();
    expect(rankedNames()).toEqual(PAGE_1);
  });

  it('follows browser back/forward (popstate)', () => {
    goTo('/counties?p=2');
    renderExplorer();
    expect(rankedNames()).toEqual(PAGE_2);

    act(() => {
      window.history.pushState(null, '', '/counties?p=3');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(rankedNames()).toEqual(PAGE_3);

    act(() => {
      window.history.pushState(null, '', '/counties?view=all');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(rankedNames()).toEqual(NAMES);
  });

  it('follows a Next.js navigation that changes the query without a popstate', () => {
    // e.g. the nav's plain <Link href="/counties"> clicked while on ?p=3: the
    // route does not remount and no popstate fires, only searchParams change.
    goTo('/counties?p=3');
    const { rerender } = renderExplorer();
    expect(rankedNames()).toEqual(PAGE_3);

    goTo('/counties');
    rerender(
      <React.StrictMode>
        <Page client={newClient()} />
      </React.StrictMode>
    );
    expect(rankedNames()).toEqual(PAGE_1);
  });

  it('normalizes to page 1 when search leaves only one page of results', () => {
    goTo('/counties?p=3');
    renderExplorer();
    expect(rankedNames()).toEqual(PAGE_3);

    const search = screen.getByRole('searchbox', { name: 'Search County' });
    fireEvent.change(search, { target: { value: 'Testcounty 0' } }); // 01–09: one page
    expect(rankedNames()).toEqual(NAMES.slice(0, 9));
    expect(listHistoryReplace).toHaveBeenLastCalledWith(null, '', '/counties');
    expect(window.location.search).toBe('');
  });

  it('paints a client-side mount (back from a county page) in its URL state on the first commit', () => {
    // The View All → county → back path. A fix that started every mount on
    // page 1 and corrected it in an effect would still END on the full list,
    // so the final state proves nothing: the first commit is what the browser
    // restores scroll against. Any <tr> added to the ranking table's body
    // after mount is that second, corrective commit.
    goTo('/counties?view=all');
    const container = document.body.appendChild(document.createElement('div'));
    const records: MutationRecord[] = [];
    const observer = new MutationObserver((r) => records.push(...r));
    observer.observe(container, { childList: true, subtree: true });

    render(
      <React.StrictMode>
        <Page client={newClient()} />
      </React.StrictMode>,
      { container }
    );
    records.push(...observer.takeRecords());
    observer.disconnect();

    const tbody = rankingTable(container).querySelector('tbody');
    const lateRows = records.filter(
      (r) => r.target === tbody && Array.from(r.addedNodes).some((n) => n.nodeName === 'TR')
    );
    expect(rankedNames(container)).toEqual(NAMES);
    expect(lateRows).toHaveLength(0);
  });
});

/* ── 2. the defect: what the static prerender contains ──────────────── */

describe('/counties static prerender', () => {
  function prerender(): string {
    mockNavigation.staticPrerender = true;
    // React reports the bail-out through console.error during a string
    // render; it is the mechanism under test, not a failure of the test.
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    try {
      return renderToString(<Page client={newClient()} />);
    } finally {
      spy.mockRestore();
      mockNavigation.staticPrerender = false;
    }
  }

  it('contains the provenance note — the LCP element — not the loading fallback', () => {
    const html = prerender();
    expect(html).toContain(PROVENANCE_NOTE);
    expect(html).not.toContain(LOADING_FALLBACK);
  });

  it('contains the first page of the ranking table', () => {
    const doc = document.createElement('div');
    doc.innerHTML = prerender();
    expect(rankedNames(doc)).toEqual(PAGE_1);
  });
});

/* ── 3. the hazard: hydrating a query the server could not see ──────── */

describe('/counties hydration with a query string', () => {
  /**
   * A static document is rendered once, with no query. A reader who opens
   * /counties?p=2 is served that same document, so the browser's hydration
   * render must produce page 1 too — reading `window.location` during it is a
   * hydration mismatch, and React answers a mismatch by discarding the
   * server's HTML and client-rendering the root, which throws away the very
   * SSR this change is for. Only after hydration may the URL take over.
   */
  async function hydrateAt(url: string) {
    goTo('/counties');
    const html = renderToString(<Page client={newClient()} />);

    goTo(url);
    const container = document.body.appendChild(document.createElement('div'));
    container.innerHTML = html;
    const recoverable: unknown[] = [];
    await act(async () => {
      hydrateRoot(container, <Page client={newClient()} />, {
        onRecoverableError: (err) => recoverable.push(err),
      });
    });
    return { container, recoverable };
  }

  it('hydrates ?p=2 without a mismatch, then shows page 2', async () => {
    const { container, recoverable } = await hydrateAt('/counties?p=2');
    expect(recoverable.map(String)).toEqual([]);
    expect(rankedNames(container)).toEqual(PAGE_2);
  });

  it('hydrates ?view=all without a mismatch, then shows every county', async () => {
    const { container, recoverable } = await hydrateAt('/counties?view=all');
    expect(recoverable.map(String)).toEqual([]);
    expect(rankedNames(container)).toEqual(NAMES);
  });

  it('CONTROL: hydrates the bare URL without a mismatch', async () => {
    const { container, recoverable } = await hydrateAt('/counties');
    expect(recoverable.map(String)).toEqual([]);
    expect(rankedNames(container)).toEqual(PAGE_1);
  });
});
