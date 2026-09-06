/**
 * A county nobody has counted must not be published — or ranked — as empty.
 *
 * `/api/v1/counties` sent `population: 0` for a county with no KNBS census
 * row. That payload is the County Explorer table, the map and the compare
 * page, and every one of them read the zero as a measurement:
 *
 *   · the ranking table printed "0" beside the county's name;
 *   · "Population (Low → High)" put it FIRST — the least populous county in
 *     Kenya, ahead of Lamu's 143,920;
 *   · the compare page divided a budget by it for a per-capita figure.
 *
 * The endpoint now sends `null`. These fixtures pin what the UI does with it:
 * an em dash where a figure would go, and last place in the ranking whichever
 * way the column is sorted — the same rule `compareByPublishedFigure` already
 * enforces for budget and debt.
 *
 * All 47 counties carry a census row today, so none of this is reachable in
 * production. That is the point: the day an extractor drops one, the site must
 * say "we don't know" rather than "nobody lives there".
 */
import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { transformCountyData } from '@/lib/api/counties';
import { compareByPublishedFigure, countyPopulation } from '@/lib/countyFigures';
import type { County } from '@/types';

/* ── fixtures ───────────────────────────────────────────────────────── */

const NAIROBI_CENSUS_2019 = 4_397_073;
/** The smallest county KNBS counted in 2019 — the floor a real figure can hit. */
const LAMU_CENSUS_2019 = 143_920;

const county = (over: Partial<County>): County =>
  ({
    id: 'x',
    name: 'X',
    code: 'x',
    population: LAMU_CENSUS_2019,
    budget_2025: 9_542_030_000,
    budget: 9_542_030_000,
    totalBudget: 9_542_030_000,
    financial_health_score: 50,
    audit_rating: '',
    auditStatus: 'pending',
    ...over,
  }) as County;

const NAIROBI = county({
  id: '001',
  name: 'Nairobi',
  code: '001',
  population: NAIROBI_CENSUS_2019,
});
const LAMU = county({ id: '005', name: 'Lamu', code: '005', population: LAMU_CENSUS_2019 });
/** The county under test: the API published no figure for it. */
const UNCOUNTED = county({ id: '002', name: 'Kwale', code: '002', population: null });

/* ── the adapter ────────────────────────────────────────────────────── */

describe('transformCountyData — an uncounted county stays uncounted', () => {
  it('carries a null population through instead of substituting a number', () => {
    const c = transformCountyData({
      id: '002',
      name: 'Kwale',
      population: null,
      budget_2025: 9_542_030_000,
      audit_rating: '',
      audit_status: 'pending',
    } as never);
    expect(c.population).toBeNull();
    expect(c.population).not.toBe(0);
    expect(Number.isNaN(c.population as number)).toBe(false);
  });

  it('still carries a published census figure through unchanged', () => {
    const c = transformCountyData({
      id: '001',
      name: 'Nairobi',
      population: NAIROBI_CENSUS_2019,
      budget_2025: 9_542_030_000,
      audit_rating: '',
      audit_status: 'pending',
    } as never);
    expect(c.population).toBe(NAIROBI_CENSUS_2019);
  });
});

/* ── the ranked figure ──────────────────────────────────────────────── */

describe('countyPopulation', () => {
  it('withholds when the API published no census figure', () => {
    expect(countyPopulation(UNCOUNTED)).toBeUndefined();
  });

  it('reports the figure when there is one', () => {
    expect(countyPopulation(NAIROBI)).toBe(NAIROBI_CENSUS_2019);
  });
});

describe('ranking by population — absence is not a small number', () => {
  const order = (dir: 'asc' | 'desc') =>
    [NAIROBI, UNCOUNTED, LAMU]
      .slice()
      .sort((a, b) => compareByPublishedFigure(a, b, countyPopulation, dir))
      .map((c) => c.name);

  it('sinks the uncounted county to the bottom of High → Low', () => {
    expect(order('desc')).toEqual(['Nairobi', 'Lamu', 'Kwale']);
  });

  it('sinks it to the bottom of Low → High too, rather than calling it the smallest', () => {
    // The defect: `a.population - b.population` coerced the absent figure to
    // 0, which ranked a county nobody has counted below Lamu's 143,920.
    expect(order('asc')).toEqual(['Lamu', 'Nairobi', 'Kwale']);
  });
});

/* ── the County Explorer ────────────────────────────────────────────── */

jest.mock('next/navigation', () => ({
  usePathname: () => '/counties',
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

jest.mock('@/lib/react-query', () => ({
  useCounties: () => ({
    // eslint-disable-next-line @typescript-eslint/no-var-requires, global-require
    data: (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__,
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
  // The factory replaces the WHOLE module, so every hook the explorer calls
  // has to appear here — a missing one is `undefined` at the call site, not a
  // pass-through. This branch made the explorer resolve its fiscal year from
  // the API instead of the clock, which added this call; the test was written
  // on a branch where the hook did not exist yet, so only the merge has both.
  // Same defect, same fix, as countySortControls.test.tsx one commit earlier.
  //
  // No year list: resolveExplorerYear yields undefined, the explorer sends no
  // fiscal_year, and these tests stay about population.
  useCountyFiscalYears: () => ({ data: undefined, isLoading: false, error: null }),
}));

// eslint-disable-next-line import/first
import CountiesPageClient from '@/app/counties/CountiesPageClient';

/** The ranking table's data rows, in render order, as [name, population]. */
function rankingRows(): Array<[string, string]> {
  const table = document.querySelector('table');
  if (!table) throw new Error('ranking table not rendered');
  return within(table)
    .getAllByRole('row')
    .slice(1) // drop the header row
    .map((tr) => {
      const cells = within(tr).getAllByRole('cell');
      // The name cell leads with a 🏛️ badge; the county's name is what follows.
      const name = (cells[1].textContent ?? '').replace('\u{1F3DB}\u{FE0F}', '').trim();
      return [name, (cells[2].textContent ?? '').trim()];
    });
}

function renderExplorer(counties: County[]) {
  (global as unknown as { __COUNTIES__: County[] }).__COUNTIES__ = counties;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CountiesPageClient />
    </QueryClientProvider>
  );
}

describe('County Explorer — the ranking table', () => {
  it('shows an em dash for a county with no census figure, never a 0', () => {
    renderExplorer([NAIROBI, UNCOUNTED, LAMU]);

    const rows = new Map(rankingRows());
    expect(rows.get('Kwale')).toBe('—');
    expect(rows.get('Kwale')).not.toBe('0');
    expect(rows.get('Kwale')).not.toBe('null');
    // The counted counties are untouched.
    expect(rows.get('Nairobi')).toBe('4.4M');
    expect(rows.get('Lamu')).toBe('144K');
  });

  it('does not rank the uncounted county as the smallest under Population sort', () => {
    renderExplorer([NAIROBI, UNCOUNTED, LAMU]);

    // First click on the Population header sorts High → Low.
    const header = screen.getByRole('columnheader', { name: /population/i });
    fireEvent.click(header);
    expect(rankingRows().map(([name]) => name)).toEqual(['Nairobi', 'Lamu', 'Kwale']);

    // Second click flips to Low → High. The absent county must stay last:
    // flipping the sign of a comparator that scored it 0 floated it to the
    // top, where it read as the least populous county in the country.
    fireEvent.click(header);
    expect(rankingRows().map(([name]) => name)).toEqual(['Lamu', 'Nairobi', 'Kwale']);
  });
});
