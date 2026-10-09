# Compact ETL UI verification receipts

Product: `6087347edf1412d232302f986166c889403d17da`.
Final tests: `dba511b9fec01ce63843fe576ef20f6e2539375a`.
Pinned base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`.
See [handoff](../BATCH_7_ETL_UI_HANDOFF.md) for scope, source and gate limits.

## Accepted command entrypoints

Working directory is the owned worktree's `frontend` unless indicated.
Node path is `/Users/roger/.nvm/versions/node/v22.19.0/bin`.
Jest runs use a clean environment with `NEXT_PUBLIC_API_URL` set to inert
`http://127.0.0.1:8162` and telemetry disabled; fixture Supabase variables are
excluded from Jest. Per-run cache directories were owned under `/tmp` and are
removed. The following commands reproduce the accepted checks with the same
runtime and flags that determine the checked scope:

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 \
  node node_modules/jest/bin/jest.js --runInBand

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 \
  node node_modules/typescript/bin/tsc --noEmit --incremental false

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 \
  node node_modules/next/dist/bin/next lint \
  --dir app/admin/etl --dir e2e/batch7-etl-ui \
  --file lib/admin/etlDispatch.ts \
  --file __tests__/batch7_etl_ui.test.tsx \
  --file __tests__/batch7_etl_ui_parsers.test.ts \
  --file __tests__/batch7_etl_ui_adversarial.test.tsx --max-warnings=0

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 \
  NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8162 \
  NEXT_PUBLIC_SUPABASE_ANON_KEY=batch7-inert-anon \
  REVALIDATE_SECRET=batch7-inert-revalidate \
  node node_modules/next/dist/bin/next build

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  HOME=/Users/roger NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 \
  BATCH7_ETL_UI_ARTIFACTS=/Users/roger/.codex/visualizations/2026/10/09/01a11f2c-fa93-7441-9107-010ba2a08dd8/batch7-etl-ui/browser-accepted \
  node node_modules/@playwright/test/cli.js test \
  --config=e2e/batch7-etl-ui/batch7-etl-ui.config.ts
```

The browser requires the owned fixture and production Next server. They were
stopped after acceptance. Equivalent fixture replay command, from owned root:

```sh
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch7-etl-ui/audit_app/backend/tests \
  /Users/roger/Documents/projects/audit_app/venv/bin/python \
  -m uvicorn batch7_etl_ui_fixture:app --host 127.0.0.1 --port 8162
```

Use the build environment above with `next start --hostname 127.0.0.1 --port
3162` in another owned process. These are inert UI fixtures, not product
backend/worker or PostgreSQL acceptance commands.

## Actual outcomes and raw receipts

The external root and its manifest SHA256 are pinned in
[artifacts.json](artifacts.json). Paths below are relative to that root.

| Receipt | Outcome |
| --- | --- |
| `raw-logs/baseline.txt` | Pinned baseline: 206 pass, 10 suites |
| `raw-logs/red-rendered.txt`, `red-browser.txt` | Old page missing new Run Now control; expected failures |
| `raw-logs/parser-red.txt` | Retained UTC chronology/order failure before repair |
| `raw-logs/renewal-red.txt`, `renewal-green.txt` | Rendered same-actor null-profile recovery failure then green |
| `raw-logs/filter-red.txt` | Sequential filter overwrite reproduced before repair |
| `raw-logs/adversarial-red.txt`, `adversarial-green.txt` | Initial hostile receipt failures then repaired behavior; final independent expanded replay is in reviewer manifest |
| `raw-logs/compatibility-final.txt` | 337 pass, 13 suites; predates final two extra filter tests |
| `raw-logs/full-jest-final.txt` | 2,063 pass, 1 existing skip; 147 suites; exit 0 |
| `raw-logs/types-delivery.txt` | Empty successful output; exit 0 |
| `raw-logs/lint-delivery.txt` | Zero warnings/errors; exit 0; Next deprecation notice |
| `raw-logs/build-final.txt` | Successful production build; exit 0 |
| `raw-logs/browser-accepted.txt` | Final 24/24 Chromium journeys, 54.9s; exit 0 |
| `browser-accepted/**.png` | Settled desktop/mobile/terminal/disabled states |
| Earlier `browser-*` traces and `raw-logs/browser-*.txt` | Retained intermediate failures, not final acceptance |
| `raw-logs/full-jest.txt`, `retry-budget-control.txt` | Two unchanged cases failed with fixture auth env; clean control 19/19; final full suite green |

Independent reports retain their exact commands, immutable original-source
replays, hashes and final content identities:
[Standards](standards-review.md), [Spec](spec-review.md),
[Adversarial](adversarial-review.md). Their counts overlap author checks.
No unresolved concrete review finding remains. The Standards duplication
judgment is nonblocking and is recorded separately from documented violations.

Cleanup check executed after stopping both owned servers:
`lsof -nP -iTCP:3162 -iTCP:8162 -sTCP:LISTEN` returned no listeners.
Owned `/tmp/batch7-etl-ui-jest-cache` and Python bytecode cache were removed.
The scoped source credential-pattern scan found zero matches across 17 files;
this is a local pattern scan, not a hosted security verdict. Git diff/staged
whitespace checks passed. Whole-repository hosted security/coverage/deployment
gates remain unexecuted; Actions is disabled as captured in
[issue-accounting.json](issue-accounting.json).
