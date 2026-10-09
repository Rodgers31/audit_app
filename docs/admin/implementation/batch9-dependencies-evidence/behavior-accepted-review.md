# Independent accepted-source behavior review — 2026-10-09

Reviewed product head: `94f350ffc93bec4433617b04bf7c94bad4828345`.
Runtime: macOS arm64, Node `v22.19.0`, npm `11.6.0`, fresh owned frontend install with direct `validate-npm-package-name@6.0.2`.

**Unresolved findings in this independent behavior review: 0.** This supersedes the remaining finding in `behavior-final-review.md` and the original findings in `behavior-review.md`. Both earlier review rounds and their raw scripts/receipts/results remain unchanged.

The real graph-gate test now rejects `.braces`, `_braces`, `node_modules`, and `favicon.ico`, plus `.invalid`, `@scope/.invalid`, scoped malformed URL names, missing/scoped-empty names, embedded/trailing whitespace and line terminators. The legitimate lowercase builtin package name `fs` remains accepted through the deliberately retained old-package naming contract. Canonical `braces`/`micromatch` rows remain excluded. Unsafe/noncanonical semantic versions, malformed/empty JSON, invalid rows and missing required callers remain rejected; canonical prerelease/build versions remain accepted.

Awaited direct guard calls and real standard lint lifecycle calls rechecked the prior ESLint override, local JSON inheritance, higher-priority alternate config and descendant config failures. All were rejected before a success verdict or Next invocation. Whole-file array/string/null configurations were rejected. Actual `dev`, `build` and `lint` hooks rejected deep Tailwind input before starting Next. The actual CSS verifier rejected the unsafe ESLint override before CSS success. Default guard and standard lint fixtures still passed.

## Executed commands and counts

```sh
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-accepted-controls /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-accepted-controls.cjs
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-accepted-lifecycle /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-accepted-lifecycle-controls.cjs
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-accepted-actual-graph /Users/roger/.codex/worktrees/a486/audit_app env npm_execpath=/Users/roger/.nvm/versions/node/v22.19.0/lib/node_modules/npm/bin/npm-cli.js node --test frontend/scripts/jest-dependency-boundary.test.cjs
```

- Independent control runners: **80/80 matched expectations** (76 guard/report/lint controls + 4 lifecycle/CSS controls); no unexpected statuses, timeouts or setup errors. Rejection controls intentionally have child exit 1. Each isolated graph report control executes the selected installed-graph test; unrelated sibling tests are excluded by its name filter and do not establish acceptance.
- Actual installed npm/Jest graph, engine contract, graph parser, discovery and real assertion-failure suite: **6 passed, 0 failed, 0 skipped**. This command uses npm's actual installed `query` implementation rather than a report fixture for its installed-graph measurement.
- `behavior-accepted-provenance.{json,stdout,stderr}` records the separate executed readback command. It verified both child generator hashes, all three command receipt generator/output hashes, their exact reviewed commit, zero control mismatches and deletion of every recorded owned fixture root.

## Provenance, cleanup and limits

`behavior-accepted-{controls,lifecycle,actual-graph}.{json,stdout,stderr}` retain exact commands, timestamps, commit/tree, source/runtime/recorder hashes and raw outputs. `behavior-accepted-control-results.json` and `behavior-accepted-lifecycle-results.json` retain every child command/status/output and generator hash. Readback generator hashes were:

- Controls: `a35e96da814d8683d82d40a604872291f88f8154ff1b745b19b6ca0599c7a044`.
- Lifecycle: `40278a4fe7c175b1ec1c5901a165bc09a03eac7785234e057de4bc247aadaaf1`.

All owned `batch9-dependencies-behavior-*` temporary roots were removed. Only unique evidence files were written; fixture node_modules links were read only. No source edits, installs, service starts, provider/storage/database calls, commits, pushes or bot requests were made by this reviewer.

The guard covers effective configuration in the retained default lint directories (`pages`, `components`, `lib`, `src`, `app`) plus the root probe. Direct custom CLI/configuration, arbitrary executable configuration and changes during an already-running watcher remain disclosed outside this guard's contract. This review does not certify Linux/minimum Node behavior, full audit counts, native/browser inference or full frontend build completion, and does not imply complete #494 acceptance while residual advisories remain.
