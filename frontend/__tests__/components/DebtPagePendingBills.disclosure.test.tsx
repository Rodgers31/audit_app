import '@testing-library/jest-dom';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NationalDebtPage from '@/app/debt/DebtPageClient';
import type { PendingBillsResponse, PendingBillsSummaryResponse } from '@/lib/api/debt';

const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = { get: (...args: unknown[]) => mockGet(...args) };
  return { __esModule: true, apiClient: client, default: client };
});
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ isAuthenticated: false }) }));
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

const coverage = {
  national_components: 2,
  national_expected: 2,
  national_complete: true,
  county_count: 46,
  county_expected: 47,
  county_complete: false,
  missing_counties: ['Nandi'],
  qualified_counties: [],
};

const pending: PendingBillsResponse = {
  status: 'success',
  data_source: 'database',
  pending_bills: [],
  summary: {
    total_pending: null,
    national_total: 525_900_000_000,
    county_total: null,
    total_absent_reason: 'incomplete_county_publication',
    reported_county_sum: 280_000_000_000,
    coverage,
    national_as_at: '2025-06-30',
    county_as_at: '2026-06-30',
    record_count: 48,
  },
  sources: [
    { side: 'national', title: 'Treasury BROP', url: 'https://example.org/brop', as_at: '2025-06-30' },
    { side: 'county', title: 'Controller of Budget CBIRR', url: 'https://example.org/cbirr', as_at: '2026-06-30' },
  ],
  source: 'Treasury BROP; Controller of Budget CBIRR',
  source_url: 'https://example.org/brop',
  currency: 'KES',
  explanation: 'Synthetic pending-bills fixture.',
};

const summary: PendingBillsSummaryResponse = {
  total_pending_amount: null,
  total_absent_reason: 'incomplete_county_publication',
  coverage,
  reported_county_sum: 280_000_000_000,
  breakdown_by_type: {},
  aging_buckets: null,
  aging_buckets_absent_reason: 'loans_table_carries_no_aging_data',
  top_counties_by_amount: [
    { county_id: '1', county_name: 'Mombasa', amount: 12_000_000_000, per_capita: 0, population: 0 },
  ],
  trend: [],
};

async function mount(bills: PendingBillsResponse | null = pending, ranking: PendingBillsSummaryResponse = summary) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockGet.mockImplementation((url: string) =>
    !bills && url === '/pending-bills'
      ? Promise.reject(new Error('synthetic unavailable endpoint'))
      : Promise.resolve({ data: url === '/data/freshness' ? { sources: [] } : {} })
  );
  client.setQueryData(['debt', 'national'], { data: {
    total_outstanding: 12_000_000_000_000,
    gdp: 20_000_000_000_000,
    summary: {}, categories: {},
  } });
  client.setQueryData(['debt', 'national-loans'], { loans: [] });
  client.setQueryData(['debt', 'national-timeline'], { timeline: [] });
  client.setQueryData(['fiscal', 'summary'], { history: [] });
  if (bills) client.setQueryData(['debt', 'pending-bills'], bills);
  client.setQueryData(['debt', 'pending-bills-summary'], ranking);
  const view = render(<QueryClientProvider client={client}><NationalDebtPage /></QueryClientProvider>);
  await act(async () => { await Promise.resolve(); });
  return { ...view, client };
}

function stalledPayments() {
  return screen.getByRole('heading', { name: /stalled payments/i, level: 2 }).closest('section')!;
}

