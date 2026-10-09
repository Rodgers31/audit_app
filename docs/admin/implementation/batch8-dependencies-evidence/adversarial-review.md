# Executed adversarial dependency review

Executed on macOS arm64 with Node v22.19.0, npm 11.6.0, installed Jest 30.5.2. Repository fixed HEAD `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, HEAD tree `f22a430a4402d79867da63ad97db8c8d474d3a71`; the implementation is a working diff atop that base. Exact final tested files, dispatched patch identity, and runtime identities are in `identities-v3.json`; the tested added test source is retained as `subject-v3.test.cjs`, and the full owned source snapshot is `working-source-v3.patch`. The final test source SHA256 is `ae7b43c389bc8a8457ecc69f43ec4ab2e01dfc6821e676606fbe1cdb90a7e830`.

## Confirmed findings and repairs

1. The original npm graph gate accepted a core-only array and `@jest/core` plus unnamed objects or rows lacking names. Original tested source is retained in `subject-v1.test.cjs`, reconstructed from `dispatched.patch` and verified against the original recorded source SHA256. Executed stubs and original exit-0 outcomes are retained in `probe-boundary.cjs`, `boundary-results.json`, and `logs/graph-core-and-untyped-entry.stdout.log` / `logs/graph-core-and-nonnamed-entry.stdout.log`. This is malformed/incomplete report acceptance; the real npm report was independently measured, so no claim of a genuine npm graph omission follows from these stubs. The author added per-row identity validation and required the four actual Jest caller packages. All original false-greens now exit 1.

2. The first repair introduced a child regression that inherited Node's `NODE_TEST_CONTEXT` from the test runner. Executing the complete actual source returned exit 1: the child skipped its test files with the recursive-test warning and returned 0, failing the expected-1 assertion. Exact red is in `boundary-results-v2.json`, `subject-v2.test.cjs`, and `logs/v2-actual-new-tests.stdout.log`. The author replaced the child's environment with explicit PATH/npm_execpath. Executing the final complete new suite and combined new/browser suite returned exit 0.

No remaining confirmed finding in the exercised scope after the final repair.

## Final executed input matrix

`probe-boundary-v3.cjs` executed 33 cases; all matched their explicit expected exit status. The actual complete new suite passed, the complete new/browser suites passed, and direct complete test invocation without npm_execpath returned 1. Hostile graph cases returned 1: missing, absent, relative, and directory npm executable paths; npm query exit 2 despite plausible JSON; absent stdout; malformed JSON; empty array; object/null containers; missing core; braces/micromatch; null rows; core-only/incomplete arrays; oversized 9 MiB stdout; 15-second query timeout. A well-formed fake four-caller graph returned 0. With the four callers present, unnamed, missing-version, blank-name/version, array, boolean, numeric-version and null rows, plus braces and micromatch, all returned 1. Exact commands, inputs, stdout/stderr, timestamps and statuses are retained in `boundary-results-v3.json`, `stubs/`, and `logs/v3-*`.

The independent actual `npm query '#jest *' --json` returned 0 and measured 318 named/versioned records, including the four Jest caller packages, with zero braces/micromatch. Raw report and exact command receipt are `live-query.stdout.json` and `live-query.receipt.json`.

## Public Jest compatibility and failure behavior

`probe-cli-watch-v2.cjs` used copied, byte-identical current Jest/Next/setup/TypeScript config files and a read-only symlink to the installed modules. The fixture has real JavaScript and TypeScript module imports, JSX and TSX transforms, and nested __tests__ cases. Discovery retained exactly eight .js/.jsx/.ts/.tsx application cases and excluded two deliberately throwing .cjs Node fixtures, e2e, and .next fixtures. All eight tests executed successfully; all eight also executed successfully with coverage. Reports had success=true, total=8, passed=8, failed=0, runtime-error suites=0, and exit 0.

Real public CLI failure inputs returned 1: no tests, absent config, malformed config JSON, null testMatch, intentional failed assertion (one failed test), absent imported module (zero tests/one runtime-error suite), and an unresolved-promise test timeout (one failed test). A deliberately infinite module body hit the supervising spawn timeout: status=null, signal=SIGTERM, error=ETIMEDOUT. It is recorded as UNINTERPRETABLE and never counted as a successful Jest run. Exact commands and JSON/output are in `cli-results-v2.json` and `logs/v2-*`.

The initial owned compatibility fixture had invalid JSX member-access syntax, causing three parser errors. That was a review-fixture error, not a product finding. Original script, exit-1 reports and raw logs remain in `probe-cli-watch.cjs`, `cli-results.json`, and `logs/application-*`; corrected valid JSX is in the v2 script. Its initial watcher trace omitted the native package request; the v2 loader hook records it without replacing installed exports.

## Actual macOS native watcher

Both the v2 CLI harness and the standalone portable harness ran ordinary Jest `--watchAll --watchman=false` with one inert owned test. They observed initial success with total=1/passed=1, changed that file to a failing assertion, and observed a real rerun with total=1/failed=1 and success=false. Runtime loader traces confirmed `@parcel/watcher` and the actual `@parcel/watcher-darwin-arm64/watcher.node`; binary SHA256 `bdc5c3950f2bc6dde211a17e100faf862e712e51c853555dade6f5d1aab1e921`. Each owned process group was terminated with SIGTERM and checked absent. The final portable receipt is `watch-portable-macos/receipt.json`, with raw initial/updated reports and loader trace beside it.

Portable Node-only reproduction: `node probe-parcel-watch-portable.cjs /candidate/frontend/node_modules/jest/bin/jest.js /owned/output/watch-root`. The author has the script for separate Linux amd64 execution. This reviewer has not executed Linux, Windows, watchman-backed watching, or network/model/browser/native production acceptance. The parent owns those separate checks.

## Isolation and limits

All review scripts, temporary directories, logs, npm cache, coverage output and fixtures are under this review-adversarial directory. Installed parent modules were only read; no npm installation/prune, parent module/cache/process mutation, paid review, CI, GitHub mutation, application feature edit, or source-preservation sentinel change was performed. Owned watcher process groups have been removed; fixtures and raw artifacts are retained as evidence. These bounded executions supplement the author's full application suites; they do not substitute for them.
