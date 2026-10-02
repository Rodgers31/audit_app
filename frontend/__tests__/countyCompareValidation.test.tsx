import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CompareClient from '@/app/counties/compare/ComparePageClient';
import ComparePage from '@/app/counties/compare/page';
import { getQueryClient } from '@/lib/react-query/getQueryClient';

const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = { get: (...args: unknown[]) => mockGet(...args) };
  return { __esModule: true, apiClient: client, default: client };
});
jest.mock('next/navigation', () => ({
  usePathname: () => '/counties/compare',
  useRouter: () => ({ replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeEach(() => {
  mockGet.mockReset();
  getQueryClient().clear();
});
afterEach(() => getQueryClient().clear());

it.each([[{ id: '001' }], { counties: [] }])('comparison rejects malformed %p in SSR and client', async (data) => {
  mockGet.mockResolvedValue({ data });
  const page = await ComparePage();
  expect(page.props.state.queries).toEqual([]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><CompareClient /></QueryClientProvider>);
  try {
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/Failed to load counties/));
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  } finally {
    view.unmount();
    client.clear();
  }
});

it('comparison SSR preserves raw county fields and null financial values', async () => {
  const data = [{ id: '001', name: 'Nairobi', code: '047', total_budget: 0, pending_bills: 0, population: null, debt: null }];
  mockGet.mockResolvedValue({ data });
  const page = await ComparePage();
  expect(page.props.state.queries[0].state.data).toEqual(data);
});
