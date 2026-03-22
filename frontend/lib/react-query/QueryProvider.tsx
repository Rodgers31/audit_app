/**
 * React Query Provider wrapper component
 */
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useState } from 'react';

interface QueryProviderProps {
  children: React.ReactNode;
}

export function QueryProvider({ children }: QueryProviderProps) {
  // Create a stable query client instance
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Stale time: data stays fresh for 10 minutes by default
            // Individual hooks override this for data that changes less often
            staleTime: 10 * 60 * 1000,
            // Cache time: keep unused data in memory for 60 minutes
            // This prevents re-fetching when navigating between pages
            gcTime: 60 * 60 * 1000,
            // Retry configuration
            retry: (failureCount, error: any) => {
              const status = error?.response?.status;
              // Don't retry on 4xx errors (client errors)
              if (status >= 400 && status < 500) {
                return false;
              }
              // Don't retry on 503 — means "data not seeded", not transient
              if (status === 503) {
                return false;
              }
              // Retry up to 2 times for other errors (502, 504, network)
              return failureCount < 2;
            },
            // Retry delay with exponential backoff
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 15000),
            // Only refetch on window focus in production (not on every tab switch)
            refetchOnWindowFocus: false,
            // Don't refetch on reconnect — stale data is fine for gov stats
            refetchOnReconnect: false,
            // ❌ REMOVED: refetchInterval — was polling ALL queries every 10min
            // Individual hooks can set refetchInterval if they need live data
          },
          mutations: {
            retry: 1,
            retryDelay: 1000,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {/* Show React Query DevTools in development */}
      {process.env.NODE_ENV === 'development' && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
