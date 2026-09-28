import type { AxiosInstance, AxiosResponse } from 'axios';

/** Preserve the existing one-argument call for direct callers without a signal. */
export function apiGet<T>(
  client: Pick<AxiosInstance, 'get'>,
  url: string,
  signal?: AbortSignal
): Promise<AxiosResponse<T>> {
  return signal ? client.get<T>(url, { signal }) : client.get<T>(url);
}
