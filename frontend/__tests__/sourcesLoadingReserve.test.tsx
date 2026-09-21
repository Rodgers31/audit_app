/**
 * `/sources` must reserve the space its two fetches will fill, and must not
 * publish a zero while it waits.
 *
 * Two defects, one render path:
 *
 * 1. **A zero standing in for absence.** The hero strip read
 *    `data?.total_documents || 0` and `distinctAgencyCount ?? sources.length`,
 *    so the served document said "Documents indexed 0 / Publishing agencies 0"
 *    until the fetch landed, and then said 2,330 / 11. Those are the same two
 *    slots. Nothing distinguished a zero nobody had counted from a counted
 *    zero — and the page has a genuine empty state for the counted one.
 *    Verified in the prerendered HTML, scripts stripped:
 *
 *        $ python3 probe.py http://localhost:3101/sources
 *        ... Documents indexed 0 Publishing agencies 0 ...
 *
 * 2. **Two blocks inserted above the fold.** The data-health grid rendered
 *    nothing at all until `/provenance/health` answered, and the manifest
 *    rendered an 84px spinner where 1,657px of cards were going. Each landed
 *    above the fold and shoved what was below it out of the viewport:
 *    0.197 + 0.177 = 0.374 measured on a cold 1440x900 load (#221 finding #6).
 *
 * This route keeps fetching on the client on purpose — it is the freshness
 * page, and `fmtRelativeDate`/`freshnessColor` are computed from `Date.now()`
 * at render, so baking them into an hour-old ISR document would ship a stale
 * answer to the one question the page exists to answer. So the fix is
 * reserved space, and these fixtures pin it.
 */
import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import SourcesPage from '@/app/sources/page';

/* ── fixtures ───────────────────────────────────────────────────────── */

const SUMMARY = {
  total_documents: 2330,
  sources: [
    {
      publisher: 'National Treasury Kenya',
      short: 'NT',
      role: 'Manages national finances',
      website: 'https://treasury.go.ke',
      document_count: 1603,
      last_fetched: '2026-06-01T00:00:00Z',
      last_seen_at: '2026-06-01T00:00:00Z',
      doc_types: { budget: 1603 },
    },
  ],
};

/** The manifest really is empty — a counted zero, not an uncounted one. */
const EMPTY_SUMMARY = { total_documents: 0, sources: [] };

const HEALTH = {
  tables: [
    {
      table: 'counties',
      label: 'Counties',
      row_count: 47,
      source: 'KNBS Census 2019',
      status: 'healthy',
      age_days: 3,
      stale_after_days: 400,
    },
  ],
};

const get = jest.fn();

jest.mock('@/lib/api/axios', () => ({
  __esModule: true,
  default: { get: (...a: unknown[]) => get(...a) },
}));

