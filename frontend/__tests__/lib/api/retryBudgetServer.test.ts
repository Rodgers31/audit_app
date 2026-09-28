/** @jest-environment node */
import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/axios';
import { getQueryClient } from '@/lib/react-query/getQueryClient';

describe('server prefetch retry budget', () => {
  const originalAdapter = apiClient.defaults.adapter;

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('bounds a fresh server QueryClient and Axios request to three HTTP attempts', async () => {
    jest.useFakeTimers();
    jest.spyOn(console, 'error').mockImplementation(() => undefined);
    let attempts = 0;
    apiClient.defaults.adapter = async (config) => {
      attempts += 1;
      throw new AxiosError('Network error', AxiosError.ERR_NETWORK, config);
    };

    const result = getQueryClient().fetchQuery({
      queryKey: ['server', 'cold-start'],
      queryFn: ({ signal }) => apiClient.get('/server-cold-start', { signal }),
    }).then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toBe(3);
  });
});
