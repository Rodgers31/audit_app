# PR #576 authorization-refusal repair

Reviewed original: `3a3daba6e03bfffdcec9769c0f41c3ffdb084cbc`.
Copilot inline comment: `4227288028`, thread `PRRT_kwDOPmNsm86qq6Ud`.

The finding is **valid for a first submission**: `rejectAccess` advances the
epoch and aborts the controller, so the following lifetime check returned before
the submitted key was cleared. The fix classifies and retires a definite
first-submission refusal before invalidation. The suggested unconditional clear
needs a narrower rule for recovery: denying a later recovery cannot establish
that the original ambiguous command was never accepted. Recovery failures retain
the original key, without an automatic POST or a fresh key for the same intent.

## Execution and retained evidence

Receipts are under the coordinator's external directory:
`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_7_REVIEW/`.
`UI_REPAIR_RECEIPTS.json` records source hashes and log hashes/sizes.

| Receipt | Executed result |
| --- | --- |
| `UI_REPAIR_BASELINE.txt` | Original three ETL suites: 133 passed |
| `UI_REPAIR_RED.txt` | Final retained tests on the pinned original component: 2 failed at unwanted Recover same intent, 10 controls passed; exit 1 |
| `UI_REPAIR_GREEN.txt` | Same twelve cases on repaired source: 12 passed; exit 0 |
| `UI_REPAIR_AMBIGUOUS_RECOVERY_RED.txt` | An intermediate unconditional-clear experiment failed both refused-recovery controls; exit 1 |
| `UI_REPAIR_FULL_JEST.txt` | 147 suites / 2,077 passed / 1 existing skip; exit 0 |
| `UI_REPAIR_TYPES.txt` | TypeScript `--noEmit --incremental false`; exit 0 |
| `UI_REPAIR_LINT.txt` | Scoped owned UI/parser/test/browser files, zero warnings/errors; exit 0 |
| `UI_REPAIR_BUILD.txt` | Production Next build; exit 0 |
| `UI_REPAIR_BROWSER.txt` | 28/28 actual Chromium journeys, 1.1 minutes; exit 0 |

`UI_REPAIR_HISTORICAL_OVERBROAD_*` logs are exploratory tests superseded after
the original-ambiguity requirement was checked; they are not final acceptance.
Final old-source replay temporarily substituted only the original owned
`DispatchPanel.tsx`, then restored the repaired bytes in a `finally` block.

The rendered fixture runs real AdminGuard, useAdmin, useOperationsAccess,
useEtlAccess, React Query and the UI, with inert auth evidence and HTTP transport.
It exercises first 401/403 refusal, null-profile guard unmount and same-actor
renewal, then asserts recovery is absent and an explicit new submission changes
the key. Controls retain the original key through network/500/503/malformed-202
responses and through a refused recovery. Browser controls first commit one
fixture command, drop its response, refuse recovery, renew, and retrieve the
same receipt with the same key and exactly one accepted command.

All checks used clean `env -i` environments and Node 22.19.0. Entry points:
`node node_modules/jest/bin/jest.js --runInBand` (targeted red/green adds
`--runTestsByPath __tests__/batch7_etl_ui_adversarial.test.tsx
--testNamePattern='review regression|review control'`);
`node node_modules/typescript/bin/tsc --noEmit --incremental false`;
`node node_modules/next/dist/bin/next lint` with the original owned-file scope;
`node node_modules/next/dist/bin/next build`;
`node node_modules/@playwright/test/cli.js test
--config=e2e/batch7-etl-ui/batch7-etl-ui.config.ts`.
The original README records the inert build/fixture environment. Manifests and
lockfiles matched the read-only dependency runtime exactly before use; no install
occurred. The primary checkout and dotenv files were not loaded or changed.

## Invariant and entrypoint inventory

`rememberSubmittedIntent` has one product caller: `execute`. Dry Run, confirmed
Run Now and the explicit recovery button all use that function. `begin` treats
the same source/mode after an ambiguous result as recovery, retaining the key;
an explicitly changed source/mode rotates it as specified. Both clear sites are
inside `execute`: accepted validated acknowledgment, and a definite first
refusal. `useEtlAccess` GET denial invalidates private evidence but cannot erase
an unresolved POST; a denied read does not establish command absence. The
initial lifetime/controller check still rejects stale POST continuations before
they alter current UI or browser intent state. Existing forced interleavings
cover actor changes, same-actor role/profile/SDK renewal, hidden pages and
unmount for POST, receipt GET, history GET and deferred confirmation. Existing
hostile parser cases executed in the full suite.

## Frozen source and limits

ETL product SHA256:
`f32429392c5c5dd4130891020a3e0f19db804ba6c542e9cd8f9ea43d632c87fc`.
Construction: for each sorted tracked file under `frontend/app/admin/etl` and
`frontend/lib/admin/etlDispatch.ts`, concatenate `path`, NUL, its SHA256 and
newline, then SHA256 that sequence. DispatchPanel SHA256:
`c0e5a8244eb96ef6808b9810bce99f47edc61c46bf86b8741f87a294cf77b82e`.
Later changes in the repair commit concern receipts/documentation only.

Both owned servers (3162/8162) stopped after replay. The browser fixture remains
synthetic: worker/PostgreSQL/audit fencing and full hosted CI are not certified.
Copilot's body-only integration/gate observations describe these real remaining
limits. No new out-of-scope finding was confirmed; #568 covers the repair.
The coordinator owns actual worker integration, independent final replay,
GitHub deduplication/accounting, push, in-thread response/resolution and merge.
