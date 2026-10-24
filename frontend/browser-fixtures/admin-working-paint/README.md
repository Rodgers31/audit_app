# Admin working-content paint fixture

This imports the actual overview/ETL route modules, AdminLayout, AdminGuard,
PageShell, Framer Motion, stylesheet and query hooks. Auth, Axios and the
Supabase client are replaced at build time with inert local modules. No real
account, API, command runner or credential is needed. Every write refuses.
The stylesheet retains its external Google Fonts import.

Prepare two fresh **external** directories from `frontend`, using an existing
supported Node/Next dependency tree. No package installation is performed:

```sh
node browser-fixtures/admin-working-paint/prepare.mjs /absolute/fresh/before frozen
node browser-fixtures/admin-working-paint/prepare.mjs /absolute/fresh/after
NEXT_PUBLIC_API_URL=http://127.0.0.1:34974 NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build /absolute/fresh/before
NEXT_PUBLIC_API_URL=http://127.0.0.1:34974 NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build /absolute/fresh/after
```

`frozen` reads only the two route modules from
`924f1a4f27e1952f97d2291d8878d88603132237`. Both variants share unchanged
dependencies from the current source. Inspect `fixture-source.json` and the
actual base diff before attributing a comparison. A receipt hashes the selected
source and producer; it does not attest a deployed artifact.

Serve each build **sequentially**, checking the owned port first:

```sh
NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next start /absolute/fresh/before --hostname 127.0.0.1 --port 34970
```

In the authorized actual Chrome session visit `/admin` and `/admin/etl`. After
the inert 200 ms access restoration, the DOM-visible `#fixture-measurements`
records the required card-label inventory, each first-frame ancestor opacity,
time from the first observed working-content frame to full observed opacity,
viewport, visibility, paint events and all LCP candidates observed during its
bounded window. It resets its inventory on SPA route changes. Empty, incomplete
and unsupported inventories cannot certify visibility. It stops after 4 seconds
or 1.8 seconds of working-content observation, whichever comes first.

Stop that owned server and serve `after` on the **same** origin/port; use the same
routes, viewport, cache and browser. Do not treat background/occluded or
concurrently compiling recordings as foreground timing evidence. Never operate
another task's browser window or transfer a production session to this fixture.

These are synthetic **opacity** observations. Full opacity is neither data-ready
time nor end-to-end latency. Fixture chrome can be FCP; the page heading or an
extension image can be LCP. No FCP/LCP, provider latency, billed savings or field
acceptance verdict follows from the card measurement. Preserve all candidates
and failed setup attempts; do not filter telemetry.

Useful inert cases: `?auth=restoring`, `?auth=citizen`, `?auth=expired`,
`?data=slow`, `?data=failed`, and `?data=cancelled`. The unprivileged cases must
never mount working content or start route reads. Do not click production
controls to obtain timing. Remove owned build directories/processes after use;
retain source receipts and sanitized observations separately.

Executable normal-suite coverage is in
`__tests__/admin-auth/working-content-paint.test.tsx`,
`b66-spec-review.test.tsx`, and `b66-standards-review.test.tsx`.
