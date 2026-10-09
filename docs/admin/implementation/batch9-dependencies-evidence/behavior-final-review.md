# Independent repaired-source behavior review — 2026-10-09

Reviewed head: `d16c5a43d7e94fde2799afe9ecaf93ac2400ebd7`.
Executed Node `v22.19.0` on macOS arm64 against the owned fresh installed frontend tree. This record supersedes the three findings at `baad3586cea2945242ea957aff9d141e83f5b348` in `behavior-review.md`; all historical scripts/results/receipts remain unchanged.

## Original findings: fixed by executed controls

1. **Effective ESLint configuration bypass:** awaited direct `verifyToolingInputs(root)` calls rejected the original override, local JSON inheritance, higher-priority `.eslintrc.cjs`, and descendant `app/.eslintrc.json` cases. Actual standard `npm run lint -- --file app/page.js` failed in `prelint` with `tooling input contract`, before any `bounded-tooling-inputs` success verdict or `next lint` invocation. No brace crash occurred. The real CSS compatibility verifier also rejected the unsafe override before reporting CSS compatibility.
2. **Whitespace package identity bypass:** the real graph-gate test now rejected the original `{name:"braces ",version:"3.0.3"}` report. New newline, CR, CRLF, U+2028/U+2029, missing/empty scoped names and embedded whitespace controls were rejected too.
3. **Non-object ESLint JSON false green:** `[]`, `"invalid"`, and `null` were rejected by awaited guard calls; the actual standard lint lifecycle rejected array/string configurations in preflight.

The default fixture still passed both the awaited direct guard and actual standard lint (`lintFilesChecked: 2`). Actual `dev`, `build`, and `lint` lifecycle hooks rejected deep Tailwind configuration before their respective Next tools started. Missing/empty/invalid configurations, malformed/incomplete graph rows, unsafe/noncanonical semantic versions, and canonical excluded `braces`/`micromatch` rows remained rejected. Canonical prerelease/build versions remained accepted.

## Remaining finding

**[P2] Graph report identity syntax still accepts npm-invalid names.** The actual graph-gate test accepted reports with the four required callers plus any of `{name:".braces",version:"3.0.3"}`, `{name:"_braces",version:"3.0.3"}`, `{name:"node_modules",version:"3.0.3"}`, or `{name:"favicon.ico",version:"3.0.3"}`. Installed npm's own `validate-npm-package-name` rejects all four with `validForNewPackages:false` and `validForOldPackages:false`. Evidence labels: `graph-hostile-name-9` through `graph-hostile-name-12` in `behavior-final-control-results.json`; the independent validator's output is `behavior-final-name-validator.stdout`. This is a malformed report schema success, not a claim that canonical `braces` bypasses the repaired check or that those packages exist in the actual installed graph. These four cases were explicitly exploratory (`expected:null`) in the control script; the green runner status does not certify them as valid inputs.

## Commands, provenance and cleanup

```sh
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-final-controls /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-final-controls.cjs
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-final-lifecycle /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-final-lifecycle-controls.cjs
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-final-name-validator /Users/roger/.codex/worktrees/a486/audit_app node -e 'const {createRequire}=require("node:module");const r=createRequire("/Users/roger/.nvm/versions/node/v22.19.0/lib/node_modules/npm/bin/npm-cli.js");const validate=r("validate-npm-package-name");for(const name of ["braces",".braces","_braces","node_modules","favicon.ico","@scope/dependency"])console.log(JSON.stringify({name,validation:validate(name)}));'
```

Seventy child controls ran in `behavior-final-controls.cjs` and four in `behavior-final-lifecycle-controls.cjs`, with zero mismatches for their asserted expectations and no skips/timeouts/setup failures. The validator command additionally executed six names against npm's real validation implementation. `behavior-final-{controls,lifecycle,name-validator}.{json,stdout,stderr}` retain command/source/runtime/commit/tree/recorder hashes and raw outputs. `behavior-final-control-results.json` and `behavior-final-lifecycle-results.json` retain every child command/status/output and each new control script's generator hash. Both child-script hashes matched a fresh readback.

Every temporary fixture root named `batch9-dependencies-behavior-*` was removed in `finally`; only unique evidence files were written. Fixture node_modules links were read only. No implementation edits, installs, live services, provider/storage/database calls, commits, pushes, or bot requests were made.

The resolved ESLint check covers the retained default lint directories (`pages`, `components`, `lib`, `src`, `app`) and effective root probe. Direct custom CLI/configuration and changes during an already-running watcher remain disclosed outside the guarded contract. These controls do not certify Linux/minimum Node compatibility, audit counts, native/browser inference, or full frontend build completion.
