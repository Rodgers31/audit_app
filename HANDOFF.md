# Batch 15 performance/dependencies — partial implementation

Date: 16 October 2026 (Chicago). Worktree `/Users/roger/.codex/worktrees/b15-performance/audit_app`; branch `codex/b15-performance`; accepted base `06896185005d822c4b29888138b984510dd1fdbd`. Implementation commit `b8c76a859bc7fab2c9340ab332f4e6b806c30747`; draft PR [#701](https://github.com/Rodgers31/audit_app/pull/701). Final publication HEAD is recorded in the shared `FULL_PLAN_COMPLETION_B15/lane/performance-status.md` after publication. Primary dirty checkout remained untouched; an existing external Python runtime was read-only.

## Implemented and tested

`frontend/app/reset-password/page.tsx` now reserves a full viewport during auth loading, matching its existing Suspense and ready-form states. Previously its 60vh spinner brought the footer into view, then moved it out when auth settled. No auth/session/submission behavior or ready design changes. The two other minimum-height states on this route already use `min-h-screen`; this is the only 60vh occurrence found on the route. No shared auth guard changes.

The standalone Chrome fixture in `frontend/browser-fixtures/reset-loading` pauses the actual profile request, requires the visible loading spinner, measures the footer, releases the request and requires the ready form. Desktop1365×900 and mobile390×844 fail against the original production build (footer y540 and506.390625) and pass against the repaired build. The test submits no password. Its local API reuses the existing external-HTTP-blocked, startup-disabled disposable SQLite fixture. All identity/financial data are synthetic.

Source-bound local Chrome observations with1800ms delayed browser API/profile reads are retained in `docs/admin/implementation/batch15-performance-evidence/{baseline-bound,candidate-bound}.json`. Fresh Chrome contexts, same1365×900 viewport, reduced motion, installed Google Chrome155.0.8059.80. These are laboratory observations, not field CWV or provider billing. The generator records selected tracked source hashes before/after and the build ID; original bytes are retained as `measurement-generator.cjs.txt`. This inventory is not a complete environment/backend/third-party attestation.

| Route | Baseline layout-shift sum | Candidate sum | Interpretation |
| --- | ---: | ---: | --- |
| `/reset-password?recovery=local-test` |0.2113987569342881|0.00040974594527708083|Visible footer intrusion repaired. The sum is not the session-window CLS metric. |
| `/counties` |0.0001381618788212195|0.0001381618788212195|No redundant county-list fetch after hydration; fiscal-years/freshness reads remain. |
| `/` |0.0001381618788212195|0.0001381618788212195|No demonstrated loading/layout defect requiring a change. Synthetic national-debt503 remains an unavailable-data path. |
| `/admin` |0.03775299279475104|0.03775299279475104|Auth-loading/error-view observation only. Synthetic backend rejects the inert JWT; this is not healthy-admin acceptance. |

The largest session-window CLS derived from the raw shift timestamps is0.10590425143978259 baseline /0.00040974594527708083 candidate (reset route).

Reset LCP was1916ms baseline /2344ms candidate: auth still delays the form; no LCP speedup is claimed. Root LCP64/60ms; county128/120ms; admin64/48ms. Single-run timing differences do not establish a speedup or production causality. No screenshot/sample from Vercel was treated as causal evidence. Two profile reads occur in the synthetic admin journey; event/lifetime/role-refresh semantics were not changed without a causal regression. No database overfetch or audit pagination defect was reproduced in this lane.

## Dependency disposition

No manifest, lockfile, repair contract or dependency version changes. Current official GHSA-vfj7-8cjw-p6xm still lists braces<=3.0.3 and no patched version; npm metadata reports latest3.0.3. Raw GitHub API/advisory bytes and fresh audits are retained. Full audit:7 high propagated package entries, one advisory root; production audit:0. These counts do not establish exploitability or an accepted exception. Existing bounded repairs and sprintf retirement remain in force. No forced major override, lockfile wipe or scanner weakening.

Real normal lifecycle installs passed in this worktree and a separately archived accepted-base frontend, with `ONNXRUNTIME_NODE_INSTALL=skip`, dev and optional packages included. Node22.19.0/npm11.6.0, macOSarm64. `npm ls --all --json` in the worktree returns1 with two Sharp/WASM optional descendants called extraneous and pretty-format27.5.1 called invalid for `^27.0.2`; the separate clean archive returns0 but lists the same two extraneous descendants. The manifest, lock, hidden install lock and relevant pretty-format/DOM package bytes compare equal between installations. Direct Arborist reports that edge valid, and semver says27.5.1 satisfies the declared range. This discrepancy is unresolved; a clean graph gate is **not** claimed. It did not justify changing dependency ranges. Both raw npm reports remain retained under #494's qualification boundary.

## Commands/results

All run from the owned checkout unless explicitly described; full logs are in the evidence directory and external packet.

- `ONNXRUNTIME_NODE_INSTALL=skip npm ci --include=dev --include=optional --no-audit --no-fund`: exit0 (899 packages, seven reviewed repair files). Separate accepted-base archive install also exit0.
- `npm run test:dependency-boundaries`: exit0,133 Node controls plus9 runtime controls, zero skips. These cohorts overlap other checks and are not summed with unit totals.
- `npm run verify:dependency-tooling`: exit0; actual parser/theme/typography/nesting behavior passes.
- `npm run build` with explicit loopback API/Supabase and inert anon value: final exit0; lint/type/build complete. First candidate build failed because reducedMotion was at the wrong Playwright config level; moved it into contextOptions, retained failed log, reran the complete build.
- `node node_modules/playwright/cli.js test --config browser-fixtures/reset-loading/playwright.config.ts --reporter=line`: original production source2 failures; repaired source2 passes. Original bootstrap-only test wrongly passed before the meaningful auth hold was added; that diagnostic is retained externally and is not the regression claimed here.
- `npm test -- --runInBand`:155 suites pass;2195 tests pass /one existing skip. Actual baseline/current Jest discovery lists both contain the identical155 files, excluding the new standalone browser fixture through existing runner policy.
- Actual Next/Transformers sharp0.35.5 PNG roundtrip/pixel checks pass; ORT1.30.0 native module imports. Full inference not rerun: validated model cache absent; no model/service charge or external inference used. No fresh Linux/native-target/browser-WASM qualification is claimed.
- `git diff --check`: product/fixture/docs source passed before raw-log import. Raw stdout/stderr retains its original control characters, CRLF and trailing whitespace; the evidence-only `.gitattributes` disables text conversion to preserve exact bytes. Source whitespace check excludes these raw `.log` artifacts explicitly. No operator guard changed. Independent API-fixture isolation/cleanup checks execute under normal and optimized Python.

Retained setup failures: primary Python runtime lacked requests; an older external runtime lacked dotenv; third existing runtime successfully ran the actual source fixture. First production build completed with the API absent and is diagnostic only; it was rebuilt with verified fixture readiness before the reported baseline. Initial CORS fixture error redirected admin home; corrected fixture replay is the bound baseline. First native probe used a non-exported Transformers package.json subpath; corrected smoke uses the supported module entry. None is a product pass. External raw logs are at `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/performance`.

## Independent reviews

Spec: `batch15-performance-evidence/spec-review/report.md`, no blocker in this limited increment; original2 browser cases pass, forced60vh mutants fail, profile503 explicitly outside auth acceptance. Standards: `batch15-performance-evidence/standards-review/REPORT.md`,0 actionable findings; original2 pass,3 hostile controls fail as intended, real API isolation/CORS/external-egress/cleanup checked under normal and optimized Python. Reports retain exact reviewed hashes, commands and outputs. No paid/bot review was requested. Fresh remote readback on draft #701 found zero inline comments, zero review bodies, zero issue comments, no requested reviewer and no closing-issue references; final readback is recorded in shared status.

## Original requirements still remaining

- #481/#545: representative closed-day Vercel/hosting/egress/workload attribution, sustained headroom and production root/county/reset/admin performance acceptance are coordinator-owned external work. Local synthetic shifts do not establish billed savings. Healthy-admin delayed-response and auth-event tracing remain unqualified here; no broader performance completion claim.
- #494: no supported patched braces release; residual advisory remains blocked, not waived. Installed-graph discrepancy, complete target-platform/native-model qualification and integrated/hosted checks remain. This lane does not replace those requirements with a scanner or small native smoke.
- #611: genuine production UI page-boundary acceptance remains. No manufactured events, production mutations or pagination code changes.
- Full original admin/social product and operational completion are not established by this increment. Other lanes retain their contract ownership.

## Shared edits, dependencies and resources

Shared product edit: reset-password route only. New standalone fixture/test/config/README plus evidence/handoff docs. No package/lock/config outside that standalone test, migration, API registration, social UI or runtime flag changes. No peer checkout changes. Build cohort released after final build; owned loopback Next33508/API33518 were stopped cleanly and both listener checks were empty; DB55404 unused. A final supported-fixture replay is recorded in shared status. The shared status records final cleanup, source HEAD and PR. Publishing/uploads/Actions/automatic previews remain outside this lane; Actions readback was false. No deploy, merge, policy override, paid resource, hosted build, provider operation or bot request.
