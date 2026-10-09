# Batch 7 dependency exposure handoff

Lane: `batch7-dependencies`, branch `codex/batch7-dependency-remediation`.
Parent [#545](https://github.com/Rodgers31/audit_app/issues/545); retained residual issue [#494](https://github.com/Rodgers31/audit_app/issues/494).
Source commit: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`, tree `712b43650b1203ffd84583b67d07d30775669b1e`.
Author worktree: `/Users/roger/.codex/worktrees/batch7-dependencies/audit_app`.
The dirty primary checkout was read only. No other lane's installation or files were changed.

## Result

Move Tailwind, Autoprefixer and Transformers to development dependencies. Their complete build/offline installation remains available with `npm ci --include=dev --include=optional`; production runners use the existing Dockerfiles' post-build `npm prune --omit=dev --include=optional` boundary. Browser Transformers/WASM code remains in the built static chunks. Next's browser/server guards and tracing exclusions are unchanged.

Declare the already selected Sharp `0.35.5` explicitly as a production dependency. The initial classification-only lock regeneration marked shared Sharp platform binaries as development-only, causing actual image decoding to fail after pruning. The explicit runtime dependency retains them. The final lock has **no package version, resolved URL or integrity changes** relative to the source. Next remains `15.5.27`; Transformers remains `4.3.1`, ORT Node `1.30.0`, AdmZip `0.6.1`, and the accepted overrides remain intact.

Fresh production audit: five affected entries → zero. Fresh full audit: unchanged 38 affected entries (33 high, five moderate, zero critical). This removes vulnerable glob tooling from the pruned production installation; it does **not** patch braces/sprintf or certify every deployed asset, caller, platform or repository gate. Keep #494 open. Build workers and developer/test installations still carry the residual advisories.

## Current sources and caller exposure

Registry metadata and GitHub advisory API bodies were captured on 9 October 2026 UTC; see the hashed external evidence manifest and `RECEIPTS.md`. Issue #494's original October 3 version prose was superseded by its comments and the already merged #512 handoff at `docs/verification/2026-10-08-dependency-security.md`.

| Residual | Exact package / primary source | Inputs and execution boundary |
| --- | --- | --- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | braces `3.0.3`; registry latest `3.0.3`, advisory patched version null | Tailwind `3.4.19` content scanning via fast-glob/micromatch and CLI watching via chokidar; Next ESLint root globs; Jest test discovery, matching and diagnostic formatting. Patterns come from repository config/CLI. No application request-pattern importer was found in the reviewed application/scripts. That is a bounded caller inventory, not universal immunity. |
| [GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) | sprintf-js `1.0.3`; registry latest `1.1.3` is also affected, advisory patched version null | Jest/Babel coverage → `@istanbuljs/load-nyc-config` `1.1.0` → js-yaml `3.15.2` → argparse `1.0.10` → sprintf-js. Coverage YAML/config and CLI descriptions are local tooling inputs. No application formatter import was found. |

`npm why braces sprintf-js --json` captures every installed chain. Actual upstream callers include Tailwind `lib/lib/content.js:183`, `lib/cli/build/watching.js`, Next ESLint `dist/utils/get-root-dirs.js`, Jest `jest-config/build/normalize.js` and `jest-message-util/build/index.js:227`; micromatch's brace APIs at `index.js:427,451`; NYC YAML loader at `index.js:80`; argparse `lib/argument_parser.js:13,433,445`. These source paths refer to the exact owned installed versions, retained in the lock and external caller receipts.

Latest compatible Tailwind 3 is still `3.4.19`. Latest NYC loader still declares js-yaml 3; latest Babel Istanbul plugin also keeps the NYC loader. Forced Tailwind/Jest majors, downgrade of Next lint tooling, global native overrides, and an unsupported YAML-major override were not selected. Untrusted contributions/configuration can still reach build tooling; the production packaging mitigation does not establish a risk exception for those environments.

Transformers' actual native caller is `scripts/build-embeddings.mjs`. Browser search is `data/constitution/semantic-search.ts` → ONNX Web/WASM; the `typeof window` guard and `.next/server/app/learn/page.js.nft.json` inspection exclude the native model trees from the observed Learn server trace. The plain text query does not call brace/format APIs. Next image optimization still has untrusted image input exposure and retains the patched Sharp decoder. AdmZip remains an ORT installer dependency, available in full native environments but absent from the pruned runtime. The native text encoder does not process uploaded ZIPs.

## Executed acceptance

| Check | Actual outcome |
| --- | --- |
| Old pinned production installation, new runtime boundary check | **Red**, exit 1: Tailwind was still resolvable; separate baseline receipts resolve braces, micromatch, Transformers, ORT and AdmZip. |
| Fresh final full and production-only macOS installations | Pass; installed tree peer check (`npm ls --all --json`) exit 0. |
| Pruned runtime verifier | **Green**, macOS arm64 and emulated Linux x64; excluded packages fail resolution, Next/React/Axios resolve, actual Sharp PNG→WebP decoding succeeds. |
| Native model/ZIP/SVG/PNG/WebP/Transformers RawImage | Pass, macOS arm64 Node `22.19.0` and emulated Linux x64 Node `22.23.3`. Article 142 ranks first. |
| Actual unchanged embedding builder | Pass on both platforms: 264 × 384 finite normalized vectors, maximum norm error below `5e-7`; outputs only in owned fixture copies. |
| Full frontend Jest with coverage | 144 suites, 1,932 passed, one existing optional financial skip, zero failures. |
| Lint / TypeScript | Zero lint warnings/errors, `tsc --noEmit` exit 0. |
| Fresh production builds | Pass on macOS and emulated Linux x64, including built-in lint/type validation. |
| Complete macOS CSS | Same four content hashes before/after. |
| Actual pruned `next start` | `/api/health` and `/learn` succeed; real `/_next/image` HTTP 200 WebP on macOS. |
| Real Chromium Learn search, fallback and WASM | Two queries per context, model unavailable/available controls; real WASM required in available context, Article 142/43 first, zero unexpected external requests/page errors. Exact baseline/final results identical. |

The native model revision is `751bff37182d3f1213fa05d7196b954e230abad9`. Public model bytes were downloaded into an owned cache. The actual builder was copied byte-for-byte to an owned fixture with copied chapter files, and a preload selected those pinned bytes using local-only model configuration. It generated fixture outputs without rewriting committed embeddings. Browser fixtures fulfill only those public model/runtime resources; application UI, index, ranking and WASM computation are real. Native verification of the existing script needs public HuggingFace metadata even with a populated cache; its first network-disabled Linux run failed truthfully. The actual builder's local-only run avoids that transport. CPU execution is verified; GPU/CUDA execution is not.

The first broad Jest invocation supplied unnecessary inert Supabase configuration and failed two fake-timer retry cases; the same suite passes with that configuration unset. Builds/previews use explicit inert public config; this local acceptance is not production identity/configuration parity. The first Linux native replay raced a separate prune operation and failed package resolution; serial fresh install → native/tooling/builder → prune is the accepted replay.

## Review, remaining work and delivery

Independent adversarial verification and Standards/Spec reviews are recorded in `batch7-dependencies-evidence/REVIEW.md`. Reviewers receive the exact source SHA, originating issue and frozen spec. Any confirmed findings are repaired before the final scoped push. Coordinator owns integration with both ETL lanes, bot-review handling, issue closure and merge.

#494 stays open for upstream braces/sprintf fixes or a separately approved residual-risk disposition. No separate residual ticket duplicates it. No unrelated application defect is claimed fixed. Hosted Actions/security/quality checks remain unexecuted because Actions is disabled. Backend/ETL suites, all legacy browser journeys, other browser engines, native Linux hardware, Linux arm64/musl/Windows and GPU paths are outside this verification. Linux x64 runs under Docker Desktop emulation using `node:22-bookworm-slim` digest `sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`; `ONNXRUNTIME_NODE_INSTALL=skip` skips only optional GPU downloads and retains bundled CPU libraries.

Owned resources: preview `127.0.0.1:43193`, image fixture `127.0.0.1:43194`, inert Supabase address `127.0.0.1:58173`; Docker names start `batch7-dependencies-`; writable installations/caches/fixture outputs stay beneath `/Users/roger/.codex/worktrees/batch7-dependencies/`. Public browser binaries and the specified Node/Python runtimes were reused read only. External evidence is beneath `/Users/roger/.codex/visualizations/2026/10/09/01a11f2c-fce1-7ce0-9659-bb13eef9ca6c/batch7-dependencies/`. Cleanup and final source identities are recorded in the committed delivery receipts. No deployment, migration, publication, live provider/user/storage change, paid request or repository-policy change occurred.

## Coordinator Copilot repairs

The browser verifier now permits only complete approved HTTPS model URLs and complete installed-version ONNX Web CDN URLs. Twelve wrong-package/version/protocol/port/query/credential/path cases failed against the old actual route callback; all fifteen boundary cases pass after repair. The real Chromium fallback and WASM runs also pass with zero unexpected requests and page errors. The fixture intentionally serves pinned model bytes for the enumerated model URLs; that does not pin production model configuration.

`npm run test:dependency-boundaries` runs the browser transport regressions and installed-runtime regressions. Without `RUNTIME_VERIFY_ROOT`, it creates a fresh production-only installation in an owned temporary directory, leaving the build installation intact. The command is wired into the three existing frontend CI jobs; Actions remains disabled and these hosted jobs were not executed.

Coordinator review also found [#577](https://github.com/Rodgers31/audit_app/issues/577): the original destructive negative tests could follow a linked source installation and remove its Sharp decoders. The repair uses an explicit realpath-based owned clone, rather than relying on this Node runtime's ineffective `cpSync` dereference flag. The retained isolation regression runs the actual child suite against a disposable linked source and verifies the source decoder bytes and real Sharp decoding remain intact. Close #577 only after this repair is accepted and merged; #494 remains open. Final command counts and exact source identities are recorded in the coordinator acceptance receipts.

Final coordinator replay: the fresh standard command exits 0 with 15 URL controls and 9 runtime/isolation controls, no failures or skips. All 24,426 disposable source files retain their combined SHA256: `ebe1c2a4563cbb9424d0541a7ec738206707531a00e8c5e4150ff60b9218e1fb` in the fresh standard command, and `a30fdf38e2282c63dcb444be44acc5aff8e9cedf2e559b8e13381481910347f1` in the independent existing-installation replay. Their package manifests differ by the new test script. Actual Sharp decoding succeeds in both. The retained old-source replay has all five child tests green while deleting 18 disposable decoder files, so the outer ownership regression fails meaningfully. Seven changed verifier/test scripts pass zero-warning ESLint. The independent reviewer also rejects eight extra hostile URL forms, validates all three YAML job insertions, and checks the launcher failures/cleanup. Windows invocation is simulated only; Windows runtime compatibility is unverified.

Coordinator bulk logs and their SHA256 manifest are in `/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_7_REVIEW/DEPENDENCY_COORDINATOR_RECEIPTS.json`. Their failures and corrected passes are retained separately. This review adds test definitions and wiring without enabling Actions or changing repository rules.
