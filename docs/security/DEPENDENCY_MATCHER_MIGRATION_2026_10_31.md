# Lint matcher migration — 31 October 2026

This follows the [deepmerge repair and applicability investigation](DEPENDENCY_FOLLOWUP_2026_10_31.md).
It removes legacy minimatch 3, glob 7 and rimraf 3 from the frontend dependency
graph while preserving the existing ESLint 8 / Next 15 configuration and rules.
No merge, deployment, production write or source/worker/publishing opt-in is part
of this change. Issue [494](https://github.com/Rodgers31/audit_app/issues/494)
remains open for the remaining dependency maintenance.

## Smallest compatible scope

The current published React, import and accessibility plugins still declare
minimatch 3. Latest ESLint 9 and eslintrc also retain it; ESLint 10 is outside
Next 15's supported peer range and does not remove those plugin dependencies.
A framework/flat-config migration would therefore add changes without completing
this removal. The independently tested migration keeps those package versions
and their rule inventory.

Six exact parent-scoped overrides select minimatch 11.0.3 for ESLint 8.57.1,
eslintrc 2.1.4, config-array 0.13.0, import 2.32.0, React 7.37.5 and jsx-a11y
6.10.2. ESLint's direct requirement is pinned to its already installed 8.57.1
to satisfy npm's direct-override identity requirement. There is no general
legacy minimatch override that could silently substitute an unreviewed caller.
Existing modern overrides remain in place.

Fifteen source-bound caller edits provide the actual API migration:

* eslintrc's native ESM source imports the named `Minimatch` export. Its CJS
  export already consumes the compatible constructor namespace.
* Six import-rule files, five React-rule files and two accessibility utilities
  select the modern named callable export.
* Import's `no-internal-modules` rule compiles `Minimatch` instances and calls
  `match`, replacing its removed `makeRe` / RegExp path. This is the seventh
  changed import-rule file; it does not reintroduce a regex compatibility shim.

The old cache leg is removed with one additional scoped override:
flat-cache 3.2.0 uses rimraf 6.1.3's retained synchronous API with `glob: false`.
Its glob dependency resolves to the already tested modern glob 14.0.3. This
preserves the existing file-entry-cache API. An isolated flat-cache 4 alternative
failed directory/symlink deletion compatibility and was not adopted.

Resolution also deduplicates modern glob/matcher support packages. The only new
package name is `package-json-from-dist` 1.0.1; no production dependency version
changes. The lock delta and raw audits are retained with the final evidence.

## Preserved lint policy and explicit compatibility limits

The `.eslintrc.json` file and both local-rule source files are unchanged. Before
replacement, independent reviewers captured complete effective configurations,
file coverage and diagnostics. The repaired tree preserves all **54 configured
rules, 46 enabled rules, every option, both JS/TS configurations and all 360
current lint targets**, with identical diagnostics. All **347 declared rule
exports** remain present, with their schemas and metadata unchanged.

Permanent controls preserve the baseline rule/options object for six supported
source extensions. They execute real refusal cases for the published-figure
zero fallback, missing suppression reason, Next synchronous scripts, React keys,
hooks, accessibility and anonymous default-export rules. Positive null rendering
and reasoned suppression remain accepted. Independent plugin controls execute
fourteen migrated plugin files plus the preserved constructor-based caller with
both allow and refusal outcomes. The fifteenth migrated file, eslintrc's ESM
source, is exercised separately through its native public exports.

The optional `import/no-internal-modules` rule is not enabled in this repository's
effective configuration. For arbitrary future options, its old generated RegExp
and the modern matcher's path semantics are not universally identical. Dot paths,
leading globstars and extglobs have measured edge differences. The migration
preserves current policy and tested plugin cases; it does not promise to preserve
every old regex quirk for a rule that is currently disabled. Future activation
of that rule must review its actual patterns under the modern semantics.

The previous specific optimizer and legacy backtracking controls now execute
against modern minimatch throughout the graph. This removes the legacy code
path; it is not a general claim that unlimited untrusted patterns are safe.

## Install verification and maintenance

The source-bound repair manifest advances to schema 4 and seven packages.
It retains complete installed-tree file inventories, including nested package
bytes, without skipping `node_modules`. There are 25 repaired files in total:
the previous ten and fifteen migrated callers. Original tar identities and
repaired hashes are verified separately.

Three ordinary npm CLI links inside the import/React package trees are now
explicitly inventoried. Only their exact reviewed `.bin` locations and relative
targets are permitted. Each target must remain inside that package tree, be a
regular inventoried file and retain its reviewed bytes/mode. All other symlinks
remain refused. This does not introduce a generic exclusion field.

The installer rejects legacy matcher/glob/remover lock entries and checks the
actual dependency resolved by all six migrated callers, flat-cache and rimraf.
An unrecorded physical legacy copy cannot shadow a modern locked entry and still
produce a successful verification. Metadata and the actual CommonJS entry must
resolve to the same named, locked package; the entry path, regular-file status
and exact reviewed entry bytes are checked together.

Verification also uses the actual requester directories. Package-root resolution
alone missed legacy copies placed beneath ESLint's `lib` directories. The
reviewer and author both reproduced that false success with real legacy code.
Five further permanent refusal cases fail before the origin checks and pass
afterward. The guard now checks eight package-root resolutions plus five actual
source contexts, including ESLint's two requesters, config-array, the cache
remover and rimraf's glob requester. Repaired packages retain complete nested
file inventories. The glob 14 main export is its minified bundled entry, which
is verified using that actual exported path and bytes.

The comparison root is canonicalized after refusing symlinked roots and module
directories. This preserves legitimate macOS ancestor aliases such as `/tmp`
and `/private/tmp` without permitting an out-of-root resolution. A permanent
ancestor-alias positive and direct-root-symlink refusal reproduce the earlier
fail-closed portability error and verify the correction.

Independent review reproduced a metadata-alias gap in the initial candidate:
a hidden legacy package could link its `package.json` to legitimate modern
metadata while executing its own old code. The author independently reproduced
that false success. Two permanent controls fail before executable binding and
pass afterward, covering the alias and canonical-entry drift. This was a
malformed physical-install verification defect, not a failure of the clean
installation or a demonstrated public request exploit.

Production omission is explicit; it does not
claim that absent development packages were inspected or repaired.

These are application-owned compatibility exceptions outside the parents'
declared minimatch/rimraf major ranges. They require manual review on parent,
layout or dependency changes. Future update PRs must preserve all rule settings,
caller APIs, source hashes, exact CLI links and runtime resolution checks. An
install refusal is a maintenance signal, not permission to bypass a guard.
ESLint 8 remains deprecated; its broader eventual upgrade is separate work.

## Validation, audit and rollback

Final command receipts and both independent executable reviews are retained in
the accompanying evidence directory. Acceptance includes a fresh scripted
installation, full dependency/runtime controls, TypeScript, lint, all Jest tests,
production build and the admin Chromium gate. The completed final run passes
217 dependency controls, nine runtime/isolation controls, 215 Jest suites with
2,904 passing tests and one existing pending case, and all 14 admin browser
cases. Lint runs without its cache; TypeScript and the complete installed peer
graph also pass. Isolated controls retain the
original-callers/modern-matcher failures and repaired success, actual ESM/CJS
behavior, cache invalidation/deletion and installer link/shadow refusals.

The full npm audit changes **22 → 5**, removing all 17 moderate propagated
minimatch entries. Production remains **0**. The five low entries still refer
to the unchanged deepmerge registry version, whose exact installed code remains
locally repaired and tested. No advisory suppression, version relabelling or
downgrade is used. Historical raw reports retain their original dates/scopes.

Python manifests/source, application code, auth/issuer policy and data are
unchanged. Initial Python/native/worker qualification limits remain attributed
to their earlier reports. This does not qualify deployed images or enable any
held consumer. Windows was not qualified; the reviewed npm CLI links apply to
the tested Unix installation layout.

Rollback is a reviewed revert of this migration commit followed by clean
`npm ci`. That restores legacy matcher/cache dependencies and the recorded
moderate findings; retain their risks. It leaves the preceding deepmerge repair
independently intact. No data migration or production data undo is required.
