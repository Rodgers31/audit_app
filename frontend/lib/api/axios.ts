/**
 * Axios configuration for API requests
 *
 * Browser requests use the public backend directly. Server prefetches can
 * use INTERNAL_API_URL when the backend has a separate container address.
 *
 * Auth tokens are obtained from the Supabase session (cookie-based).
 * No manual localStorage management is needed.
 *
 * A bounded retry budget helps safe reads recover from transient network
 * failures and backend startup delays.
 */
import { createClient } from '@/lib/supabase/client';
import { getApiBase } from './base';
import axios, { AxiosError, AxiosHeaders, CanceledError, type InternalAxiosRequestConfig } from 'axios';

const API_VERSION = process.env.NEXT_PUBLIC_API_VERSION || 'v1';

// Browser calls retain the direct public API address. Server prefetches can
// reach the backend over container DNS through a runtime-only internal address.
const API_BASE = getApiBase();
const baseURL = `${API_BASE}/api/${API_VERSION}`;

/** Max retries for network errors / timeouts (cold-start recovery) */
const MAX_RETRIES = 2;
/** Base delay between retries in ms (doubles each attempt: 1.5s → 3s) */
const RETRY_BASE_DELAY = 1500;
// Serving capacity refusals use delta-seconds. Longer or unknown instructions
// remain visible failures; they cannot extend this client's existing backoff ceiling.
const MAX_RETRY_AFTER_DELAY = RETRY_BASE_DELAY * 2;

type RetryConfig = InternalAxiosRequestConfig & { __retryCount?: number };

function capacityRetryDelay(error: AxiosError): number | undefined {
  if (error.response?.status !== 503) return undefined;
  const headers = error.response.headers;
  let header: unknown;
  if (headers instanceof AxiosHeaders) {
    header = headers.get('Retry-After');
  } else {
    const matches = Object.entries(headers).filter(([name]) => name.toLowerCase() === 'retry-after');
    if (matches.length !== 1) return undefined;
    header = matches[0][1];
  }
  if (typeof header !== 'string' || /[\r\n]/.test(header)
      || !/^[ \t]*[0-9]{1,3}[ \t]*$/.test(header)) return undefined;
  const delay = Number(header) * 1000;
  return delay <= MAX_RETRY_AFTER_DELAY ? delay : undefined;
}

/** Only safe reads get automatic retries. Mutations need caller-level decisions. */
function isRetryable(error: AxiosError, config: RetryConfig): boolean {
  if (config.signal?.aborted || error.code === AxiosError.ERR_CANCELED) return false;
  const method = (config.method ?? 'get').toLowerCase();
  if (method !== 'get' && method !== 'head') {
    return false;
  }
  if (!error.response) {
    // Exclude request setup and malformed URL errors with no HTTP response.
    return [
      AxiosError.ERR_NETWORK,
      AxiosError.ECONNABORTED,
      AxiosError.ETIMEDOUT,
      AxiosError.ECONNREFUSED,
      'ECONNRESET',
      'EHOSTUNREACH',
      'ENOTFOUND',
      'EAI_AGAIN',
    ].includes(error.code ?? '');
  }
  // An explicit short Retry-After distinguishes temporary admission from
  // unavailable data. A bare 503 remains a visible failure.
  const status = error.response.status;
  return status === 502 || status === 504 || capacityRetryDelay(error) !== undefined;
}

/** Abort a pending backoff immediately when its logical request is cancelled. */
function waitForRetry(delay: number, config: RetryConfig): Promise<void> {
  const signal = config.signal;
  if (signal?.aborted) return Promise.reject(new CanceledError());

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener?.('abort', onAbort);
      reject(new CanceledError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, delay);
    signal?.addEventListener?.('abort', onAbort, { once: true });
    // The signal may have fired between the first check and listener registration.
    if (signal?.aborted) onAbort();
  });
}

// Create axios instance with default configuration
export const apiClient = axios.create({
  baseURL,
  timeout: 12000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor — attach Supabase access token for backend calls
apiClient.interceptors.request.use(
  async (config) => {
    // Attach Supabase access token if available (browser only)
    if (typeof window !== 'undefined') {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session?.access_token) {
          config.headers.Authorization = `Bearer ${session.access_token}`;
        }
      } catch {
        // Silent — unauthenticated requests are fine for public endpoints
      }
    }

    // Log requests in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`🚀 API Request: ${config.method?.toUpperCase()} ${config.url}`);
    }

    return config;
  },
  (error) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor — retry on cold-start errors + logging
apiClient.interceptors.response.use(
  (response) => {
    // Log successful responses in development
    if (process.env.NODE_ENV === 'development') {
      console.log(
        `✅ API Response: ${response.config.method?.toUpperCase()} ${response.config.url}`,
        response.status
      );
    }
    return response;
  },
  async (error: AxiosError) => {
    const config = error.config as RetryConfig | undefined;
    if (!config) return Promise.reject(error);

    // Axios preserves custom config fields. Reject malformed counts so a
    // caller cannot accidentally turn the retry budget into an unbounded loop.
    const suppliedRetryCount = config.__retryCount;
    config.__retryCount =
      typeof suppliedRetryCount === 'number' &&
      Number.isInteger(suppliedRetryCount) &&
      suppliedRetryCount >= 0
        ? suppliedRetryCount
        : 0;

    if (isRetryable(error, config) && config.__retryCount < MAX_RETRIES) {
      config.__retryCount += 1;
      const delay = Math.max(
        RETRY_BASE_DELAY * Math.pow(2, config.__retryCount - 1),
        capacityRetryDelay(error) ?? 0
      );

      if (process.env.NODE_ENV === 'development') {
        console.log(
          `🔄 Retry ${config.__retryCount}/${MAX_RETRIES}: ${config.method?.toUpperCase()} ${config.url} (waiting ${delay}ms)`
        );
      }

      await waitForRetry(delay, config);
      return apiClient(config);
    }

    // Log errors — downgrade to warn for expected failures (503 = data not seeded, 404 = not found)
    const status = error.response?.status;
    const isExpectedFailure = status === 503 || status === 404;
    const logFn = isExpectedFailure ? console.warn : console.error;
    const prefix = isExpectedFailure ? '⚠️ API Warning' : '❌ API Error';

    if (process.env.NODE_ENV === 'development' || !isExpectedFailure) {
      logFn(`${prefix}:`, {
        url: error.config?.url,
        method: error.config?.method,
        status,
        message: (error.response?.data as any)?.message || (error.response?.data as any)?.detail || error.message,
        retries: config.__retryCount || 0,
      });
    }

    return Promise.reject(error);
  }
);

export default apiClient;
