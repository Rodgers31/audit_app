/**
 * How old a server-prefetched query can be while its page is still fresh.
 *
 * Every route that dehydrates React Query data into its document declares
 * `export const revalidate = 3600` (`/`, `/counties`, `/counties/compare`,
 * `/audits`, `/transparency`, `/debt`, `/budget`). Next requires that export
 * to be a literal, so the pages cannot import this constant; instead
 * `__tests__/hydratedStaleRefetch.test.tsx` checks that each of them equals it.
 *
 * Why the hooks need it: a dehydrated query carries `dataUpdatedAt` = the
 * moment the page was rendered, and an ISR document is served unchanged for
 * up to `revalidate` seconds. So the hydrated data is as old as the document,
 * and a hook whose `staleTime` is shorter than the window refetches, on mount,
 * data the document has just rendered. OBSERVED on production (#221): `/` at
 * `age: 3243` re-downloaded `/audits/federal` (139,320 B gzip) and `/counties`
 * (41,824 B) after hydration; `/debt` and `/budget`, which had no `revalidate`
 * and were days old, re-requested every query they had shipped.
 *
 * The trade, accepted deliberately: a hook that reads SSR data re-checks it
 * after an hour rather than after 5–30 minutes. The backend caches the same
 * responses for 5–60 minutes and the data behind them changes nightly, so a
 * refetch inside the window mostly returned the bytes already on the page. A
 * document older than the window (served STALE while Vercel regenerates it)
 * still refetches on mount.
 */
export const ISR_REVALIDATE_SECONDS = 3600;

/** `staleTime` for any hook whose data a route dehydrates into its HTML. */
export const SSR_HYDRATED_STALE_TIME_MS = ISR_REVALIDATE_SECONDS * 1000;
