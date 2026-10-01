import '@testing-library/jest-dom';
import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NationalDebtPage from '@/app/debt/DebtPageClient';

const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = { get: (...args: unknown[]) => mockGet(...args) };
  return { __esModule: true, apiClient: client, default: client };
});
jest.mock('@/lib/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));
jest.mock('next/navigation', () => ({
  usePathname: () => '/debt',
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

if (typeof globalThis.IntersectionObserver === 'undefined') {
  globalThis.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
  } as unknown as typeof IntersectionObserver;
}

// The real API contract: the register total and GDP are not the numerator
// and denominator of the separately published WEO observation.
const IMF_DSA = {
  overall_risk_of_debt_distress: 'High',
  risk_of_external_debt_distress: 'High',
  source: {
    series: 'IMF Country Report No. 24/316',
    url: 'https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf',
    page: 132,
    dsa_date: '2024-10-18',
    published: '2024-11-01',
  },
  latest_confirmed: { as_of: '2026-03-31' },
};
const OVERVIEW = {
  total_outstanding: 12_000_000_000_000,
  gdp: 20_000_000_000_000,
  debt_to_gdp_ratio: 69.3,
  debt_to_gdp_year: 2025,
  debt_to_gdp_basis: 'IMF General Government Gross Debt, % of GDP (GGXWDG_NGDP) — vintage-consistent',
  debt_to_gdp_source: 'IMF World Economic Outlook',
  debt_sustainability: { imf_dsa: IMF_DSA },
  summary: {},
  categories: {},
};

let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockGet.mockReset();
  mockGet.mockImplementation((url: string) => Promise.resolve({
    data: url === '/data/freshness' ? { sources: [] } : {},
  }));
  client.setQueryData(['debt', 'national-loans'], { loans: [] });
  client.setQueryData(['debt', 'national-timeline'], { timeline: [] });
  client.setQueryData(['fiscal', 'summary'], { history: [] });
  client.setQueryData(['debt', 'pending-bills'], { status: 'no_data' });
  client.setQueryData(['debt', 'pending-bills-summary'], {});
});
afterEach(() => client.clear());

async function mount(patch: Record<string, unknown> = {}) {
  client.setQueryData(['debt', 'national'], { data: { ...OVERVIEW, ...patch } });
  const view = render(<QueryClientProvider client={client}><NationalDebtPage /></QueryClientProvider>);
  await act(async () => { await Promise.resolve(); });
  return view;
}

// Locate the existing tile so the red run fails on the financial claim,
// rather than on a new test ID or a new accessibility label.
function ratioTile() {
  return screen.getByText('Debt-to-GDP', { exact: true }).parentElement!;
}

describe('debt page financial claims (#289)', () => {
  it('shows the reported nominal ratio with its own basis, year and source', async () => {
    await mount();
    expect(ratioTile()).toHaveTextContent('69.3%');
    expect(ratioTile()).not.toHaveTextContent('vs PFM Act 55%');
    expect(ratioTile()).toHaveTextContent('Nominal debt');
    expect(ratioTile()).toHaveTextContent(OVERVIEW.debt_to_gdp_basis);
    expect(ratioTile()).toHaveTextContent('Observation: 2025');
    expect(ratioTile()).toHaveTextContent('IMF World Economic Outlook');
  });

  it.each([35, 50, 69.3])('does not classify a nominal ratio of %s with a colored gauge', async (ratio) => {
    await mount({ debt_to_gdp_ratio: ratio });
    expect(ratioTile()).toHaveTextContent(`${ratio.toFixed(1)}%`);
    expect(ratioTile().querySelector('[style*="background"]')).toBeNull();
  });

  it.each([null, undefined, NaN, Infinity, -Infinity, -1, true, '69.3', {}, []])('keeps missing or invalid %s ratios absent even with register/GDP inputs', async (ratio) => {
    await mount({ debt_to_gdp_ratio: ratio });
    expect(ratioTile()).toHaveTextContent('Not published');
    expect(ratioTile()).not.toHaveTextContent(/\d+(\.\d+)?%/);
    expect(screen.getByText('High', { exact: true })).toBeInTheDocument();
  });

  it('preserves a reported zero without manufacturing a risk classification', async () => {
    await mount({ debt_to_gdp_ratio: 0 });
    expect(ratioTile()).toHaveTextContent('0.0%');
    expect(ratioTile()).not.toHaveTextContent('Low');
  });

  it('does not borrow the total-debt date/source when ratio metadata is missing', async () => {
    await mount({ debt_to_gdp_year: null, debt_to_gdp_source: null, debt_to_gdp_basis: null,
      as_of: '2026-09-27', source: 'Unrelated register source' });
    expect(ratioTile()).toHaveTextContent('Observation year unavailable');
    expect(ratioTile()).toHaveTextContent('Source unavailable');
    expect(ratioTile()).toHaveTextContent('Basis unavailable');
    expect(ratioTile()).not.toHaveTextContent('Unrelated register source');
  });

  it('retains the dated, linked assessment independently of the ratio', async () => {
    await mount({ debt_to_gdp_ratio: 35 });
    expect(screen.getByText('High', { exact: true })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'IMF–World Bank DSA, Oct 2024' }))
      .toHaveAttribute('href', `${IMF_DSA.source.url}#page=132`);
    expect(screen.getByText(/Published 1 Nov 2024/)).toHaveTextContent('31 Mar 2026');
    expect(screen.getByText(/Published 1 Nov 2024/)).toHaveTextContent('current status unverified');
  });

  it.each([{}, [], true, 12, '   '])('withholds malformed source and basis %p', async (value) => {
    await mount({ debt_to_gdp_source: value, debt_to_gdp_basis: value });
    expect(ratioTile()).toHaveTextContent('Source unavailable');
    expect(ratioTile()).toHaveTextContent('Basis unavailable');
    expect(ratioTile()).toHaveTextContent('69.3%');
  });

  it.each([{}, [], false, 0, -1, 2025.5, '2025', NaN, Infinity, ''])('withholds malformed observation year %p', async (year) => {
    await mount({ debt_to_gdp_year: year });
    expect(ratioTile()).toHaveTextContent('Observation year unavailable');
    expect(ratioTile()).not.toHaveTextContent('Observation:');
  });

  it.each([{}, { risk_level: 'High' }, { imf_dsa: { ...IMF_DSA, source: {} } }])(
    'does not derive a missing/uncited assessment from a high nominal ratio', async (debt_sustainability) => {
      await mount({ debt_sustainability, debt_to_gdp_ratio: 95 });
      expect(screen.getByText('Not assessed')).toBeInTheDocument();
      expect(screen.queryByText('High', { exact: true })).not.toBeInTheDocument();
    }
  );
});

