# Critical admin paint regression

This credential-free component fixture imports the actual PageShell and global
stylesheet. It freezes `.ledger-enter` at the first animation frame, making an
unwanted initial fade deterministic. It does not import an auth provider, start
an API/worker, or certify production LCP/CLS. Public routes and `/administrator`
are controls that retain the existing animation. The imported global stylesheet
retains its existing external Google Fonts import; this fixture is not a
network-isolation test.

From `frontend`, prepare a fresh directory outside the checkout, then start it
with the existing Next runtime (no installation):

```sh
node browser-fixtures/admin-paint/prepare.mjs /absolute/fresh/fixture
NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next dev /absolute/fresh/fixture --hostname 127.0.0.1 --port 33610
```

In Chrome, open `http://127.0.0.1:33610/admin/etl`. The heading and working content
must have combined ancestor opacity 1, even with the animation timeline held.
With the entrance class present, they render at opacity 0.01. `/counties`,
`/administrator` and `/status-extra` must still have opacity between 0 and 0.1.
Repeat `/admin`, `/admin/social/new` and `/admin/social/example`, plus the
administrator-only `/status` page. Do not use an authenticated production URL
for this fixture. Reset any temporary viewport and stop the owned server afterward.

The same cases are available in the separate browser runner:

```sh
ISSUE774_PAINT_URL=http://127.0.0.1:33610 node node_modules/playwright/cli.js test --config browser-fixtures/admin-paint/playwright.config.ts
```

Jest's existing policy excludes browser-fixtures. The generated source receipt
binds the selected files and producer bytes; it does not authenticate a remote
deployment or declare a performance pass. Retain browser results separately.
