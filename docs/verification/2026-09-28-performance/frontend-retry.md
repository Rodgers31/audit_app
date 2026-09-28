# Frontend retry budget verification — issue #357

## Change

- Axios owns a maximum of three HTTP attempts for GET and HEAD reads on transient network/timeout failures and HTTP 502/504. It skips cancelled requests, request setup errors, mutations, 4xx and the app's unavailable 503. The 12-second per-attempt timeout was not increased.
- The shared browser/server QueryClient has no automatic query or mutation retry. The three local query retry overrides were removed. Direct and SSR Axios callers retain cold-start recovery.
- Query functions pass TanStack's `AbortSignal` through the API adapters to Axios. Axios backoff stops when that signal aborts. The debt page's direct population read aborts on effect cleanup.
- All eight SSR pages with a prefetch timeout now cancel their request-scoped QueryClient when the existing timeout wins and clear the timer when work settles. No response fields, data transformations, unavailable states or UI layout changed.

## Behavioral receipts

- Before the change, `./node_modules/.bin/jest --runInBand __tests__/lib/api/retryBudget.test.ts` failed: repeated 502s made **9** HTTP attempts through real QueryClient + Axios, while the fixture expected 3. After the change, it passed with 3.
- Before the SSR timeout fix, `./node_modules/.bin/jest --runInBand __tests__/ssrPrefetchCancellation.test.tsx` failed: the page returned at its timeout while the request's signal remained unabortable (`false`, expected `true`). After the fix, it passed. An independent fake 502 transport observed one request at render and one after both former backoffs, versus three after the old timeout race.
- Before retry-counter validation, `./node_modules/.bin/jest --runInBand __tests__/lib/api/retryBudget.test.ts -t 'malformed caller retry counter'` failed: a malformed `-Infinity` counter let the request succeed on attempt 6. After validation, it failed after 3 as intended.
- Controlled adapters and fake timers also covered direct recovery and exhaustion, browser and server QueryClients, 502/504, network errors, timeouts, permanent 4xx/503, POST/PATCH/DELETE, active-request cancellation, backoff cancellation, and preservation of a successful payload containing a sourced zero, null withheld value and metadata.
- `./node_modules/.bin/tsc --noEmit --pretty false`: passed.
- `./node_modules/.bin/jest --runInBand __tests__/lib/api/retryBudget.test.ts __tests__/lib/api/retryBudgetServer.test.ts __tests__/ssrPrefetchCancellation.test.tsx __tests__/lib/api/axios.test.ts __tests__/lib/api/audits.test.ts __tests__/lib/api/counties.test.ts __tests__/auditsSsrHydration.test.tsx __tests__/transparencySsrHydration.test.tsx __tests__/federalTopStatedFindings.test.ts __tests__/debtSsrPrefetch.test.tsx __tests__/countiesSsrHydration.test.tsx __tests__/hydratedStaleRefetch.test.tsx __tests__/components/DataFreshnessBadge.absence.test.tsx`: **13 suites, 164 tests passed**.
- ESLint on every changed frontend file and new helper/test files, plus `git diff --check`: passed.

## Boundary and follow-up

Current production query callers have no explicit `retry` override. Exported hooks still accept `options.retry`, and a future caller could use it to repeat an entire three-attempt Axios request; a controlled `fetchQuery({ retry: 1 })` made six HTTP attempts. Keep the shared no-retry policy when adding queries. This is an API-surface risk within issue #357, not an observed current production caller.

HTTP cancellation stops client attempts and wait timers. It does not prove that a database query already running behind the server request stops. No production database or environment file was accessed, and these tests do not attribute historical Supabase egress.
