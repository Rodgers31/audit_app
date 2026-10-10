# Batch 10 county smart-back investigation — unresolved

Issue [#601](https://github.com/Rodgers31/audit_app/issues/601) remains open. This branch preserves a bounded investigation and executable evidence checks. It changes no application, navigation, original test, assertion, sleep, fixture, dependency or browser configuration. The historical post-back `scrollY=100` failure has not been reproduced causally. There is no supported product repair or observable test-contract correction to propose, so this lane does not create a repair PR.

## Source and original failure

Author base: `f6c31e271297eece52f34102dc40a1e2ed7069a8`, tree `69ddfad6deb814dd08fdaee2db2d512d73e14c78`. Historical failure: [run 38009357220, attempt 1, job 114085507802](https://github.com/Rodgers31/audit_app/actions/runs/38009357220/job/114085507802), actual commit `b70996e9e1e28f7e6b445f0d3c41be3681fadd61`. These are different executions. Relevant navigation/counties/layout/test/config/fixture bytes match between those commits; the archive verifies 386 consumed source identities against this checkout.

The preserved original trace SHA-256 is `75522647fc9dbe493b54c8670e79baabf8c67e1a2fc86f17886e9e67963572b4`. The original case is `frontend/e2e/smart-back.spec.ts:72`, with the unchanged `afterY > 100` assertion at line 100. Before the first county click, its evaluated Y was 750 during smooth scrolling; departure snapshots reached 900–911. The back click occurred on the detail page around Y=92. The returned list progressed 86 → 100 and remained 100 after the original 800ms observation. Playwright did not expose the browser's internally saved target position. Those observations do not prove whether restoration was lost, clamped or competing with another transition.

## Executed author diagnostics

All records below used production Next.js builds, original Desktop Chrome viewport 1280×720, Playwright 1.58.2 / Chromium 145.0.7632.6, zero retries, and the author base's actual source bytes.

| Record | Execution and outcome | Interpretation |
| --- | --- | --- |
| `original-linux-20` | Original unchanged scroll case, 20/20 passes, two workers | No original failure reproduced |
| `probe-linux-cpu1` | Original steps/assertions plus measurement hooks, 6/6 passes | Outgoing and returned native Y=900 |
| `probe-linux-cpu8` | CDP CPU throttle 8, 10/10 passes | Departure/return Y=890 or 900; no original failure |
| `probe-chunk-delay1000` | Real detail lazy chunk delayed 1000ms in each of 10 attempts; 10/10 passes | Detail height changed, but still supported the departing Y |
| `probe-native-absent-negative` | Native `history.scrollRestoration='manual'`, one actual assertion failure at Y=0 | Detector control only; deliberately removes native restoration, not a reproduction or defect red/green |
| `original-node22-linux-100` | Original unchanged case, 99 passes / 1 unexpected failure, no retries | Failure at line 38, before scrolling: table rows 11–20 with URL still `/counties`; not the historical post-back Y=100 failure |
| `full-original-chromium` | All 323 original cases: 312 passes, 11 existing fixmes, zero unexpected/flaky/retried results | Full inventory exercised; does not resolve #601 |

The six full cohorts were public 258 passes/11 fixmes, users 4 passes, operations 6 passes, overview/audit 5 passes, ETL UI 28 passes and coordinator 11 passes. Existing fixmes: charts lines 54/70/91/104; home-map line 46; learn lines 65/66/67/106/107; static-pages line 29. They were reported, not executed, and were not introduced here or relabeled as prerequisite omissions. Overlapping targeted repetitions are not added to the 323-case inventory.

The 100-attempt record's raw report, log, trace, screenshot, error context and video are preserved. Its trace SHA-256 is `632bd83708061ba281d908c4b1ad40acb4db5707277ce8f88ca5b150b8cc9585`. A 200 response to `/counties?p=2&_rsc=…` occurred, while subsequent snapshots and the URL assertion still showed `/counties`. This observed pagination mismatch is tracked separately as [#607](https://github.com/Rodgers31/audit_app/issues/607), after a complete all-state census of 298 issues across seven pages. No cause or repair is inferred from one trace.

## Runtime, ownership and limits

The owned Linux AMD64 container ran under Docker Desktop emulation on a macOS ARM64 host, using pinned Playwright image digest `6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d`. Earlier/full diagnostic runs used its Node 24.13.0. The 100-attempt replay used verified Linux x64 Node 22.23.3, matching the original hosted Node version. An initially copied ARM64 Node binary was identified and never used for browser execution. Local Python was 3.12.3; historical hosted Python was 3.12.15. Resolved backend packages and actual runtime/environment/build readbacks are archived. Linux browser identity does not establish equivalence to native hosted CPU, fonts, kernel or scheduling.

The production public fixture uses real application readers with disposable SQLite, disabled dotenv/config loading, inert secrets and blocked external HTTP. Other original cohorts used their actual inert fixture contracts and owned PostgreSQL. There were no `.env` files in the author checkout. Reserved host ports 55523/18013/13013 were checked free and remained unused. Original internal ports (public 55494/8141/3141, then the original cohort ports) ran entirely in the owned container namespace with no host publication. This is an explicit resource substitution. `run_full.py` adapts resource ownership only; the original runner's inventory, six production cohort configurations and `executionPassed`/partition checks were executed. It is not represented as a byte-identical invocation of the original runner's Docker resource-creation path.

Resources: `batch10-scroll-linux`, `batch10-scroll-postgres`, `batch10-scroll-network`, `batch10-scroll-pg-data`, each labeled `audit_app.owner=batch10-scroll`. The container's minimal Git object mirror represented the actual tested commit/tree; it did not modify the dirty primary checkout. Final replay and cleanup receipts are recorded separately after publication. No shared skills, sibling worktrees, production databases, deployments, billing or Actions settings were changed.

## Evidence and next work

Portable evidence lives in [batch10-scroll-evidence](batch10-scroll-evidence/README.md). Its manifest binds losslessly compressed raw outputs to their original bytes, command/source receipts and archived generators. Raw attachment paths in reports retain their actual `/evidence` execution location. The verifier translates only the known `/app/frontend` mount prefix for the original parser's local source-existence check, without rewriting archived reports or case identities. Successful archive validation means integrity and **always reports #601 unresolved**; it is not behavioral acceptance or receipt authentication.

Local raw root: `/Users/roger/.codex/visualizations/2026/10/10/01a123ab-8dbe-78d1-9583-521af8091fa1/batch10-scroll-evidence`. Author checkout: `/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app`. Prior investigation artifacts remain read-only and are never relabeled as this author's execution.

Next: reproduce the original return-to-Y=100 failure with native restoration enabled and capture the causal history/layout ordering. Instrumentation forces layout and can perturb timing; passing probes do not clear an uninstrumented failure. A product change requires an actual failing control followed by a pass while retaining query/filter/history behavior. A test correction requires a demonstrated unfinished transition and meaningful saved-position assertions. Combined hosted acceptance and any eventual merge remain the coordinator's work. There is no safe basis here for an extra sleep, weaker threshold, scroll shim, quarantine, dependency edit or issue closure.
