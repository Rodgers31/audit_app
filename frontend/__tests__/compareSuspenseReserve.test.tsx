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
  { id: '047', name: 'Nairobi', budget_source: 'cob_cbirr' },
  { id: '001', name: 'Mombasa', budget_source: 'cob_cbirr' },
  { id: '022', name: 'Kiambu', budget_source: 'cra_model' },
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

    expect(screen.getByRole('heading', { name: 'Compare counties', level: 1 })).toBeInTheDocument();
    expect(
      screen.getByText(/Line up two or three counties side-by-side/i)
    ).toBeInTheDocument();
  });

  it('reserves the picker rather than collapsing it to a spinner', () => {
    renderWithHydratedCounties();

    expect(screen.getByText(/County 1/)).toBeInTheDocument();
    expect(screen.getByText(/County 2/)).toBeInTheDocument();
    expect(screen.getByText('Nairobi vs Kiambu')).toBeInTheDocument();
  });

  it('reserves the empty state the page opens in — the tallest block on a cold load', () => {
    renderWithHydratedCounties();

    expect(screen.getByText('Pick at least two counties to compare')).toBeInTheDocument();
  });

  it('waits for a comparison before showing provenance and the table legend', () => {
    renderWithHydratedCounties();

    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.queryByText('Reading this table')).not.toBeInTheDocument();
  });

  it('reserves the real empty fields without exposing inactive controls', () => {
    const { container } = renderWithHydratedCounties();

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const fields = Array.from(container.querySelectorAll<HTMLInputElement>('[data-compare-pickers] input'));
    expect(fields).toHaveLength(2);
    fields.forEach((field) => {
      expect(field).toBeDisabled();
      expect(field).toHaveValue('');
    });
  });
});
