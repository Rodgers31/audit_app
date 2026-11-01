# Deepmerge repair and minimatch applicability — 31 October 2026

**Later migration:** [the lint matcher migration](DEPENDENCY_MATCHER_MIGRATION_2026_10_31.md)
removes the remaining legacy implementation while preserving the existing lint
policy. Its final graph/audit supersedes the 22-entry snapshot below; that
snapshot and its evidence remain historical.

This follows the initial [dependency remediation](DEPENDENCY_REMEDIATION_2026_10_31.md)
on branch `codex/dependency-security-weekly`. It adds a tested local repair for
deepmerge's returned-object prototype poisoning and investigates the specific
minimatch amplification advisory. Package versions and `package-lock.json` are
unchanged. No advisory is suppressed, version relabelled, merge performed or
deployment started. Issue [494](https://github.com/Rodgers31/audit_app/issues/494)
remains open.

## Current result

| Raw audit root | npm entries | Follow-up assessment |
|---|---|---|
| deepmerge 4.3.1 / GHSA-gcqx-w48m-w2h4 | 5 low | Returned-object prototype poisoning is reproduced on original bytes and blocked by the source-bound repair. npm still reports the unchanged registry version. |
| minimatch 3.1.5 / GHSA-g3hv-75wg-m249 | 17 moderate | The described level-2 preprocessing mechanism is absent from this legacy implementation. Cross-version execution supports non-applicability of this particular mechanism; the aggregate advisory's broad range still matches it. This is not clearance of all possible matcher denial of service. |
| Production npm audit | 0 | No production finding; the affected packages above are development/build tooling. |

The full audit therefore still reports **22**, with its original nonzero exit.
Both fresh [full](dependencies/2026-10-31/followup/npm-full.json) and
[production](dependencies/2026-10-31/followup/npm-production.json) outputs are
retained. Fixing behavior and changing a version-based scanner's output are
different outcomes. There is no claim of an upstream patched deepmerge release
or an officially corrected minimatch affected-version range.

## Deepmerge: bounded repair, complete installed package identity

The [current advisory](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
lists no patched release. Both installed Jest 30.5.2 config loaders resolve the
single development-only deepmerge 4.3.1 installation. Its actual main export is
`dist/cjs.js`, not `index.js`.

The existing postinstall repair mechanism now inventories deepmerge as its third
package. It checks every distributed file, package metadata, locked version and
location against exact hashes. It applies the same small change to `index.js`,
`dist/cjs.js` and `dist/umd.js`: reject the `__proto__` key before reading or
assigning it in either the target-copy or source-copy loop. It retains the
existing inherited-property guard. This covers the package main, UMD CommonJS
and browser-global paths, as well as the unbundled source.

The key check covers null-prototype targets, own enumerable prototype keys and
nested null/primitive placeholders. It runs before a getter or custom merge
callback can receive the forbidden key. Other keys, symbols, default array
concatenation, cloning, dates and custom merge/array options retain their prior
contracts. `constructor` and `prototype` remain ordinary permitted data where the
old API permits them; broad removal would change legitimate configuration data.
This is a repair to the library's own copy operations, not a sanitizer for
arbitrary objects returned by application-provided callbacks or references
intentionally retained with `clone: false`.

Unknown source bytes, missing bundles, symlinks, unexpected nested copies,
changed metadata/versions and malformed locks still fail visibly before patch
publication. Clean production omission reports all three absent tooling packages
without claiming to have repaired them. Check mode refuses an unpatched full
installation; normal lint/build/test entry points enforce it. Successful clean
installation applies ten files in total (the previous seven plus three
deepmerge files), and repeated installation is idempotent.

Independent review also reproduced an exception-field gap in the existing
installer: coherently changed repair/lock metadata could exempt an unpatched
nested deepmerge copy from inspection. A real copied Jest caller then resolved
that original vulnerable bundle despite a successful repair verdict. The
installer now permits only the exact reviewed `node_modules/js-yaml` 4.3.2
exception. Braces/deepmerge cannot declare exclusions; malformed values and
changed YAML exception paths/versions are rejected. Five permanent tests fail
before this guard change and pass after it. This was a repair-verification
metadata defect, not a public request exploit or a bypass present in the
committed candidate metadata.

The repair preserves original metadata and license files. It does not install a
fork or assert upstream endorsement. It resembles the approach discussed in
[upstream PR 274](https://github.com/TehShrike/deepmerge/pull/274), which is closed
and was not released; acceptance here depends on executable evidence, not that
proposal's status. A future upstream version or package-layout change requires
manual re-review of the repair inventory rather than a hash bypass.

## Minimatch: specific mechanism and compatibility

There is a real source discrepancy:

* The [maintainer advisory](https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249)
  identifies 10.2.6 and level-2 `firstPhasePreProcess` expansion followed by
  pairwise `secondPhasePreProcess` work.
* The [aggregate advisory consumed by npm](https://github.com/advisories/GHSA-g3hv-75wg-m249)
  assigns the range `<11.0.1`, which includes our remaining 3.1.5.
* The [upstream fix](https://github.com/isaacs/minimatch/commit/77a0f5c)
  bounds generated pattern rows and skips pairwise deduplication for large sets.
  These preprocessing methods and the optimization-level mechanism do not exist
  in the installed 3.1.5 implementation.

The exact upstream trigger, reduced to eight segments, was compiled in isolated
child processes with a 96 MB heap and a five-second author replay timeout.
The same pattern, level 2 and `braceExpandMax: 8` produced:

| Actual implementation | Compiled rows | Pairwise comparisons under instrumentation |
|---|---|---|
| Unfixed 10.2.6 | 256 | 32,640 |
| Patched 11.0.3 | 8 | 28 |
| Legacy 3.1.5 | 1 | No corresponding methods |

Uninstrumented children independently produce the same row counts. The
[author replay](dependencies/2026-10-31/followup/minimatch-author-replay.json)
retains exact implementation hashes and measurements. These are bounded
mechanism controls, not an assertion that every pathological pattern is cheap.
The modern copies used by TypeScript ESLint, modern glob and coverage remain
patched at 11.0.3.

A separate [bounded matching control](dependencies/2026-10-31/followup/legacy-backtracking-author-replay.json)
also demonstrates why that distinction matters: twelve repeated wildcard/literal
pairs followed by a nonmatching suffix take about 1.4 seconds in the legacy
implementation against a 32-character path; the modern implementation returns
promptly. A review child with a shorter 750 ms bound times out on that legacy
case. This exercises regex backtracking, not the advisory's absent preprocessing
mechanism. It is retained as a separate development-tooling performance risk,
without a new CVE attribution or a demonstrated public application request path.
Advisory-range correction alone would not modernize or qualify legacy matching
for arbitrary untrusted patterns.

The investigation also found that final deduplication of our earlier modern
regression pattern masked its intermediate amplification. The permanent control now uses
the upstream trigger, checks the exact expansion cap, and checks successful
ordinary matching below that cap. This corrected control is observed RED on
10.2.6 and GREEN on 11.0.3; the prior weaker control is not cited as proof of the
amplification repair.

Remaining legacy consumers still require their old callable/RegExp API. In
particular, the actual import plugin calls `makeRe()`, which minimatch 11
[removes](https://github.com/isaacs/minimatch/blob/main/changelog.md). A blanket
override remains incompatible. Repository-owned tooling configuration and its
existing input checks remain enforced. Source text from an untrusted change can
still affect tooling inputs, and tooling execution on untrusted repositories is
outside this narrow applicability conclusion.

We retain all 17 moderate entries in the raw report. No audit ignore, policy
waiver, upstream message or advisory correction is submitted. Eliminating those
scanner entries requires a verified upstream range correction or migration of
every remaining legacy consumer to a compatible fixed/replacement graph.

## Verification, review and rollback

[Source-bound author receipts](dependencies/2026-10-31/followup/author-acceptance.json)
identify the tested executable bytes, commands, timestamps and output hashes.
The official SHA-256-checked Node 24.22.1/npm 11.19.1 runtime from initial
preparation is reused. Tests use the owned checkout and inert local fixtures.

* Original deepmerge: 30 failing security cases and six passing compatibility
  cases. Repaired CommonJS/UMD/browser behavior: all 36 pass.
* Clean `npm ci` with postinstall and optional packages, complete `npm ls`,
  TypeScript and lint pass. Full/production audits retain actual exits 1/0.
* Dependency controls: 189 pass; separate runtime/isolation selection: nine
  pass, including a real production-pruned image decoder and unchanged source
  readback. Nested cases overlap; counts are not added as unique coverage.
* Complete Jest: 215 suites, 2,904 passing tests, one existing pending test.
* Production build plus all 14 admin-shell Chromium cases pass, covering
  desktop/mobile widths and signed-out/editor refusals. Fixture servers exit.

The Python source and manifests are unchanged in this follow-up. Initial Python
audit/test results, video-tool skips, native x86 worker/base qualification and
deployed OS/binary census limits remain attributed to the initial report; they
are not newly executed or cleared here. Existing publishing, source admission,
worker and financial-generation holds remain in place.

Reverting this follow-up commit and performing a clean `npm ci` removes the local
repair and reintroduces the reproduced deepmerge behavior. Reverting only an
installed file is not a durable rollback because postinstall re-applies reviewed
repairs. There is no data migration or production data undo. The separate bot
change remains independently reviewable and revertible.
