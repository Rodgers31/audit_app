# County explorer year metadata layout

Frozen source: `3f3b1f1981b93c3317e204defbd235121c1df084`. Related roadmaps: #545 and #481. This follow-up preserves the #669 metadata transfer, #673 cache capacity, and #674 detail reservations.

## Reproduced defect and correction

The explorer receives the county list through SSR hydration, but fetches fiscal-year metadata on the client (`CountiesPageClient.tsx`, `useCountyFiscalYears`). The header previously omitted the entire year label/select until that independent request returned. In native Chrome at 390 CSS pixels, inserting it moved the export button and every following section down 28 pixels. A production reload recorded a non-input layout-shift entry of 0.122675643 at 907ms. A local replay using the real Next.js app and an inert API with a four-second metadata delay reproduced the same movement and shift value.

Keep the existing year field mounted at a stable width before and after metadata arrives. While no years exist it is invisible, aria-hidden and disabled; it neither offers an empty picker nor invents a reporting year. Existing selected-year queries, source qualifications, financial mappings, paging, filters and navigation code are unchanged. Empty/error metadata deliberately retains the blank reserved footprint.

## Same-input comparison

Node22.19.0, frozen lock (Next15.5.27, React19.2.4, Jest30.5.2), existing logged-in Chrome through cua_repl. Local app uses synthetic twelve-county data, a four-second fiscal-years delay, and loopback-only services. Measurements use buffered native PerformanceObserver entries and DOM geometry; no new browser transport or hosted measurement service.

| Measurement | Baseline | Fixed |
|---|---:|---:|
| 390px header bottom before metadata | 321.890625px | 349.890625px |
| 390px header bottom after metadata | 349.890625px | 349.890625px |
| Picker-induced non-input shift entry | 0.122675643 | none observed |
| Metadata request duration | 4004ms | 4006ms |
| Fixed 1280px header bottom before/after | — | 248.4921875px / 248.4921875px |
| Fixed 1280px export top before/after | — | 175.4921875px / 175.4921875px |

The development baseline included initial compilation while the candidate was warm. Its navigation timing is therefore **not** a latency improvement comparison. The same delayed-response geometry comparison isolates the insertion defect. At 355px the longest offered partial-year label remained usable without horizontal document overflow. The desktop page-two detail/back roundtrip retained URL `?p=2`, the same rows, and scroll1170.5px exactly. The detail payload in that fixture is synthetic, not financial-equivalence evidence.

## Bounded production observations and limits

The first county document transferred 99,468 bytes (2,712,334 decoded), TTFB19ms and FCP1448ms. A narrow repeat document had TTFB22ms and FCP448ms; its fiscal-years request started742ms and lasted151ms, producing the reproduced shift. These are fresh/repeat browser navigations, **not** a certified cold-backend/cache experiment. No cache purge or production mutation occurred.

The narrow budget sample had TTFB29.5ms, DCL656ms and heading LCP660ms; freshness took1946ms and annual-reports1711ms after hydration. The narrow detail001 sample showed the skeleton then the county heading (2556ms); DCL2520ms, fiscal-years144ms and accountability1180ms after hydration. Its accountability shift was0.000483324. Warm desktop samples: budget TTFB297.5ms/DCL1153ms, detail TTFB82ms/DCL1358ms. These bounded observations did not reproduce the historical large budget/detail shift. They do not prove those routes universally stable.

Native DevTools docking itself generated large recent-input shifts; those are excluded from page-load interpretation. Repeated small header-auth shifts are outside this lane. Some LCP entries lacked a retained element and are unattributed; browser extensions were present. No main-thread CPU trace or representative device/network distribution was obtained, so navigation-to-paint intervals cannot be attributed solely to React hydration/render work.

The supplied dated field screenshot (county LCP13.26s from two visits; desktop county/budget/detail CLS0.44/0.46/0.46; homepage mobile0.21 from one visit) remains sparse historical evidence. This patch addresses one reproduced layout source. It does not establish representative field improvement or resolve #545/#481. The full county document remains large; payload/projection and backend latency work needs separate equivalence and transfer evidence before cross-boundary changes. Private auth data is not aggregate-cached.

## Verification and release gates

- New two-case regression observed failing on frozen source under locked Jest30.5.2, then passing after the fix.
- Ten targeted hydration/year/paging/detail/budget-selection suites:87 passes, zero skips.
- A broader path-pattern command matched the worktree's `county-performance` absolute path and therefore ran all155 frontend suites:2195 passes, one existing optional PostgreSQL HTTP-capture skip. Do not sum overlapping runs. No capture was fabricated to satisfy that prerequisite.
- TypeScript, focused lint and production Next.js build pass with inert configuration. The build exercises compilation/prerendering; unsupported fixture API routes return404, so it is not full backend-route acceptance.
- Existing detail-layout test needed an honest nullable fiscal-year fixture annotation and named test doubles for its type/lint checks. Assertions and runtime values were retained.
- Independent spec review:31 passes including four new executable cases. Independent standards review:seven new cases plus four detail-layout cases pass. No actionable findings; jsdom does not measure layout or screen-reader behavior.

Detailed source hashes, command receipts, screenshots, fixture server and independent executable reviews are in the lane evidence directory referenced by the batch coordination contract. Initial dependency/CORS/test-path setup failures are retained there and excluded from acceptance. Exact frozen dependencies were installed after an offline-cache miss; no manifests or lockfiles changed.

Stop at a reviewed draft PR. Coordinator integration, current remote review/check state, production rollout, repeated field observations, low-end-device CPU traces, long-session/cache behavior and the broader operational roadmaps remain gates. No production deploy, paid resource/reviewer, hosted Actions, financial source edit or publication/upload/native/retained-write activation is part of this work.
