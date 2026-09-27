/** Independent regression probes for source-shaped JSON without a usable locator. */
import RevenueMix, { type RevSource } from '@/components/budget/RevenueMix';
import { render, screen, within } from '@testing-library/react';
import React from 'react';

jest.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: () => ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
      <div {...props}>{children}</div>
    ),
  }),
}));

const ABSENT = 'No verifiable source version was recorded for this PAYE row.';

function renderSource(source: unknown, sourceAbsent?: string) {
  // This is the runtime JSON boundary. Deliberately exercise shapes that the
  // TypeScript contract cannot prevent a legacy API/database from returning.
  const row = JSON.parse(JSON.stringify({
    revenue_type: 'PAYE', amount: 0, basis: 'published',
    source, source_absent_reason: sourceAbsent,
  })) as RevSource;
  render(<RevenueMix revenueBySource={[{
    fiscal_year: 'FY 2025/26', sources: [row, {
      revenue_type: 'VAT', amount: 12, basis: 'published',
    }],
  }]} />);
  const card = screen.getByText('PAYE').closest('[data-revenue-card]');
  if (!(card instanceof HTMLElement)) throw new Error('Expected a PAYE card');
  return within(card);
}

describe('RevenueMix source URL publication boundary', () => {
  it.each([
    ['absent', undefined],
    ['null', null],
    ['empty object', {}],
    ['metadata only', { retrieved_at: '2026-09-27T12:00:00Z' }],
    ['blank URL', { url: '   ' }],
    ['relative URL', { url: '/annual-performance' }],
    ['malformed URL', { url: 'https://[bad' }],
    ['script URL', { data_url: 'javascript:alert(1)' }],
    ['non-web URL', { url: 'mailto:press@kra.go.ke' }],
    ['numeric URL', { data_url: 17 }],
    ['list URL', { data_url: ['https://www.kra.go.ke/performance.pdf'] }],
  ])('shows the explicit absence reason for %s', (_name, source) => {
    const card = renderSource(source, ABSENT);
    expect(card.queryByText('Source version')).not.toBeInTheDocument();
    expect(card.getByText(ABSENT)).toBeInTheDocument();
    expect(card.getByText('KES 0B')).toBeInTheDocument();
  });

  it('shows a default absence explanation for a legacy source with no URL or reason', () => {
    const card = renderSource({ period: 'FY 2025/26' });
    expect(card.queryByText('Source version')).not.toBeInTheDocument();
    expect(card.getByText(/source.*unavailable/i)).toBeInTheDocument();
  });

  it.each([
    ['publisher URL', { url: 'https://www.kra.go.ke/performance' }, 'https://www.kra.go.ke/performance'],
    ['HTTP document URL', { data_url: 'http://www.kra.go.ke/report.pdf' }, 'http://www.kra.go.ke/report.pdf'],
    ['document preferred', { data_url: 'https://www.kra.go.ke/report.pdf', url: 'https://www.kra.go.ke/performance' }, 'https://www.kra.go.ke/report.pdf'],
    ['valid fallback from invalid data URL', { data_url: 'not a URL', url: 'https://www.kra.go.ke/performance' }, 'https://www.kra.go.ke/performance'],
    ['valid fallback from malformed data URL', { data_url: true, url: 'https://www.kra.go.ke/performance' }, 'https://www.kra.go.ke/performance'],
    ['valid data URL with invalid publisher URL', { data_url: 'https://www.kra.go.ke/report.pdf', url: 'javascript:alert(1)' }, 'https://www.kra.go.ke/report.pdf'],
  ])('keeps the %s and the reported zero', (_name, source, url) => {
    const card = renderSource(source, ABSENT);
    expect(card.getByRole('link', { name: 'Source version' })).toHaveAttribute('href', url);
    expect(card.queryByText(ABSENT)).not.toBeInTheDocument();
    expect(card.getByText('KES 0B')).toBeInTheDocument();
  });
});

describe('RevenueMix publisher totals use the same URL boundary', () => {
  it.each([
    [{ url: 'javascript:alert(1)' }, undefined],
    [{ retrieved_at: '2026-09-27T12:00:00Z' }, undefined],
    [{ data_url: 'https://www.kra.go.ke/report.pdf' }, 'https://www.kra.go.ke/report.pdf'],
    [{ data_url: 'bad locator', url: 'https://www.kra.go.ke/performance' }, 'https://www.kra.go.ke/performance'],
  ])('keeps zero and applies locator validation to %j', (source, url) => {
    render(<RevenueMix revenueBySource={[{
      fiscal_year: 'FY 2025/26',
      sources: [
        { revenue_type: 'PAYE', amount: 12, basis: 'published' },
        { revenue_type: 'Total Tax Revenue', category: 'total', amount: 0, basis: 'published', source },
      ],
    }]} />);
    const total = screen.getByText(/Total Tax Revenue: KES 0B/);
    expect(total).toHaveTextContent('publisher-stated');
    if (url) {
      expect(within(total).getByRole('link', { name: 'Source version' })).toHaveAttribute('href', url);
      expect(total).not.toHaveTextContent('source version unavailable');
    } else {
      expect(within(total).queryByRole('link')).not.toBeInTheDocument();
      expect(total).toHaveTextContent('source version unavailable');
    }
  });
});
