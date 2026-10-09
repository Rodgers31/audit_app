# Independent adversarial verification — ETL UI

Origin: #568, backend companion #554, parent #545. Frozen contract: `BATCH_7_SESSIONS/SPEC.md` and `dispatch-contract-examples.json`, read before verification. Review skills: adversarial-verify and regression-fixture-on-fix. Primary checkout was not touched.

Initial source commit: `f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3`; pinned integration base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`. The first repair replay ran the author's working delta. Final independent replay ran exact committed product source `6087347edf1412d232302f986166c889403d17da`; its contents were not edited by this reviewer. The target-content hashes below identify that final source and the expanded review test.

## Executed findings and repair replay

The independent test file is `frontend/__tests__/batch7_etl_ui_adversarial.test.tsx`. Product source was changed by the author; this reviewer added only the dedicated tests and this report.

Corrected initial red run: **6 failures, 25 passes, 31 tests**, exit 1. Four concrete invariant failures were observed:

1. `parseCommand({...queued, created_at:'2026-10-09T12:00:00.000002Z', updated_at:'2026-10-09T12:00:00.000001Z'})` returned an accepted parsed receipt despite reversed chronology.
2. `parseDispatchCapability({...ready, timestamp:'2026-10-09T12:00:00.000001Z', worker:{...ready.worker,last_seen_at:'2026-10-09T12:00:00.000002Z'}}, Date.parse(ready.timestamp))` returned ready evidence with a heartbeat later than the evidence timestamp.
3. `parseCommandList` accepted creation timestamps `.000001Z`, `.000002Z` in that ascending order when the UUIDs were descending. The parser treated distinct microsecond instants as tied.
4. `commandProgress` accepted a previously completed receipt with version 4 and its existing `finished_at` rewritten from `12:00:03Z` to `12:00:04Z`.

The other two red cases exercised actual `CommandDetail`: the malformed microsecond completed receipt displayed its ingestion-observation link; a refresh with a rewritten terminal finish stayed visibly completed. These were rendered behavior failures, not source-string assertions. One earlier test fixture mistakenly uppercased an all-digit UUID; that fixture was corrected before the retained 6-failure run and was not reported as a product defect.

The author repaired all inter-field/progress/history comparisons to preserve the extra three microsecond digits and froze an already recorded `finished_at`. The same six cases passed after repair. Final expanded independent replay: **42 passes, 42 tests**, exit 0. No unresolved defect was found in the executed cases.

## Forced temporal controls

Real `useAdmin`, `useOperationsAccess`, `useEtlAccess`, React Query, DispatchPanel, CommandDetail, CommandHistory and AdminGuard ran. Only auth evidence and HTTP transport were inert. Deferred promises forced actor change, same-actor privilege loss, profile renewal, SDK renewal with the same User object, hidden page and unmount before releasing each pending POST or GET.

- 24 forced cases covered late acceptance, deferred real-run confirmation, late detail GET and late history GET across the six transitions. Old requests aborted; old success/observation links were absent; deferred confirmations sent no POST.
- Current 401/403 GET responses removed prior receipt evidence and disabled access. An old-lifetime 401/403 could not deny a newly authorized lifetime. Static UI failure text withheld an inert private diagnostic marker.
- A lost response produced one POST even with QueryClient mutation retries configured to 5. Manual recovery retained the same UUID after renewal; changed Run Now/Dry Run mode rotated it.
- Actual AdminGuard profile revalidation unmounted DispatchPanel. The unresolved same-actor intent survived remount with no automatic POST; a different actor could not see recovery. The originating actor could manually recover the same key after returning.
- Initial hidden mount sent no private reads. Lease expiry while real-run confirmation was deferred sent no POST. Malformed, expired and failed worker refreshes disabled controls and hid prior panel success.
- Hostile input execution covered absent/null/empty objects and arrays, strings, boolean coercion, NaN, infinity, negative/zero numeric values, missing source keys, invalid/case-mismatched UUIDs, wrong intent, wrong acknowledgment booleans and page/page_size bounds. The parsers failed closed for the tested cases.

The chronology repair is shared by capability parsing, command parsing, list ordering and progress checks. Acceptance parses through `parseCommand`; detail and accepted-receipt reads run parsing plus `commandProgress`; history runs `parseCommandList` plus `commandProgress`. The terminal finish guard therefore applies to both receipt and history refresh paths. Filter/lifetime changes intentionally start a fresh observation scope.

## Commands and receipts

Working directory: `/Users/roger/.codex/worktrees/batch7-etl-ui/audit_app/frontend`.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 PYTHON_DOTENV_DISABLED=1 /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js __tests__/batch7_etl_ui_adversarial.test.tsx --runInBand --cacheDirectory /tmp/batch7-etl-ui-adversarial-cache
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin NEXT_PUBLIC_API_URL=http://127.0.0.1:8162 PYTHON_DOTENV_DISABLED=1 /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/typescript/bin/tsc --noEmit --incremental false
```

Final Jest result: one suite passed, 42 tests passed, no snapshots, 1.038 seconds. Final TypeScript result: exit 0 with no diagnostics. The test fixture's original Set iteration was replaced with `Array.from` to support this project's ES5 target before the final replay.