describe('debt page pending-bills disclosure (#321)', () => {
  it('explains a partial county publication and separates the reported sum from the withheld total', async () => {
    await mount();
    const section = stalledPayments();
    expect(section).toHaveTextContent(/combined total not published/i);
    expect(section).toHaveTextContent(/46 of 47 counties/i);
    expect(section).toHaveTextContent(/reported county sum/i);
    expect(section).toHaveTextContent('KES 280.0B');
    expect(section).not.toHaveTextContent('KES 805.9B');
    expect(within(section).getByRole('link', { name: /Treasury BROP/i })).toHaveAttribute('href', 'https://example.org/brop');
    expect(within(section).getByRole('link', { name: /Controller of Budget CBIRR/i })).toHaveAttribute('href', 'https://example.org/cbirr');
    expect(section).toHaveTextContent(/30 June 2025/);
    expect(section).toHaveTextContent(/30 June 2026/);
    fireEvent.click(within(section).getByRole('button', { name: 'Counties' }));
    expect(within(section).getByRole('button', { name: 'Counties' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(section).getByRole('heading', { name: /reported counties by stalled payments/i })).toBeInTheDocument();
    expect(section).toHaveTextContent(/ranking covers 46 of 47 counties/i);
  });

  it('discloses qualified county amounts without certifying the county sum', async () => {
    await mount({ ...pending, summary: {
      ...pending.summary,
      coverage: { ...coverage, county_count: 47, missing_counties: [], qualified_counties: ['Nandi'] },
    } }, { ...summary, coverage: { ...coverage, county_count: 47, missing_counties: [], qualified_counties: ['Nandi'] } });
    const section = stalledPayments();
    expect(section).toHaveTextContent(/qualified reported amounts/i);
    expect(section).toHaveTextContent(/reported county sum/i);
    fireEvent.click(within(section).getByRole('button', { name: 'Counties' }));
    expect(section).toHaveTextContent(/ranking.*qualified/i);
  });

  it('does not certify a full ranking when the two cached summaries disagree', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount(pending, { ...summary, coverage: complete });
    const section = stalledPayments();
    fireEvent.click(within(section).getByRole('button', { name: 'Counties' }));
    expect(within(section).getByRole('heading', { name: 'Reported counties by stalled payments' })).toBeInTheDocument();
    expect(section).toHaveTextContent(/source summaries do not agree/i);
    expect(section).not.toHaveTextContent(/ranking covers 47 of 47/i);
  });

  it('does not certify a full ranking when missing-county identities conflict', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, total_pending: 805_900_000_000,
      county_total: 280_000_000_000, total_absent_reason: null,
      coverage: complete, county_as_at: '2025-06-30',
    } }, { ...summary, total_pending_amount: 805_900_000_000,
      coverage: { ...complete, missing_counties: ['Nandi'] } });
    const section = stalledPayments();
    expect(section).not.toHaveTextContent('KES 805.9B');
    fireEvent.click(within(section).getByRole('button', { name: 'Counties' }));
    expect(within(section).getByRole('heading', { name: 'Reported counties by stalled payments' })).toBeInTheDocument();
  });

  it('withholds a complete hero total when the ranking summary says county publication is partial', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, total_pending: 805_900_000_000, county_total: 280_000_000_000,
      total_absent_reason: null, coverage: complete,
    } }, summary);
    const section = stalledPayments();
    expect(section).toHaveTextContent(/source summaries do not agree/i);
    expect(section).not.toHaveTextContent('KES 805.9B');
    expect(section).not.toHaveTextContent('65%');
  });

  it('does not show a partial county amount as the complete county total', async () => {
    await mount({ ...pending, summary: {
      ...pending.summary, county_total: 280_000_000_000,
    } });
    const section = stalledPayments();
    const countyCell = within(section).getAllByText('Counties', { exact: true })[1].parentElement!;
    expect(countyCell).toHaveTextContent(/Reported county sum: KES 280.0B/);
    expect(countyCell).toHaveTextContent('—');
  });

  it('states missing date and source context even when an amount is present', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, sources: [], summary: {
      ...pending.summary, total_pending: 805_900_000_000, county_total: 280_000_000_000,
      total_absent_reason: null, coverage: complete, national_as_at: null, county_as_at: null,
    } }, { ...summary, total_pending_amount: 805_900_000_000, coverage: complete });
    const section = stalledPayments();
    expect(section).toHaveTextContent('Date unavailable');
    expect(section).toHaveTextContent('Source link unavailable');
  });

  it('reports an unavailable endpoint instead of removing the section', async () => {
    await mount(null);
    await waitFor(() => expect(stalledPayments()).toHaveTextContent(/pending-bills information is temporarily unavailable/i));
  });

  it('does not print non-finite or negative amounts as published pending bills', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, total_pending: Infinity, national_total: -5,
      county_total: 280_000_000_000, total_absent_reason: null, coverage: complete,
    } }, { ...summary, total_pending_amount: Infinity, coverage: complete });
    const section = stalledPayments();
    expect(section).not.toHaveTextContent('Infinity');
    expect(section).not.toHaveTextContent('KES -5');
    expect(section).toHaveTextContent(/combined total not published/i);
  });

  it('does not claim an absent combined total is unaffected by missing aging data', async () => {
    await mount();
    const section = stalledPayments();
    expect(section).not.toHaveTextContent('The total above is unaffected.');
    expect(section).toHaveTextContent(/no age breakdown is shown/i);
  });

  it('does not turn an unsafe source value into a link', async () => {
    await mount({ ...pending, sources: [
      pending.sources![0],
      { ...pending.sources![1], url: 'javascript:alert(1)' },
    ] });
    const section = stalledPayments();
    expect(section).toHaveTextContent('Controller of Budget CBIRR');
    expect(section).toHaveTextContent('Controller of Budget CBIRR · Source link unavailable');
    expect(within(section).queryByRole('link', { name: 'Controller of Budget CBIRR' })).not.toBeInTheDocument();
  });

  it('keeps the different reporting dates visible when both components are complete', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, county_total: 280_000_000_000,
      total_absent_reason: 'national_and_county_stated_at_different_dates', coverage: complete,
    } }, { ...summary, coverage: complete,
      total_absent_reason: 'national_and_county_stated_at_different_dates' });
    const section = stalledPayments();
    expect(section).toHaveTextContent(/combined total not published/i);
    expect(section).toHaveTextContent(/national figure is at 30 June 2025 and the county figure at 30 June 2026/i);
    expect(section).not.toHaveTextContent('KES 805.9B');
  });

  it('preserves complete totals and a full-coverage ranking', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, total_pending: 805_900_000_000, county_total: 280_000_000_000,
      total_absent_reason: null, coverage: complete, county_as_at: '2025-06-30',
    } }, { ...summary, total_pending_amount: 805_900_000_000, total_absent_reason: null, coverage: complete });
    const section = stalledPayments();
    expect(section).toHaveTextContent('KES 805.9B');
    expect(section).toHaveTextContent('KES 280.0B');
    expect(section).not.toHaveTextContent(/combined total not published/i);
    fireEvent.click(within(section).getByRole('button', { name: 'Counties' }));
    expect(within(section).getByRole('heading', { name: 'Top counties by stalled payments' })).toBeInTheDocument();
  });

  it('shows an explicit published zero rather than an absent figure', async () => {
    const complete = { ...coverage, county_count: 47, county_complete: true, missing_counties: [] };
    await mount({ ...pending, summary: {
      ...pending.summary, total_pending: 0, national_total: 0, county_total: 0,
      reported_county_sum: 0, total_absent_reason: null, coverage: complete,
      county_as_at: '2025-06-30',
    } }, { ...summary, total_pending_amount: 0, reported_county_sum: 0, total_absent_reason: null, coverage: complete, top_counties_by_amount: [] });
    const section = stalledPayments();
    expect(section).toHaveTextContent('KES 0');
    expect(section).not.toHaveTextContent(/combined total not published/i);
  });

  it('states when no pending-bills figures are published', async () => {
    await mount({ ...pending, status: 'no_data', summary: {
      total_pending: null, national_total: null, county_total: null, record_count: 0,
    } }, { ...summary, top_counties_by_amount: [] });
    expect(stalledPayments()).toHaveTextContent(/no pending-bills figure is published/i);
    expect(stalledPayments()).not.toHaveTextContent('KES 0');
  });
});
