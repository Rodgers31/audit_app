/**
 * `/counties/compare` must put something the size of the page in the
 * prerendered document, not an 84px spinner.
 *
 * `CompareContent` calls `useSearchParams()`. On a statically prerendered
 * route that opts its subtree out of server rendering, and the nearest
 * `<Suspense>` boundary is what scopes the opt-out — so whatever that
 * boundary wraps is all the prerendered document can contain. The boundary
 * used to wrap `ComparePageInner`, i.e. `PageShell` and every heading with
 * it, behind a fallback that was one spinner in a `p-8` box.
 *
 * Measured consequence: the served document was the nav, an 84px box and the
 * footer. The footer sat at y=84 in a 900px viewport and was shoved to y=988
 * the moment the client rendered the page — one layout shift of 0.269 on a
 * 0.1 budget, and 0.902 at a 390x844 phone viewport (#221 finding #6).
 *
 * These fixtures reproduce the bailout by making `useSearchParams()` suspend,
 * which is what Next does to it during a static prerender, and then assert on
 * what renders. Pre-fix every assertion below fails: nothing but the spinner
 * is reachable.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import ComparePage from '@/app/counties/compare/ComparePageClient';
import { compareCountiesKey } from '@/lib/react-query/useCounties';

/* ── fixtures ───────────────────────────────────────────────────────── */

const COUNTIES = [
  {
    id: '047',
    name: 'Nairobi',
    code: '047',
    population: 4_397_073,
    total_budget: 41_000_000_000,
    total_spent: 25_000_000_000,
    budget_utilization: 61.2,
    development_budget: 12_000_000_000,
    recurrent_budget: 29_000_000_000,
    pending_bills: 3_000_000_000,
    debt: null,
    financial_health_score: 58,
    audit_rating: 'Qualified',
    audit_status: 'completed',
    budget_source: 'cob_cbirr' as const,
  },
  {
    id: '001',
    name: 'Mombasa',
    code: '001',
    population: 1_208_333,
    total_budget: 15_000_000_000,
    total_spent: 9_000_000_000,
    budget_utilization: 60,
    development_budget: 4_000_000_000,
    recurrent_budget: 11_000_000_000,
    pending_bills: 1_000_000_000,
    debt: null,
    financial_health_score: 61,
    audit_rating: 'Qualified',
    audit_status: 'completed',
    budget_source: 'cob_cbirr' as const,
  },
];

/**
 * `useSearchParams` as Next.js behaves during a static prerender: it never
 * resolves, so React falls back to the nearest boundary. A plain jest mock
 * returning a URLSearchParams would render the happy path and pin nothing —
 * the defect is precisely about what happens when this hook is unavailable.
 */
const NEVER = new Promise<never>(() => {});
const suspendingSearchParams = () => {
  throw NEVER;
};

jest.mock('next/navigation', () => ({
  __esModule: true,
  usePathname: () => '/counties/compare',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => suspendingSearchParams(),
}));

/** The list `app/counties/compare/page.tsx` prefetches, already hydrated. */
function renderWithHydratedCounties() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(compareCountiesKey(), COUNTIES);
  return render(
    <QueryClientProvider client={client}>
      <ComparePage />
    </QueryClientProvider>
  );
}

/* ── what the document contains while the URL subtree is unavailable ── */

describe('/counties/compare — the prerendered document, with useSearchParams suspended', () => {
  it('renders the page shell, which does not read the URL and has no business being deferred', () => {
    renderWithHydratedCounties();

    expect(screen.getByText('Compare counties')).toBeInTheDocument();
    expect(
      screen.getByText(/Line up two or three counties side-by-side/i)
    ).toBeInTheDocument();
  });

  it('reserves the picker rather than collapsing it to a spinner', () => {
    renderWithHydratedCounties();

    expect(screen.getByText(/County 1/)).toBeInTheDocument();
    expect(screen.getByText(/County 2/)).toBeInTheDocument();
  });

  it('reserves the empty state the page opens in — the tallest block on a cold load', () => {
    renderWithHydratedCounties();

    expect(screen.getByText('Pick at least two counties to compare')).toBeInTheDocument();
  });

  it('reserves the legend that sits under the comparison', () => {
    renderWithHydratedCounties();

    expect(screen.getByText('Reading this table')).toBeInTheDocument();
  });

  it('renders the provenance note off the hydrated list, so its height is the real one', () => {
    renderWithHydratedCounties();

    // Not a placeholder: this is `ModelledDataNote` reading the same
    // prefetched payload the content will read, which is why the fallback
    // and the content agree on this block's height at any viewport.
    expect(
      screen.getByText(/County budget figures are the Controller of Budget/i)
    ).toBeInTheDocument();
  });

  it('publishes no figure in the reserved picker — reserved space is not data', () => {
    renderWithHydratedCounties();

    // The control-shaped box that stands in for the two selects must be
    // empty. A `0`, a `—` or a county name there would read as a choice the
    // page had already made.
    const boxes = screen.getAllByTestId('compare-picker-placeholder');
    expect(boxes.length).toBe(2);
    boxes.forEach((b) => {
      expect(b.textContent?.replace(/ /g, '').trim()).toBe('');
    });
  });
});