Raw outputs were archived outside git in `/Users/roger/.codex/visualizations/2026/10/09/01a11f2c-fa93-7441-9107-010ba2a08dd8/batch7-etl-ui-adversarial/` before the original temporary files were removed. The full receipt/source hash manifest is `manifest.json`, SHA-256 `0a58d38806a91920f510c3eb3361b4e898803da77e6d1932e4087b871714a37b`.

| Receipt | SHA-256 |
| --- | --- |
| `batch7-etl-ui-adversarial-red.txt` | `209c3374419373f9a886b985da6a8295879fca7b00435b209160d84a8a3c3f21` |
| `batch7-etl-ui-adversarial-final.txt` | `7c8f466e82a6d5e28d6243342d86e44e24e651395b129a80fc0266b602202de3` |
| `batch7-etl-ui-adversarial-types-final.txt` | empty successful TypeScript output |
| `batch7-etl-ui-adversarial-6087347-42.txt` | `5c29e063df930da229c1869b5537cfb5f0d97f14884930ac90b27a49fffd97a1` |
| `batch7-etl-ui-adversarial-6087347-44.txt` | `a50c7637881fcaf86c250663f8034b604b126d94f521cef058e08b8d350db3b4` |
| `batch7-etl-ui-adversarial-filter-red.txt` | `01d87ced9a791f8579885cc097ed6b89aff2cfc6278cadfd9da8f11f0b92f483` |
| `batch7-etl-ui-adversarial-6087347-types.txt` | empty successful TypeScript output |

Final reviewed content SHA-256:

| File | SHA-256 |
| --- | --- |
| `frontend/lib/admin/etlDispatch.ts` | `60376cdce3fbb49c735389be51fba75f3ed4919f2f6c96f73672152d0b0e6487` |
| `frontend/app/admin/etl/useEtlAccess.ts` | `edebdbb0b172325b59ff9f2a9dad3cf27f9325eb002aee703ac2e493e62e1481` |
| `frontend/app/admin/etl/DispatchPanel.tsx` | `91c9ecac3df7e240ca5587604d40abdbe8bcd320912a36cef2c88be143f46ab0` |
| `frontend/app/admin/etl/useCommandReceipt.ts` | `c438cf221559de6150aed62950e5815c42d63d0ca4d2ed8ef080e16ee0d183f6` |
| `frontend/app/admin/etl/CommandHistory.tsx` | `2736196589839991a13d17bb1cc99cf406c66b5cd5071e26f07e4d5bd6a6d2f2` |
| `frontend/app/admin/etl/submittedIntent.ts` | `3debdb7bf60d758ad8d1d0ecd0536f30fe1137f8c7d7f5a584a51fb48006f9c8` |
| `frontend/__tests__/batch7_etl_ui_adversarial.test.tsx` | `62d95c5c8c121ea0230284a20e41ae7a8bf41646d26205fc18dda6a305fe8375` |

## Exact committed-source replay and filter delta

On `6087347edf1412d232302f986166c889403d17da`, the unchanged original **42/42** independent tests passed, exit 0. Two additional rendered tests then exercised the final CommandHistory delta: sequential source/status/page-size changes before navigation completed, an intermediate older navigation completing while a newer filter intent remained pending, subsequent navigation completion, Clear followed immediately by another filter edit, and browser Back followed by an edit. The final expanded suite passed **44/44**, exit 0, in 1.022 seconds. TypeScript `--noEmit --incremental false` passed with no diagnostics after these additions. No new product defect was found.

The two filter tests were independently replayed against the actual original `CommandHistory.tsx` extracted from `f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3`. A Jest module mapper selected only that original component; all other product code and rendered interactions were unchanged, and no product file was mutated. Both tests failed for the expected observable routing defects: rapid edits sent `/admin/etl?page_size=50` instead of retaining source/status, and a filter immediately after Clear resurrected `status=failed`. The same tests passed against the committed current component.

The selective original-component replay used the Jest command above with these additional arguments (the extracted temporary source is retained in the external manifest):

```sh
--modulePaths /Users/roger/.codex/worktrees/batch7-etl-ui/audit_app/frontend/node_modules --testNamePattern 'adversarial rapid history filters|adversarial clear and browser back' --moduleNameMapper '{"^\\./CommandHistory$":"/tmp/batch7-etl-ui-adversarial-old-CommandHistory.tsx","^\\./CommandReceipt$":"/Users/roger/.codex/worktrees/batch7-etl-ui/audit_app/frontend/app/admin/etl/CommandReceipt.tsx","^@/(.*)$":"<rootDir>/$1"}'
```

Original component SHA-256: `37c138c9291c12b3a89a1aa17db53e117911bcd60012a3ffb8cbba6aaf7d65bf`. Selective red result: 2 failed, 42 intentionally skipped, exit 1. Final expanded replay ran without the module override and had no skipped cases.

## Boundaries and cleanup

This independently certifies the executed local UI/parser cases against inert transport; it does not certify product backend integration, a real worker lease/audit/JSONB claim, persisted ingestion identity, deployed readiness or hosted gates. The author owns actual browser fixture journeys and final browser/build controls; the coordinator owns combined worker replay. No GitHub mutation or issue closure was performed by this reviewer.

No server, database, provider, production environment, .env file, paid service or external HTTP transport was used. No port was bound; 3162/8162 remain the author's resources. No installation occurred and the dependency runtime was read only. After archiving and hashing receipts, the review-owned `/tmp/batch7-etl-ui-adversarial-cache`, raw temporary receipts and extracted temporary original component were removed. There is no running review process or active review resource to clean up.
