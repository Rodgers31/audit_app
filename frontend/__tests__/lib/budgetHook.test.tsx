import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useBudgetAllocation } from '@/lib/react-query/useBudget';
import { apiClient } from '@/lib/api/axios';
import captures from '../api/fixtures/county-budget-http.json';

jest.mock('@/lib/api/axios', () => ({ apiClient: { get: jest.fn() } }));
const get = apiClient.get as jest.Mock;

function harness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

beforeEach(() => get.mockReset());

test('hook publishes the selected account and absence despite a legacy fiscal-year argument', async () => {
  const { client, wrapper } = harness();
  get.mockResolvedValueOnce({ data: captures.missing_spending });
  const { result, unmount } = renderHook(() => useBudgetAllocation('mandera-county', '1900/01'), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.total_budget).toBe(2000);
  expect(result.current.data?.total_spent).toBeNull();
  expect(result.current.data?.fiscal_period?.label).toBe('FY2024/25');
  expect(result.current.data?.absent_reasons.total_spent).toBe('spending_not_reported');
  unmount();
  client.clear();
});

test('React Query cancellation reaches the real service transport', async () => {
  const { client, wrapper } = harness();
  let transportSignal: AbortSignal | undefined;
  get.mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
    transportSignal = options.signal;
    options.signal.addEventListener('abort', () => reject(new Error('cancelled')));
  }));
  const { result, unmount } = renderHook(() => useBudgetAllocation('mandera-county'), { wrapper });
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  await act(async () => client.cancelQueries({ queryKey: ['budget', 'allocation', 'mandera-county'] }));
  expect(transportSignal?.aborted).toBe(true);
  expect(result.current.data).toBeUndefined();
  unmount();
  client.clear();
});
