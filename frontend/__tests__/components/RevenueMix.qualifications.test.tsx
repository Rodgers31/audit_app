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

const CAUTION = 'Dashboard version; not independently reconciled to the KRA annual PDF.';
const SOURCE = {
  url: 'https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026',
  data_url: 'https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js',
  version: 'dashboard_bundle', period: 'FY 2025/26', publication_date: null,
  retrieved_at: '2026-09-27T00:00:00+00:00',
  stated_amount_billion_kes: '0', reconciliation: CAUTION,
};

function subject(kind: 'head' | 'total', source: unknown, absentReason: string | null = 'Recorded source locator unavailable.') {
  const row = JSON.parse(JSON.stringify({
    revenue_type: kind === 'head' ? 'PAYE' : 'Total Agency Revenue',
    category: kind === 'head' ? 'tax' : 'total', amount: 0, basis: 'published', source,
    source_absent_reason: absentReason,
  })) as RevSource;
  render(<RevenueMix revenueBySource={[{
    fiscal_year: 'FY 2025/26', sources: [row, { revenue_type: 'VAT', amount: 12, basis: 'published' }],
  }]} />);
  const el = kind === 'head'
    ? screen.getByText('PAYE').closest('[data-revenue-card]')
    : screen.getByText(/Total Agency Revenue: KES 0B/);
  if (!(el instanceof HTMLElement)) throw new Error('Expected rendered observation');
  return within(el);
}

describe.each(['head', 'total'] as const)('RevenueMix %s observation qualifications', (kind) => {
  it('preserves stated zero, retrieval date and known reconciliation with a valid locator', () => {
    const row = subject(kind, SOURCE);
    expect(row.getByText(/stated KES 0B/)).toBeInTheDocument();
    expect(row.getByText(/retrieved 2026-09-27/)).toBeInTheDocument();
    expect(row.getByText(new RegExp(CAUTION.replace('.', '\\.')))).toBeInTheDocument();
    expect(row.getByRole('link', { name: 'Source version' })).toHaveAttribute('href', SOURCE.data_url);
  });

  it('distinguishes the recorded edition and observation period from an unknown publication date', () => {
    const row = subject(kind, SOURCE);
    expect(row.getByText(/edition dashboard_bundle/i)).toBeInTheDocument();
    expect(row.getByText(/source period FY 2025\/26/i)).toBeInTheDocument();
    expect(row.getByText(/publication date unavailable/i)).toBeInTheDocument();
    expect(row.queryByText(/published 2026-09-27/i)).not.toBeInTheDocument();
  });

  it.each([undefined, 'javascript:alert(1)'])('keeps known uncertainty when the locator is %s', (url) => {
    const row = subject(kind, { ...SOURCE, url, data_url: undefined });
    expect(row.queryByRole('link')).not.toBeInTheDocument();
    expect(row.getByText(new RegExp(CAUTION.replace('.', '\\.')))).toBeInTheDocument();
    expect(row.getByText(/retrieved 2026-09-27/)).toBeInTheDocument();
  });

  it('does not deny a recorded date or edition when the API omits its absence explanation', () => {
    const row = subject(kind, { ...SOURCE, url: undefined, data_url: undefined }, null);
    expect(row.getByText('Source URL unavailable.')).toBeInTheDocument();
    expect(row.getByText(/retrieved 2026-09-27/)).toBeInTheDocument();
    expect(row.queryByText(/observation date unavailable/i)).not.toBeInTheDocument();
  });
});

it('keeps a partial current release distinct from historical values and withholds residual/shares', () => {
  render(<RevenueMix revenueBySource={[
    { fiscal_year: 'FY 2024/25', sources: [
      { revenue_type: 'PAYE', amount: 560.963, basis: 'published' },
      { revenue_type: 'VAT', amount: 327.336, basis: 'published' },
    ] },
    { fiscal_year: 'FY 2025/26', sources: [
      { revenue_type: 'PAYE', amount: 0, basis: 'published', source: SOURCE },
      { revenue_type: 'VAT', amount: null, absent_reason: 'No observation' },
      { revenue_type: 'Other Tax Revenue', amount: 216.247, basis: 'residual' },
    ] },
  ]} />);
  expect(screen.getByText('KRA revenue collections · FY 2025/26')).toBeInTheDocument();
  expect(screen.getByText('KES 0B')).toBeInTheDocument();
  expect(screen.queryByText('VAT')).not.toBeInTheDocument();
  expect(screen.queryByText('Other Tax Revenue')).not.toBeInTheDocument();
  expect(screen.getByText(/percentage shares are unavailable/)).toBeInTheDocument();
});
