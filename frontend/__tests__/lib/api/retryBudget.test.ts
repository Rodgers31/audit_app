import { AxiosError, CanceledError, type AxiosAdapter, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { apiClient } from '@/lib/api/axios';
import { getCounties } from '@/lib/api/counties';
import { getQueryClient } from '@/lib/react-query/getQueryClient';

const response = (config: InternalAxiosRequestConfig, status: number) => ({
  config,
  data: status === 200 ? { value: 'ready' } : { detail: 'temporarily unavailable' },
  headers: {},
  status,
  statusText: String(status),
});

const statusAdapter = (statuses: number[], attempts: number[]): AxiosAdapter => async (config) => {
  const status = statuses[Math.min(attempts.length, statuses.length - 1)];
  attempts.push(status);
  if (status === 200) return response(config, status);
  throw new AxiosError(`HTTP ${status}`, AxiosError.ERR_BAD_RESPONSE, config, undefined, response(config, status));
};

const networkAdapter = (
  attempts: number[],
  successAt?: number,
  code: string = AxiosError.ERR_NETWORK
): AxiosAdapter => async (config) => {
  attempts.push(attempts.length + 1);
  if (successAt === attempts.length) return response(config, 200);
  throw new AxiosError('Network error', code, config);
};

describe('one HTTP retry budget', () => {
  const originalAdapter = apiClient.defaults.adapter;
  let errorLog: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers();
    getQueryClient().clear();
    errorLog = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    getQueryClient().clear();
    errorLog.mockRestore();
    jest.useRealTimers();
  });

  it('bounds a QueryClient request through the real Axios interceptor to three HTTP attempts', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([502], attempts);

    const result = getQueryClient()
      .fetchQuery({ queryKey: ['retry-budget', 'query'], queryFn: () => apiClient.get('/retry-budget') })
      .then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(3);
  });

  it.each([502, 504])('exhausts a direct GET on %i after three attempts', async (status) => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([status], attempts);
    const result = apiClient.get('/direct').then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(3);
  });

  it('recovers a direct GET after one transient network failure', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = networkAdapter(attempts, 2);
    const result = apiClient.get('/cold-start');

    await jest.runAllTimersAsync();

    expect((await result).data).toEqual({ value: 'ready' });
    expect(attempts).toHaveLength(2);
  });

  it('recovers a direct GET after a timeout', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = networkAdapter(attempts, 2, AxiosError.ECONNABORTED);
    const result = apiClient.get('/timeout');

    await jest.runAllTimersAsync();

    expect((await result).data).toEqual({ value: 'ready' });
    expect(attempts).toHaveLength(2);
  });

  it('returns an unchanged payload after a transient failure', async () => {
    const payload = {
      amount: 0,
      withheld: null,
      source: { page: 12, title: 'Published report' },
      metadata: { extraction_stats: null },
    };
    let attempts = 0;
    apiClient.defaults.adapter = async (config) => {
      attempts += 1;
      if (attempts === 1) {
        throw new AxiosError('HTTP 502', AxiosError.ERR_BAD_RESPONSE, config, undefined, response(config, 502));
      }
      return { ...response(config, 200), data: payload };
    };
    const result = apiClient.get('/published-data');

    await jest.runAllTimersAsync();

    expect((await result).data).toEqual(payload);
    expect(attempts).toBe(2);
  });

  it('does not retry a request configuration error with no HTTP response', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = networkAdapter(attempts, undefined, AxiosError.ERR_BAD_OPTION_VALUE);
    const result = apiClient.get('/bad-config').then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(1);
  });

  it('exhausts a direct GET after three network failures', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = networkAdapter(attempts);
    const result = apiClient.get('/network').then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(3);
  });

  it('does not accept a malformed caller retry counter as an unlimited budget', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([502, 502, 502, 502, 502, 200], attempts);
    const result = apiClient.get('/malformed-counter', {
      __retryCount: Number.NEGATIVE_INFINITY,
    } as AxiosRequestConfig).then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(3);
  });

  it.each([400, 404, 429, 503])('does not retry permanent HTTP %i', async (status) => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([status], attempts);
    const result = getQueryClient()
      .fetchQuery({ queryKey: ['permanent', status], queryFn: () => apiClient.get('/unavailable') })
      .then(() => null, (error: AxiosError) => error);

    await jest.runAllTimersAsync();

    expect((await result)?.response?.status).toBe(status);
    expect((await result)?.response?.data).toEqual({ detail: 'temporarily unavailable' });
    expect(attempts).toHaveLength(1);
  });

  it.each(['post', 'patch', 'delete'] as const)('does not repeat a failed %s mutation', async (method) => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = networkAdapter(attempts);
    const client = getQueryClient();
    const result = client.getMutationCache()
      .build(client, {
        mutationFn: () => apiClient.request({ method, url: '/mutation', data: { value: 1 } }),
      })
      .execute(undefined)
      .then(() => 'success', () => 'error');

    await jest.runAllTimersAsync();

    expect(await result).toBe('error');
    expect(attempts).toHaveLength(1);
  });

  it('cancels a pending backoff without sending another request', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([502], attempts);
    const controller = new AbortController();
    const result = apiClient.get('/cancel-backoff', { signal: controller.signal })
      .then(() => 'success', (error: unknown) => error);

    // Let the first adapter rejection reach the interceptor's wait.
    for (let i = 0; i < 20 && jest.getTimerCount() === 0; i += 1) await Promise.resolve();
    expect(attempts).toHaveLength(1);
    expect(jest.getTimerCount()).toBeGreaterThan(0);
    controller.abort();
    const error = await result;
    await jest.runAllTimersAsync();

    expect(error).toBeInstanceOf(CanceledError);
    expect(attempts).toHaveLength(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('stops an active query request when its QueryClient signal is cancelled', async () => {
    const attempts: number[] = [];
    let started!: () => void;
    const active = new Promise<void>((resolve) => { started = resolve; });
    apiClient.defaults.adapter = (config) => {
      attempts.push(1);
      started();
      return new Promise((_resolve, reject) => {
        config.signal?.addEventListener?.('abort', () => reject(new CanceledError()), { once: true });
      });
    };
    const client = getQueryClient();
    const result = client.fetchQuery({
      queryKey: ['cancel-active'],
      queryFn: ({ signal }) => apiClient.get('/cancel-active', { signal }),
    }).then(() => 'success', () => 'cancelled');

    await active;
    await client.cancelQueries({ queryKey: ['cancel-active'] });
    await jest.runAllTimersAsync();

    expect(await result).toBe('cancelled');
    expect(attempts).toHaveLength(1);
  });

  it('propagates query cancellation through the county API adapter and its backoff', async () => {
    const attempts: number[] = [];
    apiClient.defaults.adapter = statusAdapter([502], attempts);
    const client = getQueryClient();
    const result = client.fetchQuery({
      queryKey: ['counties', 'cancel-backoff'],
      queryFn: ({ signal }) => getCounties(undefined, signal),
    }).then(() => 'success', () => 'cancelled');

    await jest.advanceTimersByTimeAsync(0);
    expect(attempts).toHaveLength(1);
    expect(jest.getTimerCount()).toBeGreaterThan(0);
    await client.cancelQueries({ queryKey: ['counties', 'cancel-backoff'] });
    await jest.runAllTimersAsync();

    expect(await result).toBe('cancelled');
    expect(attempts).toHaveLength(1);
  });
});
