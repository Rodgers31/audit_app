# Independent Spec: minimal minimatch caller migration

The smallest viable candidate is the contained caller migration already being prepared: retain ESLint 8.57.1, Next/eslint-config-next 15.5.28 and the complete authored lint configuration; pin the six legacy lint parents explicitly to minimatch 11.0.3; repair the public ESM default import in eslintrc and the actual callable/RegExp calls in the three plugins. The cache/rimraf/glob7 leg must separately move off minimatch 3 with its own API tests. This is a targeted security migration, not a claim that ESLint 8 is maintained. It creates an explicit local source-repair maintenance burden.

This recommendation is based on executed controls of the core/configuration leg. It is not final acceptance of the author's forthcoming installed implementation, and does not independently qualify the plugin/cache legs assigned elsewhere. No candidate file or installed package was changed by this reviewer.

**Core execution.** Runtime load redirection changed only minimatch requested by ESLint, @eslint/eslintrc and @humanwhocodes/config-array. Other legacy plugin callers kept their original library for this isolation control. Baseline and candidate each ran real lint over all 360 files selected by Next's default source directories/extensions, calculated complete effective configurations for those files and representative root/nested/dot paths, and exercised ConfigArray matching/ignores directly. They produced identical full configuration objects, rule severities/options, parser settings, ignore decisions and file-by-file lint diagnostics. Both unique effective configurations are retained, not just the local rule pair. [Exact comparison](runs/core-parity-summary.json), [commands/exits](runs/core-lint-receipts.json), [immutable baseline](baseline-pre-migration/effective-configs-and-diagnostics.json).

The first effective configuration contains 54 configured rules and 46 enabled rules:

| Namespace | Configured | Enabled |
|---|---:|---:|
| @next/next | 21 | 20 |
| react | 22 | 16 |
| jsx-a11y | 6 | 6 |
| react-hooks | 2 | 1 |
| import | 1 | 1 |
| local | 2 | 2 |

These counts describe the actual effective project configuration, not the entire catalog of rules exported by each installed plugin. Preserving the configuration does not authorize removal of unconfigured plugin rule implementations or their schemas. The plugin repair must retain those exports and test every changed API call.

ESLint's legacy enumerator, its flat helper and ConfigArray use the retained Minimatch constructor/match interfaces. An additional actual FlatESLint API fixture used dot files, basename selectors, nested brace globs, ignores and a missing selector. Original and modern-core results match exactly, including NoFilesFoundError. Every selected fixture executes the real no-undef rule and reports its expected error, preventing empty/ignored work from masquerading as compatibility. [Flat API receipts](runs/flat-api.receipts.json).

**Public ESM repair is necessary.** Native import of the original eslintrc 2.1.4 public ESM entry, with modern minimatch supplied in an owned package copy, fails because no default export exists. Replacing only the default import/destructure with `import { Minimatch } from "minimatch";` makes the public Legacy/FlatCompat exports load. Repaired native ESM and existing CJS exports match baseline export keys, OverrideTester serialization, and 120 actual include/exclude decisions over dot, basename, ./, brace and extglob patterns. Relative test paths and invalid absolute/parent override patterns still reject. [Executed ESM RED/GREEN](runs/eslintrc-esm.receipt.json).

The exact override-tester source SHA-256 values are original `dcb0beb172afb43a2c019eea2193c29f15edb98bf10ca77f1c3307f176c0a75a`, repaired `47d0140fe48e73387e9f5605ff8e5262f8fb67e97cf1ac707d00f38e027b8d40`. No CJS core/config algorithm replacement is needed for the tested API uses. Explicit dependency pins and installed inventory/readback must still prove every actual caller resolves the intended modern implementation.

**Alternatives checked against current primary metadata.** The retrieved registry records are saved under upstream with URLs/timestamps. These are current as of the review, not inferred from historical major-version assumptions.

| Candidate | Evidence and consequence |
|---|---|
| Compatible parent-only upgrades | Latest ESLint 8 remains 8.57.1 and declares minimatch 3; latest ESLint 9.39.5 also declares minimatch 3. Latest eslintrc 3.3.7 and current import/react/a11y plugin releases still declare 3. Updating those parents alone cannot remove the legacy graph. |
| ESLint 9 flat configuration | Still retains core minimatch 3 and eslintrc 3 in its dependency graph. Changing configuration format adds migration scope without completing this remediation. Its registry metadata also marks the current 9 release unsupported. |
| ESLint 10.14.0 flat configuration | Core moves to minimatch 10 and modern config-array, but eslint-config-next 15.5.28 and the existing plugin peer ranges stop at 9. An actual strict npm resolver experiment refuses ESLint 10 + current Next config with ERESOLVE, specifically that peer conflict. No force/legacy-peer bypass was used. [Resolver receipt](runs/eslint10-strict-peer.receipt.json). Rebuilding the flat Next/plugin/rule configuration and qualifying all callers is a larger future migration. |
| eslint-plugin-import-x 4.17.1 | Its maintained fork declares minimatch 9/10 and supports ESLint 8/9/10, but exact published-source gitHead still imports makeRe in no-internal-modules, which minimatch 11 removed. It therefore also needs an API migration to use 11; replacing one plugin does not remove the other legacy parents. Current Next config directly selects the original plugin; substituting this fork would additionally require verified plugin/config/resolver and full rule behavior compatibility. It was inspected, not installed as an app replacement or accepted as a drop-in. |

Primary references: [ESLint 9 migration](https://eslint.org/docs/latest/use/migrate-to-9.0.0), [ESLint 10 migration](https://eslint.org/docs/latest/use/migrate-to-10.0.0), [minimatch API changes](https://github.com/isaacs/minimatch/blob/main/changelog.md), [import-x project](https://github.com/un-ts/eslint-plugin-import-x). Registry metadata is preserved rather than treating the latest Next documentation as documentation for the installed Next 15 CLI.

The final candidate should be reviewed by replaying the saved full configuration/diagnostic baseline against the actual installed, repaired tree without load redirection; exercising native eslintrc ESM and CJS imports; testing every changed plugin call with both positive and negative rule fixtures; verifying declared plugin rule/schema inventories; checking lock/install identities, no legacy minimatch/glob7 and raw full/production audit exits; and executing the existing build/test/input/repair gates. Installer mutations must reject unknown/missing/newly nested package bytes before publishing any repair. Normal app requests and worker/source/financial/publishing holds remain unchanged.
