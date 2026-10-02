# Original browser suite — issue #291

Run from `frontend` with Node 22 and backend requirements installed:

```sh
npm ci
npx playwright install --with-deps chromium
npm run test:e2e:legacy
```

Set `BROWSER_TEST_PYTHON` when Python is not available as `python`. The command
builds production Next.js and starts its own frontend on 127.0.0.1:3141 and API
on 127.0.0.1:8141. Occupied ports fail instead of reusing another service.
The build refuses frontend dotenv files. Children receive allowlisted environment
variables, synthetic API/auth values, and no inherited provider configuration.
The API disables dotenv and Pydantic files before application imports, uses
production readers against disposable SQLite, blocks external HTTP, and disables
bootstrap and warmup. The 47 counties, two fiscal periods, fiscal totals, findings,
and source documents are explicitly synthetic; these checks certify application
behavior, not Kenya's published finances.

Per-test national debt responses exercise the modern observation contract. SSR
prefetch is deliberately unavailable for that endpoint so browser responses are
actually read. County failure tests select a different period before intercepting
the response; initial SSR data cannot silently make a failed browser read pass.
Both populated and empty unaccounted-finding responses execute unconditionally.

`ci.yml` prepares this command on the workflow's existing PR/main triggers, adds
it to the required quality gate, and retains JSON, HTML, screenshots, videos and
traces on failure. The focused publication acceptance job remains separate and
unchanged. The Docker workflow uses the same command. Actions remained disabled
through this work; no GitHub run was requested.

## Local evidence — 2 October 2026 UTC

The original config first failed test collection because device descriptors set
`defaultBrowserType` inside describe-level `test.use`. After fixing only collection,
the original Chromium baseline ran 190 cases in 25 files against the built app:
142 passed, 47 failed, 1 dataset-dependent skip, 0 flaky. The five original debt
cases again had four failures. This is a fresh baseline, not the inherited February
or September workflow result.

The final canonical runner started at 15:51:16.050Z: **170 passed, 20 named
quarantines, 0 failures, 0 flaky**, in 68.965 seconds including its owned server
setup and production build. All 190 cases remain represented in the same 25 files.
Current routes, selectors and data contracts replace stale assumptions. Checks
include 10B allocation / 6B spending / 60% execution, 50 debt service / 100 revenue,
150 framework spending, 20 + 5 + 25 financing, 180 current gross approved budget,
and cited synthetic findings without inventing missing amounts or lender splits.

A valid FY2024/25 response displayed 8.0B and passed. Deliberately changing the
same consumed financial response to 1.0B failed the 8.0B assertion and exited 1,
with screenshot, video and trace. Independent probes also verified failures for
an impossible assertion, missing browser, no matching tests and failed Next build;
a failed build never started Next. Extracted quality-gate shell execution passed
only `success` and failed `failure`, `cancelled` and `skipped` legacy results.
TypeScript, frontend lint and the real production build passed locally.

Local Python was 3.13; prepared CI uses 3.12 on Ubuntu. Final approved CI is still
required on the consolidated commit. No claim of a successful remote run is made.

## Named quarantines

All remaining cases are individually `test.fixme`, not ignored files or describes.
Tracking remains **#291 until the coordinator transfers each remaining behavior
into durable follow-up tracking before closing that issue**. Missing product
controls are not replaced by tests that merely find an SVG or arbitrary button.

| File | Exact case | Reason |
| --- | --- | --- |
| api-failures.spec.ts | /counties/001 — handles failed browser reads without certifying unavailable data | Failed lazy Follow the Money read leaves a blank panel without an unavailable state. |
| charts.spec.ts | chart legend is interactive | Current county rankings table/map has no interactive chart legend. |
| charts.spec.ts | debt chart segments are clickable | Current debt chart has no segment drilldown. |
| charts.spec.ts | county chart tooltips show category details | Total-only source rows provide no sector split; totals and honest absence are checked separately. |
| charts.spec.ts | chart zoom controls work | No zoom controls exist. |
| charts.spec.ts | chart can be exported or downloaded | Export PDF invokes printing; there is no download contract. |
| charts.spec.ts | charts have ARIA labels | Cost chart SVG has no accessible application role/name. |
| charts.spec.ts | chart data is available in table format | No chart-to-table toggle exists; county tables are tested independently. |
| charts.spec.ts | charts support keyboard navigation | Cost chart has no keyboard activation handler. |
| error-states.spec.ts | handles missing required fields in API response | Missing County.name reaches sorting/rendering without schema validation. |
| home-map.spec.ts | map integrates with county slider | The former quick slider is no longer mounted. |
| home-map.spec.ts | map is keyboard navigable | Geographic paths have pointer handlers but no keyboard activation. |
| learn.spec.ts | video cards are displayed | Current routes mount no video gallery. |
| learn.spec.ts | clicking video card opens modal | No video modal exists. |
| learn.spec.ts | video category filter works | No video category control exists. |
| learn.spec.ts | story cards can be expanded | Current stories are static prose. |
| learn.spec.ts | action steps are interactive | Current action steps are static prose. |
| learn.spec.ts | learn page has proper headings structure | Strengthened single-h1 check discovers two h1 elements; the old test only checked the first heading's visibility. |
| static-pages.spec.ts | /status — renders with a page heading matching /Status|ETL|Ingestion/i | Authenticated operator route redirects without an operator-auth fixture. |
| user-flows.spec.ts | clamp out-of-range page to last valid page | Current page-reset effect returns page 1 instead of clamped page 5. |

Issue #291 can close after consolidation, verified final CI and preserved follow-up
tracking for these exact quarantines. It does not require a production data write.
