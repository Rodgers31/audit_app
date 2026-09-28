import type { QueryClient } from '@tanstack/react-query';

/** Stop SSR prefetch HTTP work when the render's existing wait limit expires. */
export async function prefetchWithTimeout<T>(
  queryClient: QueryClient,
  work: Promise<T>,
  timeoutMs: number
): Promise<T | undefined> {
  const timedOut = Symbol('prefetch timed out');
  let timer: ReturnType<typeof setTimeout> | undefined;

  try {
    const result = await Promise.race([
      work,
      new Promise<typeof timedOut>((resolve) => {
        timer = setTimeout(() => resolve(timedOut), timeoutMs);
      }),
    ]);
    if (result === timedOut) {
      await queryClient.cancelQueries();
      return undefined;
    }
    return result;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
