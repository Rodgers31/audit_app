/**
 * A column header must keep reversing the sort, however React schedules the
 * state update behind it.
 *
 * `handleSort` used to call `setSortDir` from *inside* the `setSortField`
 * updater:
 *
 *   setSortField((prev) => {
 *     if (prev === field) {
 *       setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));   // ← side effect
 *       return prev;
 *     }
 *     ...
 *   });
 *
 * React treats a state updater as a pure function and reserves the right to
 * call it more than once — which StrictMode does deliberately, in development,
 * to surface exactly this. The nested toggle therefore ran twice per click and
 * cancelled itself: clicking POPULATION a second time left the arrow on ↓ and
 * the rows in the order they were already in, however many times you clicked.
 *
 * Production builds do not double-invoke, so the column sorted correctly for
 * users. The cost was paid in development, where the toggle was dead and
 * untestable — and the impurity was one scheduling change away from shipping.
 *
 * These fixtures render the County Explorer inside `<React.StrictMode>`, which
 * is what `next dev` does (Next 15, `reactStrictMode` unset = on). Without the
 * StrictMode wrapper the pre-fix code passes, so the wrapper is the fixture.
 *
 * The POPULATION column is the one that mattered: the sidebar's SORT BY select
 * offers `population-desc` and no ascending twin, so "smallest county first"
 * was reachable only through this header.
 */
import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import type { County } from '@/types';

/* ── fixtures ───────────────────────────────────────────────────────── */

/**
 * Three counties whose population order, budget order and reverse-population
 * order are all different, so a stale table cannot be mistaken for a sorted
 * one. 2019 KNBS census figures.
 */
const county = (over: Partial<County>): County =>
  ({
    id: 'x',
    name: 'X',
    code: 'x',
    population: 100_000,
    budget: 1e9,
    totalBudget: 1e9,
    debt: 1e8,
    totalDebt: 1e8,
    budgetUtilization: 70,
    financial_health_score: 50,
    audit_rating: '',
    auditStatus: 'pending',
    ...over,
  }) as County;

const NAIROBI = county({
  id: '047',
  name: 'Nairobi',
  code: '047',
  population: 4_397_073, // largest population
  budget: 12e9,
  totalBudget: 12e9, // middle budget
});
const TURKANA = county({
  id: '023',
  name: 'Turkana',
  code: '023',
  population: 926_976, // middle population
  budget: 40e9,
  totalBudget: 40e9, // largest budget
});
const LAMU = county({
  id: '005',
  name: 'Lamu',
  code: '005',
  population: 143_920, // smallest population
  budget: 3e9,
  totalBudget: 3e9, // smallest budget
});

const COUNTIES = [NAIROBI, TURKANA, LAMU];

/** The page opens on budget-desc, which is none of the population orders. */
const BY_BUDGET_DESC = ['Turkana', 'Nairobi', 'Lamu'];
const BY_POPULATION_DESC = ['Nairobi', 'Turkana', 'Lamu'];
const BY_POPULATION_ASC = ['Lamu', 'Turkana', 'Nairobi'];

/* ── harness ────────────────────────────────────────────────────────── */

jest.mock('next/navigation', () => ({
  usePathname: () => '/counties',
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

jest.mock('@/lib/react-query', () => ({
  useCounties: () => ({
    data: (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__,
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
}));

// eslint-disable-next-line import/first
import CountiesPageClient from '@/app/counties/CountiesPageClient';

function renderExplorer(counties: County[]) {
  (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = counties;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <React.StrictMode>
      <QueryClientProvider client={qc}>
        <CountiesPageClient />
      </QueryClientProvider>
    </React.StrictMode>
  );
}

/** The rankings table — the one carrying the sortable POPULATION header. */
function rankingTable(): HTMLElement {
  const table = screen
    .getAllByRole('table')
    .find((t) => within(t).queryByRole('columnheader', { name: /population/i }));
  if (!table) throw new Error('ranking table not rendered');
  return table;
}

/** County names in render order. The name cell leads with a 🏛️ badge. */
function rankedNames(): string[] {
  return within(rankingTable())
    .getAllByRole('row')
    .slice(1) // drop the header row
    .map((tr) => {
      const cells = within(tr).getAllByRole('cell');
      return (cells[1].textContent ?? '').replace('\u{1F3DB}\u{FE0F}', '').trim();
    });
}

function header(name: RegExp): HTMLElement {
  return within(rankingTable()).getByRole('columnheader', { name });
}

/** What the header's arrow claims the direction is: ↑ asc, ↓ desc, none. */
function arrow(name: RegExp): 'asc' | 'desc' | 'none' {
  const text = header(name).textContent ?? '';
  if (text.includes('↑')) return 'asc';
  if (text.includes('↓')) return 'desc';
  return 'none';
}

/* ── the toggle ─────────────────────────────────────────────────────── */

describe('County Explorer — column header sort toggle under StrictMode', () => {
  it('reverses the population sort on every click, not just the first', () => {
    renderExplorer(COUNTIES);
    expect(rankedNames()).toEqual(BY_BUDGET_DESC);

    // First click takes over the column: largest population first.
    fireEvent.click(header(/population/i));
    expect(rankedNames()).toEqual(BY_POPULATION_DESC);
    expect(arrow(/population/i)).toBe('desc');

    // Second click must flip it. The nested `setSortDir` updater ran twice
    // here under StrictMode — desc → asc → desc — so the table never moved.
    fireEvent.click(header(/population/i));
    expect(rankedNames()).toEqual(BY_POPULATION_ASC);
    expect(arrow(/population/i)).toBe('asc');

    // And back, so the toggle is a toggle rather than a one-way trip.
    fireEvent.click(header(/population/i));
    expect(rankedNames()).toEqual(BY_POPULATION_DESC);
    expect(arrow(/population/i)).toBe('desc');
  });

  it('gives a newly-picked column its own default direction', () => {
    renderExplorer(COUNTIES);

    // A numeric column opens high → low: the interesting end first.
    fireEvent.click(header(/population/i));
    expect(arrow(/population/i)).toBe('desc');
    expect(rankedNames()).toEqual(BY_POPULATION_DESC);

    // The name column opens A → Z instead, and taking it over must clear the
    // previous column's arrow rather than leave two columns claiming the sort.
    fireEvent.click(header(/county/i));
    expect(arrow(/county/i)).toBe('asc');
    expect(arrow(/population/i)).toBe('none');
    expect(rankedNames()).toEqual(['Lamu', 'Nairobi', 'Turkana']);

    // Coming back to population resets it to desc — not to whatever direction
    // it was left in, and not to the name column's asc.
    fireEvent.click(header(/population/i));
    expect(arrow(/population/i)).toBe('desc');
    expect(rankedNames()).toEqual(BY_POPULATION_DESC);
  });
});
