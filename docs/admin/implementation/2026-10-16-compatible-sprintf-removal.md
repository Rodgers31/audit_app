# Compatible removal of sprintf-js (#689)

The earlier #680 packet proved that merely overriding argparse was incompatible. This change uses the reviewed argparse2.0.1 graph, retires the sprintf-js repairs, and makes the legacy NYC js-yaml3.15.2 CLI compatible with that graph. The separate js-yaml4.3.2 CLI and all 173 non-development lock records remain unchanged. No application, native/model identity, production configuration or activation flag changes.

## Source-bound installation

Repair manifest schema3 admits the exact braces3.0.3 and nested js-yaml3.15.2 locations, names, development classification, complete package-file inventory, original and repaired source hashes. The separate root YAML4 entry is explicitly admitted without patching its source. Unknown YAML locations/versions, argparse traversal/drift, any retired sprintf lock entry, changed/added/missing source files and symbolic links refuse before publication. Check mode still refuses unpatched source. Omitted development packages are reported absent only in explicit production mode. Atomic replacement retains original permission bits; the legacy CLI must be0755, including in check mode. Existing lock ownership, retry and failed-publication behavior remains visible.

The legacy YAML CLI now uses argparse2 public snake_case APIs and an explicit -v/--version action. A public error hook preserves usage on stdout and the diagnostic on stderr, with status2. Successful data output and statuses remain compatible, including with --throw-deprecation; help/error wording follows argparse2. YAML loading/dumping APIs and the NYC loader are untouched. Both real CLI versions, loader configurations and instrumentation are exercised independently.

## Reproductions and verification

The clean baseline install and five initial CLI cases passed. Applying only the old candidate graph made normal npm ci exit1 (missing locked sprintf-js), and both version-flag tests failed with empty output. Independent executable reviews then exposed fatal deprecations, changed parser-error streams, dropped CLI executable mode, an ignored argparse traversal entry and an ignored extra YAML3 location. All were observed failing before their repairs; permanent regressions cover them. The original packet remains historical evidence and is unchanged.

Reproduce from frontend with Node22 and npm10:

```sh
npm ci --include=dev --include=optional --no-audit --no-fund
npm run test:dependency-boundaries
npm test -- --runInBand
npx tsc --noEmit
```

The local production build needs explicit public API/Supabase inputs. The inert build uses loopback port1 and a dummy public anon value; it verifies build/trace boundaries, not production authentication or data. Live production admin/account/off-switch acceptance is recorded separately for release827a891.

The focused repairs/CLI suite has 57 passing cases; the dependency suite has 133 passing cases plus 9 pruned-runtime cases. The frontend suite has 155 passing suites /2195 passing tests, with one pre-existing PostgreSQL capture prerequisite skip. Independent Spec review executed 80 CLI comparisons, 42 strict/direct calls, 16 NYC configuration cases and instrumenter parity. Independent Standards review executed 52 hostile guard cases, 33 permanent install/CLI cases, six omit-dev variants and three interrupted-publication/retry cases. Both final reviews have no unresolved finding in their executed scope.

Raw red/green receipts, source hashes, full audit results and independent executable probes are retained in the coordinator evidence directory BATCH14_RELEASE. Native ARM Linux and final build outcomes are recorded in the completion receipt below; earlier missing environment/driver prerequisites remain retained separately.

## Dependency audit boundary

Fresh npm audit changes from 26 propagated entries (7 high, 19 moderate) to 7 high entries, all in the remaining braces chain. Removing sprintf-js removes its advisory-bearing dependency rather than suppressing it. The retained braces source repairs and bounded-input guards still apply; #494 remains open for actual upstream dependency remediation. No zero-advisory or overall security-clear verdict is claimed.

Primary advisory references: [sprintf-js](https://github.com/advisories/GHSA-hp3w-g68c-fv3c), [braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), checked2026-10-16. The lock retains all 32 Next/native/Transformers/ONNX/sharp records exactly; no new model download or provider identity is introduced. Hosted Actions and automatic Preview builds stay disabled. No paid review, plan or resource is added.

## Final completion receipt

A fresh native ARM Linux Node22.23.3/npm10.9.9 install passes all 57 focused cases, all 133 dependency boundaries and 9 pruned-runtime cases with zero skips. Production-only npm audits report 0 entries on both macOS and Linux. The configured inert production build passes, including lint/type checking;50 server traces contain no excluded native/model package path. No new browser/WASM model-inference replay is claimed; the 32 relevant lock records and model/native identities are unchanged, and transport/input boundary regressions were executed. Earlier Linux fixture runs lacked the npm lifecycle driver or repository control files/Git and are retained as setup failures, not passing evidence.

Two independent current-byte reviews report no unresolved Spec or Standards finding. Existing broad #494, worker/media activation, custody, retention, field-performance observation and original later social phases remain open. This PR supplies the bounded compatible remediation for #689 only.
