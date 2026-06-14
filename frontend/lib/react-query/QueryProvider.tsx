/**
 * React Query Provider wrapper.
 *
 * Uses the shared `getQueryClient()` helper so the client context and any
 * server-prefetched `HydrationBoundary` state land on the same singleton
 * in the browser. Without that, `HydrationBoundary` can render before the
 * provider's `useState` initializer runs and throw "No QueryClient set".
 */
'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { getQueryClient } from './getQueryClient';

interface QueryProviderProps {
  children: React.ReactNode;
}

export function QueryProvider({ children }: QueryProviderProps) {
  const queryClient = getQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === 'development' && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
