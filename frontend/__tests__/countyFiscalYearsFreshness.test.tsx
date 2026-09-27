/** Fiscal-year client requests use 30 minutes; hydrated readers may opt into ISR. */
import React, { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { getCountyFiscalYears } from '@/lib/api/counties';
import { countyFiscalYearsKey, useCountyFiscalYears } from '@/lib/react-query/useCounties';
import { SSR_HYDRATED_STALE_TIME_MS } from '@/lib/react-query/isr';
import type { CountyFiscalYears } from '@/lib/utils';

jest.mock('@/lib/api/counties', () => ({ getCountyFiscalYears: jest.fn() }));

const fetchYears = jest.mocked(getCountyFiscalYears);
const MINUTE = 60_000;
const OLD: CountyFiscalYears = {
  years: [{ label: 'FY 2024/25', source: 'cob_cbirr', counties: 47 }],
  default: 'FY 2024/25',
};
const NEW: CountyFiscalYears = {
  years: [{ label: 'FY 2025/26', source: 'cob_cbirr', counties: 47 }, ...OLD.years],
  default: 'FY 2025/26',
};

function cached(ageMinutes: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(countyFiscalYearsKey(), OLD, {
    updatedAt: Date.now() - ageMinutes * MINUTE,
  });
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}

beforeEach(() => {
  fetchYears.mockReset();
  fetchYears.mockResolvedValue(NEW);
});

it('refreshes a 31-minute-old client-fetched list on county detail remount', async () => {
  const { client, wrapper } = cached(31);
  const { result, unmount } = renderHook(() => useCountyFiscalYears(), { wrapper });
  await waitFor(() => expect(result.current.data?.default).toBe(NEW.default));
  expect(fetchYears).toHaveBeenCalledTimes(1);
  unmount();
  client.clear();
});

it('keeps a 29-minute-old client-fetched list without an unnecessary request', async () => {
  const { client, wrapper } = cached(29);
  const { result, unmount } = renderHook(() => useCountyFiscalYears(), { wrapper });
  await act(async () => {});
  expect(result.current.data).toEqual(OLD);
  expect(fetchYears).not.toHaveBeenCalled();
  unmount();
  client.clear();
});

it('allows a hydrated caller to retain its 55-minute-old ISR data', async () => {
  const { client, wrapper } = cached(55);
  const { result, unmount } = renderHook(
    () => useCountyFiscalYears({ staleTime: SSR_HYDRATED_STALE_TIME_MS }),
    { wrapper }
  );
  await act(async () => {});
  expect(result.current.data).toEqual(OLD);
  expect(fetchYears).not.toHaveBeenCalled();
  unmount();
  client.clear();
});

it('refreshes an expired list even when the hydrated caller opts into ISR', async () => {
  const { client, wrapper } = cached(61);
  const { result, unmount } = renderHook(
    () => useCountyFiscalYears({ staleTime: SSR_HYDRATED_STALE_TIME_MS }),
    { wrapper }
  );
  await waitFor(() => expect(result.current.data?.default).toBe(NEW.default));
  expect(fetchYears).toHaveBeenCalledTimes(1);
  unmount();
  client.clear();
});
