# Batch 12 dependency handoff — partial #494

## Scope and publication identity

Accepted base: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree `3a680eef19822ef0ac83aa6890c3b41deee97058`. Author branch: `codex/batch12-dependency-remediation`; isolated checkout `/Users/roger/.codex/worktrees/batch12-dependency-remediation/audit_app`. The primary checkout was read only. Resolve the published draft URL/head with `gh pr view codex/batch12-dependency-remediation --json url,headRefOid,isDraft`; the final external publication receipt records exact remote readback. This handoff and all product changes are committed together before one nonforce push.

No dependency range, lock record, Python range, SQLAlchemy contract (`>=2.0.23,<2.1`), CI/workflow, Dockerfile, shared configuration, shipped embedding binary/index or peer lane file changed. No database, migration, production deploy, Actions enablement, provider operation or paid review was requested. No deployment dependency on another Batch 12 lane. This draft addresses one bounded input/output defense; compatible full remediation and target-platform acceptance for [#494](https://github.com/Rodgers31/audit_app/issues/494) remain unmet.

Product source inventory SHA256: `81cd7b961da814d51e62b9ea0f26aed922b9600aecdc3f10db07f12238d1f8f7` (canonical sorted compact JSON path→SHA256 map in external `tested-product-source.json`). Every passing runner receipt records the measured source bytes at the accepted base plus staged candidate changes; these are working-source measurements, not a claim that the base commit already contained the fix. Final publication compares committed product blobs to that inventory. The documentation itself is outside that product inventory.

## Implemented behavior

`embedding-model.json` binds four public model artifacts to exact lengths and SHA256 values at `Xenova/all-MiniLM-L6-v2`, revision `751bff37182d3f1213fa05d7196b954e230abad9`. The official exact-revision API metadata (Git blob identities for JSON and LFS SHA256 for quantized weights) is retained in `official-model-api.json`; downloaded bytes match it and the manifest.

The native verifier and builder share `embedding-model.cjs`: refuse modified retained files before any download; reject unknown inventory, source links and linked ancestry; bound downloads to expected bytes and a 60-second request deadline; publish exclusively and verify readback. They load the checked absolute snapshot with remote/FS/browser/custom library caches disabled and `local_files_only: true`. The cache is trusted against concurrent local filesystem writers; this is not a transactional hostile-filesystem sandbox. Missing files may be downloaded, while damaged retained files are never silently refreshed. Review/delete an owned invalid cache explicitly before retrying.

The builder admits only finite, normalized 384-element Float32 vectors with `[1,384]` dimensions before writing outputs, and disposes its pipeline on refusal. The full 264-article builder produced identical 405504-byte output twice using actual CPU inference; article identities/order and normalization were checked. These outputs remain external; shipped assets were not regenerated.

The browser adapter loads the known BERT tokenizer JSON at explicit fixed-revision URLs and constructs `BertTokenizer`, then loads `AutoModel` at that revision and constructs the same `FeatureExtractionPipeline`. Transformers 4.3.1 `pipeline()` and `AutoTokenizer` discovery both issue requests at `main` despite a revision option; real browser failures exposed both paths. The selector still rejects `main`, wrong revisions, unapproved origins/protocols/files and URL decoration. Browser pinning uses HTTPS revision identity; the Node manifest byte guard is not claimed as browser cache/content authentication. Existing keyword fallback and actual semantic rankings are preserved.

The default dependency control command now includes 22 model-input controls and seven builder-output controls. The two new revision-refusal controls reuse the actual browser route selector. Output doubles test admission only; actual CPU and browser WASM acceptance are separate receipts.

## Recorded verification

Runtime: macOS 27 ARM64, Node 22.19.0, npm 11.6.0, Next 15.5.27, Transformers 4.3.1, ORT Node 1.30.0, ORT Web `1.31.0-dev.20260914-8d85527a0`, Sharp 0.35.5/libvips 8.18.7, adm-zip 0.6.1. `final-runtime-catalog.json` records resolved entry paths/hashes. Playwright 1.58.2 selected the existing Chromium cache binary; its hash is recorded. No new browser download provenance is claimed.

| Check | Result and receipt label |
| --- | --- |
| Clean and cached candidate npm ci, dev/optional included, lifecycle checks enabled | PASS: `candidate-clean-install`, `candidate-cached-install`; 901 packages each, existing exact tooling repairs applied |
| Full unit selection after final adapter and cached install | PASS: `final-unit`; 148 suites, 2095 passed, one unchanged existing pending test, zero failed |
| Production build including lint/types | PASS: `production-build-explicit-tokenizer`; inert loopback API 18063, no real service/credentials |
| Standalone typecheck | PASS: `final-typecheck` before final explicit-tokenizer edit; final build also checks final types |
| Lint | PASS: `lint` (existing warnings); final build checks final lint |
| Native CPU/vector/ranking/image/ZIP | PASS: `candidate-native-fresh` with fresh official model download; `post-install-native` after cached install. Both Sharp caller adapters decode SVG/PNG/WebP, actual installer ZIP extracts, Article 142 embedding/top-rank checks pass |
| Actual full builder, twice | PASS: `actual-builder`; deterministic 264×384 output, finite normalized values and article ordering |
| Final dependency Node control selection | PASS: `final-dependency-node-npm-entry`, 143 tests, no skips, through actual offline npm entry; subset `final-model-controls`, 46 tests (overlap). Direct-node attempt correctly refused seven required npm-entry prerequisites (136 pass/7 fail), retained separately |
| Default dependency command | FAILED: `dependency-controls-final` and `dependency-controls-cow`; each Node portion passed 143 controls, fresh production installation succeeded, runtime deep-copy cases hit ENOSPC (3 pass/2 fail parent tests). No complete runtime suite acceptance is claimed |
| Production audit | PASS: `final-audit-production`, zero entries |
| Full developer/build audit | NONZERO: `final-audit-full`, 26 propagated entries (7 high/19 moderate), exactly two direct advisory roots; runner correctly records FAILED |
| Installed dependency graph | PASS: `final-graph` (`npm ls --all --json`); earlier explicit include-dev/include-optional variant reported extraneous/invalid diagnostics and is retained as `baseline-graph.json`, not relabeled |
| Linux/current native x64 | NOT EXECUTED: Docker Desktop cannot start; original exact failures retained as `docker-*`; latest read-only Docker diagnostic hung and was stopped only after matching its PID, argv and owned output descriptor (`final-docker-diagnostic-timeout.json`). Historical emulation proves neither current Linux nor native target acceptance |

Counts overlap; do not add control counts. Repository Actions readback remains OFF (`actions-permissions.json`, all static workflow states in `actions-workflows.json`). A passing inherited scanner or a provider Ready state would not satisfy missing dependency/target-platform criteria.

## Root advisories and decision

The final full audit retains [braces stack exhaustion](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [sprintf-js unbounded precision](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). Fresh registry checks show braces latest 3.0.3 and sprintf-js latest 1.1.3; both advisories have no fixed version. The installed sprintf-js is 1.0.3. Latest `@istanbuljs/load-nyc-config` remains 1.1.0 and requires js-yaml 3.x; the actual Jest→Istanbul→js-yaml→argparse→sprintf chain remains. Tailwind/Next lint glob consumers retain braces via chokidar/micromatch and fast-glob. Exact chains and registry metadata are external, not inferred from audit counts.

npm's suggested Tailwind major migration/Jest downgrade is not a compatible scoped fix. Keep the accepted #620 source-bound tooling repairs and literal input controls intact; do not remove peer-required packages or force an unproven graph. Native input admission makes the newly demonstrated mutable-model acceptance narrower, but it does not remove either advisory root or certify complete native/framework compatibility. No accepted exception or complete security remediation is asserted.

## Failures, adversarial evidence and follow-up ownership

- Original actual native verifier accepted a modified retained config (`baseline-damaged-model`) while still producing valid embeddings. Candidate actual verifier refused the same damaged cache (`candidate-damaged-model-frozen`) before native parsing/download. The first candidate attempt also had source drift and remains failed separately.
- Original builder passed six malformed output cases in the exact same fixture; original replay `builder-output-baseline` records one valid pass and six expected assertion failures. Candidate `builder-output-controls` passes all seven. Independent caller controls reproduce NaN/short-vector behavior at base and refusal after repair. Native/model doubles are explicitly distinguished.
- An intermediate native verifier lost the `tmpdir` import; `candidate-native-first` failed and independent caller controls confirmed it. The import was restored; corrected actual native checks pass.
- First full unit/runtime attempts suffered ENOSPC. The unit run also contained two repeatable failures with inert valid Supabase settings; those are a separate fixture-isolation defect, tracked as [#636](https://github.com/Rodgers31/audit_app/issues/636). Canonical unit commands match CI's unset public configuration; no assertions, retry policy or skip set were weakened.
- An intermediate build hit ENOSPC after compilation/type checks; the runner could not save its receipt. `production-build-incomplete-receipt-classification.json` preserves this qualification and raw outputs. Later successful builds are separate attempts. A fresh-native runner mkdir also failed before launch; it is distinct from the later successful run.
- Two strict actual browser attempts failed on mutable config and then tokenizer discovery requests. Final explicit-tokenizer replay passes fallback and WASM with zero unexpected external requests, top Articles 142/43, Learn/CSS HTTP 200 and owned process/listener cleanup.
- Copy-on-write fixture optimization was investigated and independently passed small isolation controls, but full command still hit ENOSPC. It was reverted; attempted bytes and reports remain external. No retrospective resource-cause proof is asserted.
- The inherited semantic asset reader can return NaN scores for malformed vectors and ignores incompatible model/index metadata. Exact original-source replay reproduces it. It is tracked as [#637](https://github.com/Rodgers31/audit_app/issues/637), with explicit frontend semantic-consumer ownership and fallback/actual-browser acceptance. Builder protection does not repair the reader.

Complete seven-page all-state issue/PR census, #494 body/comments and merged #593/#620 review bodies/inline/dispositions were inspected. All 13 #620 review threads are resolved, and comment/thread pagination reports no omitted pages. #357 was read before filing #636; it covers completed retry policy rather than this fixture isolation. No paid reviews were requested.

Independent adversaries: `adversarial-model/REPORT.md` records 65 corrected-harness controls, valid repeated-cache zero-fetch positives, same-size/sparse corruptions, links/unknown entries and a real 60-second stalled-body abort; its first NUL-path diagnostic mismatch is retained. `adversarial-caller/REPORT.md` records 10 actual caller damaged-cache refusals, original/candidate output controls and source identities. Final adapter/model inspection is retained in `adversarial-caller/adversarial-browser-adapter/REPORT.md`: actual locked web loader traces only pinned config/ONNX URLs, and real installed tokenizer/pipeline with controlled Tensor output validates caller shape/pooling/cache/refusal behavior. Setup attempts during npm reinstall remain failures; controlled outputs do not certify WASM inference. These controls are not Linux/WASM acceptance certificates.

## Evidence and replay

External packet root (local, not GitHub-hosted):
`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/DEPENDENCIES`.

`run.py` SHA256 `8e580c07995be856c56fbf6e5b752df0ada94b862c53bf4ef8e20796718b6e90` is an author-machine historical recorder with an explicit owned worktree path. Each `runs/<label>/receipt.json` binds command, safe environment, product/source hashes, stdout/stderr hashes, child outcome and survivor/source-drift flags. Do not present this hardcoded recorder as portable. Existing packet files were not overwritten to turn failed runs green. The preview producer is an external copy of accepted Batch 11 replay with only lane ports/key changed; original bytes and both producer hashes are retained. Its owned UI port is 13063; 18063 is an inert API target, not a spawned backend.

Portable commands from a fresh reviewed checkout's `frontend`, using a scrubbed environment and an absolute owned model cache:

```sh
npm ci --include=dev --include=optional --no-audit --no-fund
npm ci --include=dev --include=optional --no-audit --no-fund
npm ls --all --json
npm audit --omit=dev --json
npm audit --json
npm run test:dependency-boundaries
env -u NEXT_PUBLIC_SUPABASE_URL -u NEXT_PUBLIC_SUPABASE_ANON_KEY -u NEXT_PUBLIC_API_URL npm test -- --runInBand
npm run lint
npx --no-install tsc --noEmit
env NEXT_PUBLIC_API_URL=http://127.0.0.1:18063 npm run build
npm run verify:native
```

Set `NATIVE_VERIFY_CACHE_DIR` to an absolute real owned directory for native downloads. Run `npm run verify:dependency-browser` against a separately owned production preview, setting `DEPENDENCY_PREVIEW_URL` to its loopback origin, the same model cache, and the selected Playwright browser directory. The browser entry aborts all non-approved external requests and validates actual ranking; do not relax its selector or substitute model/runtime fixtures from a different version. Replay full builder in an external source-bound fixture if shipped assets must remain unchanged.

## Coordinator next actions and resource handoff

Before accepting or merging: rerun the complete default dependency/runtime cohort with sufficient independently owned capacity; obtain current pinned-image Linux ARM64 and actual native deployment-target acceptance (x64 emulation must be labeled separately); verify full integrated/affected CI when independently authorized; read actual automatic deployment metadata at the exact PR head, including resolved install/build context and cache behavior. Do not enable Actions or deploy manually for this lane. Keep #494 partial until its full acceptance criteria are proved.

Owned preview/browser groups and listeners were stopped and verified absent. No database/container/backend listener was created. Only owned disposable npm/build caches were deleted, after recording paths/lengths/hashes; `owned-*-cleanup*.json` preserves identities. Installed dependencies, external model snapshots, actual builder outputs, raw failures, reports and source fixtures remain available. No peer/global cache cleanup occurred.

Recommended skill lesson (proposal only; no global skill changes): dependency-auditor/verify-test-prod-parity should require observing every actual discovery request, not only the final pipeline options. Concrete example: Transformers 4.3.1 accepted a revision option but preflighted config and tokenizer metadata at `main`; the strict real browser caught it while source-bound option doubles passed. Also match canonical CI environment before attributing unit failures: inert valid Supabase settings changed fake-timer/auth behavior even though credentials were safe.