jest.mock('next/navigation', () => ({
  __esModule: true,
  usePathname: () => '/sources',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

/** Neither endpoint ever answers — the state a cold visitor spends ~1.5s in. */
const pending = () => new Promise(() => {});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SourcesPage />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
});

/** The figure rendered next to a given strip label, or null if there is none. */
function figureUnder(label: string): string | null {
  const labelEl = screen.getByText(label);
  const slot = labelEl.parentElement as HTMLElement;
  const figure = slot.querySelector('div.text-2xl');
  return figure ? (figure.textContent ?? '') : null;
}

/* ── 1. no zero for absence ─────────────────────────────────────────── */

describe('/sources hero strip — a figure nobody has counted yet', () => {
  it('shows no number for "Documents indexed" while the manifest is in flight', () => {
    get.mockImplementation(() => pending());

    renderPage();

    expect(figureUnder('Documents indexed')).toBeNull();
    expect(screen.getByLabelText('Documents indexed — still loading')).toBeInTheDocument();
  });

  it('shows no number for "Publishing agencies" while the manifest is in flight', () => {
    get.mockImplementation(() => pending());

    renderPage();

    expect(figureUnder('Publishing agencies')).toBeNull();
    expect(screen.getByLabelText('Publishing agencies — still loading')).toBeInTheDocument();
  });

  it('still prints a counted zero — an empty manifest is an answer', async () => {
    get.mockImplementation((url: string) =>
      url.includes('/sources/summary')
        ? Promise.resolve({ data: EMPTY_SUMMARY })
        : Promise.resolve({ data: { tables: [] } })
    );

    renderPage();

    // The distinction the fix turns on: absence renders nothing, a measured
    // zero renders 0. Suppressing both would be the same defect inverted.
    await waitFor(() => expect(figureUnder('Documents indexed')).toBe('0'));
    expect(screen.getByText('No source documents indexed yet')).toBeInTheDocument();
  });

  it('prints the real figures once they arrive', async () => {
    get.mockImplementation((url: string) =>
      url.includes('/sources/summary')
        ? Promise.resolve({ data: SUMMARY })
        : Promise.resolve({ data: HEALTH })
    );

    renderPage();

    await waitFor(() => expect(figureUnder('Documents indexed')).toBe('2,330'));
    expect(figureUnder('Publishing agencies')).toBe('1');
  });
});

/* ── 2. reserved space for the two inserted blocks ──────────────────── */

describe('/sources — space reserved for what the fetches will fill', () => {
  it('renders the data-health block while /provenance/health is in flight', () => {
    get.mockImplementation(() => pending());

    renderPage();

    // Pre-fix this heading did not exist until the fetch resolved, and the
    // whole block appeared out of nothing above the fold.
    expect(screen.getByText('Data health')).toBeInTheDocument();
    expect(screen.getByLabelText('Data health — still loading')).toBeInTheDocument();
  });

  it('reserves fewer health cards than the endpoint returns, never more', () => {
    get.mockImplementation(() => pending());

    renderPage();

    const grid = screen.getByLabelText('Data health — still loading');
    const cards = grid.querySelectorAll('div[aria-hidden="true"]');
    // 9 at every breakpoint plus 3 that only appear at `lg`. At `lg` that is
    // 4 rows of 3, which is what the 10 real cards also make; below `lg` the
    // extra 3 are hidden and 9 is 5 rows, which 10 real cards also make.
    // Under-reserving pushes what follows off-screen and costs nothing;
    // over-reserving drags visible content upward, which is a shift.
    expect(cards.length).toBe(12);
    expect(grid.querySelectorAll('div.hidden.lg\\:block').length).toBe(3);
  });

  it('reserves the manifest as cards, not as a spinner in a box', () => {
    get.mockImplementation(() => pending());

    renderPage();

    const grid = screen.getByLabelText('Loading source manifest');
    expect(grid.querySelectorAll('div[aria-hidden="true"]').length).toBe(6);
  });

  it('publishes nothing inside the reserved cards', () => {
    get.mockImplementation(() => pending());

    renderPage();

    const cards = Array.from(
      screen.getByLabelText('Data health — still loading').querySelectorAll('div[aria-hidden="true"]')
    ).concat(
      Array.from(
        screen.getByLabelText('Loading source manifest').querySelectorAll('div[aria-hidden="true"]')
      )
    );
    // Count first. `forEach` over an empty list asserts nothing, and pre-fix
    // there are no placeholder cards at all — the guard would have gone green
    // against the very code it is meant to catch.
    expect(cards.length).toBe(18);
    cards.forEach((c) => expect(c.textContent).toBe(''));
  });

  it('GUARD: the health block collapses rather than showing a skeleton forever when the endpoint answers with nothing', async () => {
    get.mockImplementation((url: string) =>
      url.includes('/sources/summary')
        ? Promise.resolve({ data: SUMMARY })
        : Promise.resolve({ data: { tables: [] } })
    );

    renderPage();

    // A placeholder that outlives its fetch is worse than the shift it
    // prevents: it is a page reporting "still working" forever.
    await waitFor(() =>
      expect(screen.queryByLabelText('Data health — still loading')).not.toBeInTheDocument()
    );
    expect(screen.queryByText('Data health')).not.toBeInTheDocument();
  });
});
