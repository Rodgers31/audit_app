/**
 * The freshness badge must not claim "Up to date" when nothing was measured.
 *
 * `DataFreshnessBadge` took the worst status among the matched sources with
 * `matched.reduce(..., 'fresh')`. When `/data/freshness` has not answered
 * (loading, failed, or during the server prerender, where useQuery never
 * fetches) `matched` is empty, the reduce returns its seed, and the banner
 * rendered "Up to date" in emerald — a freshness verdict nobody measured. It
 * was baked into the static `/budget` HTML.
 *
 * Absence must render as absence: a neutral "checking" state while the
 * request is in flight (and in the prerender), "Freshness unknown" once it
 * has failed or returned nothing for these sources. A measured 'fresh' still
 * says "Up to date".
 */
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { renderToString } from 'react-dom/server';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';

const get = jest.fn();
jest.mock('@/lib/api/axios', () => ({
  apiClient: { get: (...args: unknown[]) => get(...args) },
}));

const RECENT = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);

const FRESH_RESPONSE = {
  sources: [
    {
      source: 'COB',
      label: 'Controller of Budget',
      last_updated: RECENT,
      covers_through: null,
      update_frequency: 'Quarterly',
      status: 'fresh',
    },
  ],
};

const VARIANTS = ['inline', 'banner'] as const;

function client() {
  return new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } });
}

function wrap(qc: QueryClient, ui: React.ReactElement) {
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

/** Text of the markup with tags stripped — what a reader of the HTML sees. */
function visibleText(html: string) {
  return html.replace(/<[^>]*>/g, ' ');
}

beforeEach(() => {
  get.mockReset();
});

describe.each(VARIANTS)('DataFreshnessBadge (%s) with no measurement', (variant) => {
  it('does not say "Up to date" while the request is in flight', () => {
    get.mockReturnValue(new Promise(() => {}));
    const { container } = render(wrap(client(), <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(screen.queryByText(/up to date/i)).not.toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
  });

  it('does not say "Up to date" when the request failed', async () => {
    get.mockRejectedValue(new Error('503'));
    const qc = client();
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    // useDataFreshness retries once (~1s back-off) before settling on error.
    await waitFor(() => expect(qc.getQueryState(['data-freshness'])?.status).toBe('error'), {
      timeout: 4000,
    });
    await act(async () => {}); // commit the error render

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    if (variant === 'banner') {
      expect(screen.getByText(/freshness unknown/i)).toBeInTheDocument();
    }
  }, 8000);

  it('does not say "Up to date" when the response has no entry for the source', () => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources: [] });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    if (variant === 'banner') {
      expect(screen.getByText(/freshness unknown/i)).toBeInTheDocument();
    }
  });

  it('does not treat a status it does not recognise as fresh', () => {
    const qc = client();
    qc.setQueryData(['data-freshness'], {
      sources: [{ ...FRESH_RESPONSE.sources[0], status: 'unknown' }],
    });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
  });

  it('server-renders no "Up to date" when there is no data', () => {
    const html = renderToString(wrap(client(), <DataFreshnessBadge sources='COB/Treasury' variant={variant} />));

    expect(visibleText(html)).not.toMatch(/up to date/i);
    expect(html).not.toMatch(/up to date/i); // nor in aria-label / title
    expect(html).not.toMatch(/emerald/);
    expect(get).not.toHaveBeenCalled();
  });
});

describe.each(VARIANTS)('DataFreshnessBadge (%s) with a measured fresh source', (variant) => {
  it('still says "Up to date"', () => {
    const qc = client();
    qc.setQueryData(['data-freshness'], FRESH_RESPONSE);
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(container.innerHTML).toMatch(/up to date/i);
    expect(container.innerHTML).toMatch(/bg-emerald-400/);
    expect(get).not.toHaveBeenCalled();
  });
});

describe('DataFreshnessBadge banner keeps one shape across states (no CLS)', () => {
  /**
   * The layout skeleton: every element's tag and layout classes, in order.
   * An icon counts by its box (width × height), not by the paths it draws —
   * the clock and refresh glyphs differ inside the same 18px square.
   */
  function skeleton(el: Element): string[] {
    return Array.from(el.querySelectorAll('*'))
      .filter((n) => !n.parentElement?.closest('svg'))
      .map((n) =>
        n.tagName === 'svg'
          ? `svg:${n.getAttribute('width')}x${n.getAttribute('height')}`
          : `${n.tagName}:${(n.getAttribute('class') || '')
              .split(/\s+/)
              .filter((c) => /^(flex|items|gap|rounded|border$|p-|text-(xs|sm)|font|mt-|w-|h-|min-w|inline-block)/.test(c))
              .join(' ')}`,
      );
  }

  it('renders the same element structure pending and measured', () => {
    get.mockReturnValue(new Promise(() => {}));
    const pending = render(wrap(client(), <DataFreshnessBadge sources='COB' variant='banner' />));
    const pendingShape = skeleton(pending.container);
    pending.unmount();

    const qc = client();
    // Measured, but with no date: the date spans are the only optional parts.
    qc.setQueryData(['data-freshness'], {
      sources: [{ ...FRESH_RESPONSE.sources[0], last_updated: null }],
    });
    const measured = render(wrap(qc, <DataFreshnessBadge sources='COB' variant='banner' />));

    expect(skeleton(measured.container)).toEqual(pendingShape);
  });
});
