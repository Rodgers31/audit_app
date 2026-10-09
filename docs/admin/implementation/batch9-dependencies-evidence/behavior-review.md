# Independent behavior review — 2026-10-09

Reviewed head: `baad3586cea2945242ea957aff9d141e83f5b348`.
Executed Node `v22.19.0` on macOS arm64 against this worktree's fresh installed package tree. Only temporary directories named `batch9-dependencies-behavior-*` and the unique `behavior-*` evidence files were written. Fixture `node_modules` links were read only; all owned temporary fixtures were removed. No implementation edits, service start, providers, storage, database, commits, pushes, bot requests, or policy changes were made.

## Confirmed findings

1. **[P2] The lifecycle guard does not bound the effective ESLint configuration.** `verifyToolingInputs` checks only `.eslintrc.json.settings.next.rootDir`. The real standard `npm run lint -- --file app/page.js` passed its copied `prelint` hook and printed `nextRoot: "literal working directory"`, then failed while loading `@next/next/no-html-link-for-pages` with `Maximum call stack size exceeded` when the 4000-level brace pattern was supplied through any of: `.eslintrc.json.overrides[].settings`, a JSON `extends` target, a higher-priority `.eslintrc.cjs`, or `app/.eslintrc.json`. The override, JSON inheritance, and descendant cases use configuration data, not malicious executable code. These are standard automatic configuration paths, not custom CLI configurations. `verify-dependency-tooling.cjs` also printed its CSS success verdict over the unsafe override. The direct top-level setting was correctly rejected before Next started. Reproduction labels: `standard-lint-eslint-{override,extends,alternative-cjs,descendant}-deep` in `behavior-control-results.json`, and `css-verdict-with-unsafe-eslint-override` in `behavior-lifecycle-results.json`.

2. **[P2] Malformed package identities can bypass the graph exclusion verdict.** The actual graph-gate test accepted a report containing its four required callers plus `{ "name": "braces ", "version": "3.0.3" }`; it rejected the same row with canonical name `braces`. A nonempty `.trim()` check does not validate or preserve exact package identity. Reproduction label: `graph-whitespace-excluded-braces` in `behavior-control-results.json`. This is a hostile report-boundary control, not a claim that the actual installed graph contains such a package.

3. **[P2, same guard validation boundary] Non-object ESLint reports receive a success verdict.** Whole-file `[]` and `"invalid"` configurations passed `verifyToolingInputs`, but the actual Next lint correctly rejected their schema afterward. Their preflight false green is not a successful lint result. Labels: `guard-eslint-{array,string}` and `standard-lint-eslint-{array,string}`.

## Passing controls and limitations

Missing, empty, syntactically invalid or null Tailwind/ESLint files were rejected. Deep Tailwind content was rejected. Actual `npm run dev`, `build` and `lint` hooks rejected deep Tailwind input before their respective Next commands started. Default standard lint passed. The graph test rejected empty/malformed output, null/object reports, absent required callers, eight malformed row forms, 13 noncanonical/unsafe version strings (including numeric overflow and NUL/newline suffixes), and canonical `braces`/`micromatch` rows. Canonical build/prerelease versions remained accepted.

These controls do not certify audit counts, native/browser inference, frontend build completion, supported minimum Node environments, Linux behavior, or arbitrary executable configuration/watch-time changes. The graph fixture is intentionally an inert `npm_execpath` report producer for parser controls; the standard lifecycle controls execute the actual installed npm and Next tools.

## Reproduction and raw receipts

Original commands (recorder rejects reuse; use fresh receipt names when replaying):

```sh
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-controls /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-controls.cjs
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs behavior-lifecycle /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/behavior-lifecycle-controls.cjs
```

`behavior-controls.{json,stdout,stderr}` and `behavior-lifecycle.{json,stdout,stderr}` preserve the command, target commit/tree, source hashes, recorder hash, timestamps, runtime and unaltered outer outputs. `behavior-control-results.json` and `behavior-lifecycle-results.json` preserve every child command/status/stdout/stderr and control-script hashes. Outer exit zero means the control runner completed, not that every guarded input was accepted. The reproduced failures above remain unresolved at this reviewed head.
