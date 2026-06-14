/**
 * Shared QueryClient factory for both server (RSC prefetch) and client renders.
 *
 * Pattern (per TanStack's Next.js App Router guide):
 *   - On the server, every request gets a fresh client so one user's
 *     prefetch cache doesn't leak into another's.
 *   - In the browser, we hold onto a singleton so navigations can reuse
 *     cached queries and HydrationBoundary finds the same client that
 *     our `QueryProvider` registered.
 *
 * The shared config here is the single source of truth — `QueryProvider`
 * also calls `getQueryClient()` instead of new-ing up its own, so the
 * server-dehydrated cache hydrates cleanly into the client-provided one.
 */
import { QueryClient, isServer } from '@tanstack/react-query';

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10 * 60 * 1000,
        gcTime: 60 * 60 * 1000,
        retry: (failureCount, error: unknown) => {
          const status = (error as { response?: { status?: number } })?.response?.status;
          if (status !== undefined && status >= 400 && status < 500) return false;
          if (status === 503) return false;
          return failureCount < 2;
        },
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 15000),
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
      mutations: {
        retry: 1,
        retryDelay: 1000,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined = undefined;

export function getQueryClient(): QueryClient {
  if (isServer) return makeQueryClient();
  if (!browserQueryClient) browserQueryClient = makeQueryClient();
  return browserQueryClient;
}
