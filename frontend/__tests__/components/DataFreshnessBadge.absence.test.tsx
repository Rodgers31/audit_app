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
  return new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });
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

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not say "Up to date" when the request failed', async () => {
    get.mockRejectedValue(new Error('503'));
    const qc = client();
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    // The query settles on the error without repeating the Axios retry budget.
    await waitFor(() => expect(qc.getQueryState(['data-freshness'])?.status).toBe('error'), {
      timeout: 4000,
    });
    await act(async () => {}); // commit the error render

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    expect(container).toBeEmptyDOMElement();
  }, 8000);

  it('does not say "Up to date" when the response has no entry for the source', () => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources: [] });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not treat a status it does not recognise as fresh', () => {
    const qc = client();
    qc.setQueryData(['data-freshness'], {
      sources: [{ ...FRESH_RESPONSE.sources[0], status: 'unknown' }],
    });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant={variant} />));

    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container.innerHTML).not.toMatch(/emerald/);
    expect(container).toBeEmptyDOMElement();
  });

  it('server-renders no "Up to date" when there is no data', () => {
    const html = renderToString(wrap(client(), <DataFreshnessBadge sources='COB/Treasury' variant={variant} />));

    expect(visibleText(html)).not.toMatch(/up to date/i);
    expect(visibleText(html).trim()).toBe('');
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
    expect(container).toHaveTextContent('Controller of Budget');
    const message = screen.getByText('Up to date').closest('p');
    expect(message).toHaveClass('text-neutral-muted', variant === 'banner' ? 'text-sm' : 'text-xs');
    if (variant === 'banner') expect(message).toHaveClass('audit-panel');
    expect(get).not.toHaveBeenCalled();
  });
});

it('reports the source check without implying a publication date or freshness', () => {
  const qc = client();
  qc.setQueryData(['data-freshness'], {
    sources: [{ ...FRESH_RESPONSE.sources[0], status: 'unknown', last_updated: null, last_checked: RECENT }],
  });
  const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB' variant='banner' />));
  expect(container).toHaveTextContent(/Checked .* · Controller of Budget/);
  expect(container).not.toHaveTextContent(/Up to date|Data as of/);
});

describe.each(VARIANTS)('publisher coverage (%s)', (variant) => {
  it.each([
    ['missing Treasury', [FRESH_RESPONSE.sources[0]]],
    ['duplicate COB', [FRESH_RESPONSE.sources[0], FRESH_RESPONSE.sources[0]]],
  ])('withholds a freshness verdict for %s', (_, sources) => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB/Treasury' variant={variant} />));
    expect(container.innerHTML).not.toMatch(/up to date/i);
    expect(container).toBeEmptyDOMElement();
  });

  it.each(['fresh', 'stale', 'outdated'])('uses the worst measured status with complete coverage: %s', (status) => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources: [FRESH_RESPONSE.sources[0], {
      ...FRESH_RESPONSE.sources[0], source: 'Treasury', label: 'National Treasury', status,
    }] });
    const { container } = render(wrap(qc, <DataFreshnessBadge sources='COB/Treasury' variant={variant} />));
    expect(container.innerHTML).toMatch(status === 'fresh' ? /up to date/i : status === 'stale' ? /may be stale/i : /out of date/i);
  });
});

describe('malformed freshness evidence', () => {
  it.each(['T00:30:00+14:00', 'T23:30:00-02:00'])('accepts and displays a publisher-local date across a UTC day boundary (%s)', (time) => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources: [{ ...FRESH_RESPONSE.sources[0], last_updated: `${RECENT}${time}` }] });
    const html = renderToString(wrap(qc, <DataFreshnessBadge sources='COB' variant='banner' />));
    expect(html).toMatch(/Up to date/);
    expect(html).not.toMatch(/Freshness unknown/);
    const expectedDate = new Date(`${RECENT}T00:00:00Z`).toLocaleDateString('en-GB', {
      timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
    });
    expect(html).toContain(expectedDate);
  });
  it.each([null, 'not-a-date', '9999-01-01', '2026-02-31', true, {}, 0])('withholds fresh for invalid date %j', (last_updated) => {
    const qc = client();
    qc.setQueryData(['data-freshness'], { sources: [{ ...FRESH_RESPONSE.sources[0], last_updated }] });
    const html = renderToString(wrap(qc, <DataFreshnessBadge sources='COB' variant='banner' />));
    expect(html).not.toMatch(/Up to date|Invalid Date|NaN|emerald/);
    expect(visibleText(html).trim()).toBe('');
  });
  it.each([{}, { sources: null }, { sources: {} }, { sources: [null] }])('renders unknown for malformed payload %j', (data) => {
    const qc = client();
    qc.setQueryData(['data-freshness'], data);
    const html = renderToString(wrap(qc, <DataFreshnessBadge sources='COB' variant='banner' />));
    expect(visibleText(html).trim()).toBe('');
  });
});
