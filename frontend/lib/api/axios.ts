/**
 * Axios configuration for API requests
 *
 * In development, requests are proxied through Next.js rewrites:
 *   Browser → localhost:3000/api/v1/* → localhost:8000/api/v1/*
 * This avoids CORS preflight overhead since same-origin requests don't
 * need OPTIONS pre-flight.
 *
 * Auth tokens are obtained from the Supabase session (cookie-based).
 * No manual localStorage management is needed.
 *
 * COLD-START RESILIENCE:
 * Render's Starter plan spins down after ~15 min of inactivity.
 * The response interceptor automatically retries on timeouts/network
 * errors with exponential backoff so the first visitor after a sleep
 * period still gets data without a manual refresh.
 */
import { createClient } from '@/lib/supabase/client';
import axios, { type AxiosError } from 'axios';

const API_VERSION = process.env.NEXT_PUBLIC_API_VERSION || 'v1';

// In production, NEXT_PUBLIC_API_URL points to the Render backend directly.
// In development, it falls back to localhost:8000.
// We always use the full URL so we don't depend on Next.js rewrites/proxy.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const baseURL = `${API_BASE}/api/${API_VERSION}`;

/** Max retries for network errors / timeouts (cold-start recovery) */
const MAX_RETRIES = 2;
/** Base delay between retries in ms (doubles each attempt: 2s → 4s) */
const RETRY_BASE_DELAY = 2000;

/** Returns true if the error is a network/timeout issue worth retrying */
function isRetryable(error: AxiosError): boolean {
  // Network error (ECONNREFUSED, ECONNRESET, etc.)
  if (!error.response) return true;
  // 502/504 — backend is booting or overloaded (worth retrying)
  // 503 is NOT retried here — it means "data not seeded/available" in this app,
  // not a transient failure. React Query handles its own retry logic.
  const status = error.response.status;
  return status === 502 || status === 504;
}

// Create axios instance with default configuration
export const apiClient = axios.create({
  baseURL,
  timeout: 30000,
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
    const config = error.config as any;
    if (!config) return Promise.reject(error);

    // Track retry count on the config object
    config.__retryCount = config.__retryCount || 0;

    if (isRetryable(error) && config.__retryCount < MAX_RETRIES) {
      config.__retryCount += 1;
      const delay = RETRY_BASE_DELAY * Math.pow(2, config.__retryCount - 1);

      if (process.env.NODE_ENV === 'development') {
        console.log(
          `🔄 Retry ${config.__retryCount}/${MAX_RETRIES}: ${config.method?.toUpperCase()} ${config.url} (waiting ${delay}ms)`
        );
      }

      await new Promise((resolve) => setTimeout(resolve, delay));
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