// The current page withdrew the peer comparison. API states must not restore
// that strip, a peer average, or a zero debt-service claim through normalization.
describe.each([
  ['absent', { status: 'no_data', regional_peers: [{ country: 'Ethiopia', debt_to_gdp: null,
    debt_to_gdp_year: null, debt_to_gdp_absent_reason: 'no_reference_year' }] }],
  ['partial', { status: 'success', regional_peers: [{ country: 'Rwanda', debt_to_gdp: 0,
    debt_to_gdp_year: 2025, interest_payments_pct_revenue: null }] }],
  ['supported', { status: 'success', regional_peers: [{ country: 'Ethiopia', debt_to_gdp: 23,
    debt_to_gdp_year: 2025, interest_payments_pct_revenue: 0, external_debt_pct_gni: 12 }] }],
])('withdrawn regional comparison with %s API state', (_label, payload) => {
  it('keeps the existing sourced headline and does not consume or render peers', async () => {
    client.setQueryData(['debt', 'debt-sustainability'], payload);
    await mount();
    expect(ratioTile()).toHaveTextContent('69.3%');
    expect(screen.queryByText(/EAC peer average|Service \/ Revenue|Ethiopia|Rwanda/)).not.toBeInTheDocument();
    expect(mockGet.mock.calls.some(([url]) => String(url).includes('/debt/sustainability'))).toBe(false);
  });
});
