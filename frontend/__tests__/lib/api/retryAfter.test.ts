import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';
import { apiClient } from '@/lib/api/axios';

jest.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { getSession: async () => ({ data: { session: null } }) } }),
}));

describe('server-directed temporary read recovery', () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    jest.useRealTimers();
  });

  function refusal(header: unknown, attempts: number[], recover = false) {
    const errors: AxiosError[] = [];
    apiClient.defaults.adapter = async config => {
      attempts.push(Date.now());
      const response = {
        config, status: recover && attempts.length > 1 ? 200 : 503, statusText: '',
        headers: header === undefined ? {} : { 'Retry-After': header },
        data: { detail: 'Database request capacity unavailable' },
      };
      if (response.status === 503) {
        const error = new AxiosError('HTTP 503', AxiosError.ERR_BAD_RESPONSE, config, undefined, response as any);
        errors.push(error);
        throw error;
      }
      return response as any;
    };
    return errors;
  }

  it.each(['get', 'head'])('recovers a %s capacity refusal without a manual page refresh', async method => {
    let attempts = 0;
    apiClient.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
      attempts += 1;
      const response = {
        config, status: attempts === 1 ? 503 : 200, statusText: '',
        headers: { 'retry-after': '1' },
        data: attempts === 1 ? { detail: 'REQUEST_CAPACITY_EXCEEDED' } : { publishing_enabled: false },
      };
      if (response.status === 503) throw new AxiosError('HTTP 503', AxiosError.ERR_BAD_RESPONSE, config, undefined, response);
      return response;
    };
    const result = apiClient.request({ method, url: '/admin/social/system/status' })
      .then(r => r.data, () => 'Evidence unavailable');
    await jest.runAllTimersAsync();
    expect(await result).toEqual({ publishing_enabled: false });
    expect(attempts).toBe(2);
  });

  it('retains the three-attempt ceiling when temporary capacity never returns', async () => {
    const attempts: number[] = [];
    refusal('1', attempts);
    const result = apiClient.get('/admin/users/stats').then(() => 'success', e => e.response.status);
    await jest.runAllTimersAsync();
    expect(await result).toBe(503);
    expect(attempts).toHaveLength(3);
  });

  it('waits at least the server delay while preserving finite backoff', async () => {
    const attempts: number[] = [];
    refusal('2', attempts, true);
    const result = apiClient.get('/admin/audit-log').then(r => r.status, () => 503);
    await jest.advanceTimersByTimeAsync(1999);
    expect(attempts).toHaveLength(1);
    await jest.advanceTimersByTimeAsync(1);
    expect(await result).toBe(200);
    expect(attempts[1] - attempts[0]).toBe(2000);
  });

  it.each([undefined, '', 'NaN', 'Infinity', '-1', '1.5', '4', '99999999999999', true, false, ['1'], {}, 'tomorrow', '1\nx'])
  ('keeps an absent, malformed or over-budget Retry-After visible: %p', async header => {
    const attempts: number[] = [];
    refusal(header, attempts, true);
    const result = apiClient.get('/unavailable-data').then(() => 'success', e => e.response.status);
    await jest.runAllTimersAsync();
    expect(await result).toBe(503);
    expect(attempts).toHaveLength(1);
  });

  it.each(['1\n', '1\r\n'])('bounds recovery after Axios normalizes the adapter header %p', async raw => {
    const attempts: number[] = [];
    const errors = refusal(raw, attempts, true);
    const result = apiClient.get('/admin/audit-log').then(r => r.status, () => 503);
    await jest.runAllTimersAsync();
    // The locked Axios transport canonicalizes these bytes before our hook.
    const headers = errors[0].response!.headers;
    if (!(headers instanceof AxiosHeaders)) throw new Error('Expected transport-normalized AxiosHeaders');
    expect(headers.get('Retry-After')).toBe('1');
    expect(await result).toBe(200);
    expect(attempts).toHaveLength(2);
  });

  it.each(['post', 'put', 'patch', 'delete'])('never replays %s after a temporary refusal', async method => {
    const attempts: number[] = [];
    refusal('1', attempts, true);
    const result = apiClient.request({ method, url: '/admin/social/posts' }).then(() => 'success', e => e.response.status);
    await jest.runAllTimersAsync();
    expect(await result).toBe(503);
    expect(attempts).toHaveLength(1);
  });

  it.each([
    { 'Retry-After': '1', 'retry-after': '4' },
    { 'retry-after': '4', 'Retry-After': '1' },
    { 'Retry-After': '1', 'retry-after': '1' },
  ])('refuses ambiguous aliases at the raw-header interceptor boundary: %p', async headers => {
    // Normal Axios transports canonicalize headers first. Exercise the raw
    // fallback directly so its result cannot depend on object key order.
    const handler = (apiClient.interceptors.response as unknown as {
      handlers: Array<{ rejected: (error: AxiosError) => Promise<unknown> }>;
    }).handlers[0].rejected;
    const config = { method: 'get', url: '/inert-raw-refusal', headers: new AxiosHeaders() };
    let dispatches = 0;
    apiClient.defaults.adapter = async retryConfig => {
      dispatches += 1;
      return { config: retryConfig, status: 200, statusText: '', headers: {}, data: {} };
    };
    const error = new AxiosError('HTTP 503', AxiosError.ERR_BAD_RESPONSE, config, undefined, {
      config, status: 503, statusText: '', headers, data: {},
    });
    const result = handler(error).then(() => 'success', e => e.response.status);
    await jest.runAllTimersAsync();
    expect(await result).toBe(503);
    expect(dispatches).toBe(0);
  });

  it('cancels a pending capacity backoff without another HTTP attempt', async () => {
    const attempts: number[] = [];
    refusal('1', attempts, true);
    const control = new AbortController();
    const result = apiClient.get('/admin/audit-log', { signal: control.signal }).then(() => 'success', e => e.code);
    await jest.advanceTimersByTimeAsync(100);
    control.abort();
    await jest.runAllTimersAsync();
    expect(await result).toBe(AxiosError.ERR_CANCELED);
    expect(attempts).toHaveLength(1);
  });
});
