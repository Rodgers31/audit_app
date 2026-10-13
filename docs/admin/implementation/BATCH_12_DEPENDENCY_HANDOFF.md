# Batch 12 dependency handoff — partial #494

## Scope and publication identity

Accepted base: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree `3a680eef19822ef0ac83aa6890c3b41deee97058`. Author branch: `codex/batch12-dependency-remediation`; isolated checkout `/Users/roger/.codex/worktrees/batch12-dependency-remediation/audit_app`. The primary checkout was read only. Draft [PR638](https://github.com/Rodgers31/audit_app/pull/638) first published product commit `e9bf022486fd18ae561837074dd879e926c8f4f0`. The 2026-10-12 continuation froze that clean source for all fresh runtime/platform checks; its second round changes only this handoff. Resolve the final draft head with `gh pr view 638 --json url,headRefOid,isDraft`; `resumed-publication-receipt.json` records remote readback and committed product bytes. Each round uses one finished nonforce push.

No dependency range, lock record, Python range, SQLAlchemy contract (`>=2.0.23,<2.1`), CI/workflow, Dockerfile, shared configuration, shipped embedding binary/index or peer lane file changed. No database, migration, production deploy, Actions enablement, provider operation or paid review was requested. No deployment dependency on another Batch 12 lane. This draft addresses one bounded input/output defense; compatible full remediation and target-platform acceptance for [#494](https://github.com/Rodgers31/audit_app/issues/494) remain unmet.

Product source inventory SHA256: `81cd7b961da814d51e62b9ea0f26aed922b9600aecdc3f10db07f12238d1f8f7` (canonical sorted compact JSON path→SHA256 map in external `tested-product-source.json`). Original prepublication receipts measured working source at the accepted base plus candidate changes; they do not claim the base commit contained the fix. Continuation receipts bind the clean committed e9bf022 source before and after execution. Final publication compares committed product blobs to the same inventory and records the documentation-only continuation diff. This handoff is outside that product inventory.

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
| Complete default dependency command after approved cleanup | PASS: `resumed-default-runtime-01`, actual `npm run test:dependency-boundaries`: 143 Node controls and nine installed-runtime tests (five parent/four nested), zero failures/skips; fresh lifecycle production install 172 packages; actual pruned Sharp decoding, malformed/nested exposure refusals and source isolation 24426 files unchanged. `resumed-default-runtime-launch.json` verifies owned OS temporary directory absent |
| Historical default dependency failures | FAILED and retained: `dependency-controls-final` and `dependency-controls-cow`; each Node portion passed 143, fresh production installation succeeded, runtime deep-copy cases hit ENOSPC (3 pass/2 fail parent tests). Fresh acceptance above does not relabel these failures |
| Production audit | PASS: `final-audit-production`, zero entries |
| Full developer/build audit | NONZERO: original macOS `final-audit-full` 26 entries (7 high/19 moderate); fresh Linux ARM64/amd64 audits 27 entries (8 high/19 moderate), exactly two unchanged advisory roots. Added propagated entry is `@tailwindcss/typography` via Tailwind. Actual full-audit exits 1 are retained; platform runtime PASS is not an audit PASS |
| Installed dependency graph | `npm ls --all --json` exits 0 at `final-graph` and both fresh Linux runs; expected Next/Sharp/Transformers versions resolve. Raw outputs retain optional `@emnapi/runtime` and `@img/sharp-wasm32` extraneous diagnostics; no diagnostic-free graph claim. Earlier explicit include variant also reported invalid diagnostics (`baseline-graph.json`) and remains separate |
| Pinned Linux ARM64 | PASS: `resumed-linux-arm64-02/receipt.json`, native ARM64 on the ARM64 Docker VM; lifecycle full install 837 packages/ten repairs, actual CPU/vector/ranking/ZIP/both Sharp adapters, fresh production install 145 packages, excluded 16 package names absent with real image decode, production audit 0 |
| Pinned Linux amd64 emulation | PASS: `resumed-linux-amd64-02/receipt.json`, same checks/counts as ARM64, Linux x64 process on ARM64 Docker host. This is emulation and does not certify a native x64 host |
| Native deployment-target x64 | NOT EXECUTED: no native x64 environment available here. Original Docker cannot-start/hung diagnostic failures remain historical (`docker-*`, `final-docker-diagnostic-timeout.json`); current Docker availability and current emulation do not retroactively establish native x64 acceptance |

Counts overlap; do not add control counts. Fresh repository Actions readback remains OFF (`resumed-actions-permissions.json`; eight workflow states in `resumed-actions-workflows.json`). The exact product head e9bf022 now has automatic Vercel SUCCESS and Preview deployment 7020075818 success, retained in `resumed-e9bf022-*` and `resumed-deployment-7020075818-statuses.json`. No review requests/findings/threads were present in the complete fresh readback. Provider resolved install/build settings, cache behavior and production acceptance remain unverified; a Ready state does not satisfy those or native-target criteria.

## Guarded continuation and platform identity

The approved cleanup result and final verification were read before resuming. The fixed shared visualization baseline is 188380164096 bytes; the growth limit is 10737418240 bytes. Normal-Python `storage-guard.py check` ran before/after dependency installs, native tests and image phases with fresh immutable receipts. All checks passed. Final observed shared growth was 3687690240 bytes (3.43 GiB); this is a shared measurement, not an attribution to this lane. No baseline reset or historical/peer cleanup occurred.

Current official `node:22-bookworm-slim` index is `sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`. Exact selected manifests/image IDs are ARM64 `sha256:b20fe038d9592822dd534600a1ddf467e985178aa3fed60ec441a056c2cc45bd` and amd64 `sha256:efd0ab5780c2d9ab1f0f869571a00d5edb17793bff4cce4a2792e3eb0ffc7562`. Official OCI index metadata, daemon/image/container inspections and actual Node 22.23.3/npm 10.9.9 outputs are retained in each platform packet. The daemon is Linux/aarch64 Docker Desktop; amd64 execution is explicitly emulated.

Both actual entrypoints used the clean e9bf022 frontend and approved model snapshot as read-only mounts, with separate owned Linux dependency volumes and `volume-nocopy`. Full and production installs retained lifecycle scripts; `ONNXRUNTIME_NODE_INSTALL=skip` excludes the optional GPU download, while actual CPU inference executes. Existing macOS dependencies were not reused in Linux. ARM64/x64 emulation Article 142 compatibility cosines were 0.9959701196829802/0.9959702126804159 against the unchanged 0.99 floor; this tests that article and ranking, not every shipped vector. All command output hashes were checked against receipts; source, generator and inventory remained unchanged. Exact labeled containers/volumes were removed and verified absent. The official base images remain cached; no daemon reset/prune or shared image removal occurred.

The first current ARM64 attempt stopped before installation because Docker Desktop reported the model bind using `/host_mnt` plus its exact host path. Its failed `resumed-linux-arm64-01` receipt and successful ownership cleanup remain immutable. Fresh `resume-linux-v2.py` admits only the two exact observed model-path representations while requiring read-only mounts and actual model byte checks. It is an author-path historical recorder frozen to e9bf022, not a portable CI tool.

Independent controlled execution found 16 false-green recorder inputs; the author reproduced them before repair (`resumed-linux-author-red-reproduction.json`). Original outcomes and frozen generator bytes remain retained. The corrected v2 generator SHA256 is `4884ed7becb7478c90818e855f0a13d4574e8ee0c951cf85a019699cd470a05b`; `adversarial-caller/adversarial-resume-linux-03/REPORT.md` records 61 executions: three valid positives and 58 hostile refusals, including malformed/error audits, wrong identities/configuration, duplicate/writable mounts, missing outputs, source/generator/inventory drift and path translations. All tiny OS temporary fixtures were removed. These doubles verify recorder refusal behavior; actual Linux acceptance comes from the separate real platform packets above.

## Root advisories and decision

The full audits retain [braces stack exhaustion](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [sprintf-js unbounded precision](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). Fresh 2026-10-12 npm registry/GitHub advisory API and official-page readbacks still show braces latest 3.0.3 and sprintf-js latest 1.1.3, with no patched version for either advisory. The installed sprintf-js is 1.0.3. Latest `@istanbuljs/load-nyc-config` remains 1.1.0 and requires js-yaml 3.x; the actual Jest→Istanbul→js-yaml→argparse→sprintf chain remains. Tailwind/Next lint glob consumers retain braces via chokidar/micromatch and fast-glob. Fresh labels `resumed-upstream-*` and `resumed-GHSA-*.json` supplement the original exact chains/registry metadata; audit counts do not establish those chains.

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

Before accepting or merging: obtain actual native deployment-target x64 acceptance; complete compatible remediation for both residual advisory roots; verify full integrated/affected CI when independently authorized; read automatic deployment metadata at the final PR head, including resolved install/build context and cache behavior. The default/runtime cohort and current pinned Linux ARM64/emulated-amd64 checks are now complete and source-bound above. Keep #494 partial until its full acceptance criteria are proved. This lane does not enable Actions or deploy manually.

Owned preview/browser groups and listeners were stopped and verified absent. No database/backend listener was created. Current temporary Linux containers and dependency volumes were removed after exact ID/label checks; no owned Linux resources remain. Only owned disposable npm/build caches were deleted in the original phase after recording paths/lengths/hashes (`owned-*-cleanup*.json`); the historic cleanup manifest was not executed again. Existing installed macOS dependencies, model snapshots, builder outputs, raw failures/reports and protected source fixtures remain available. New fixture repositories used owned OS temporary directories with verified cleanup. No peer/global cache cleanup occurred.

Recommended skill lesson (proposal only; no global skill changes): dependency-auditor/verify-test-prod-parity should require observing every actual discovery request, not only the final pipeline options. Concrete example: Transformers 4.3.1 accepted a revision option but preflighted config and tokenizer metadata at `main`; the strict real browser caught it while source-bound option doubles passed. Also match canonical CI environment before attributing unit failures: inert valid Supabase settings changed fake-timer/auth behavior even though credentials were safe.

Continuation lesson for receipt-provenance/adversarial-verify: validate actual mount/configuration identities and measured output schemas, not just command exits. The recorder's original duplicate-mount dictionary collapse and error-bearing audit JSON both returned false PASS in literal controlled execution. Fixes required a healthy positive as well as hostile refusals; the observed Docker Desktop path translation needed an exact tested alias while retaining read-only/content authority.


## Coordinator review follow-up — #644

The historical author runtime/platform packets above remain immutable. The
coordinator addresses Copilot's body-only summary findings with a shared
manifest import in the actual browser consumer, route selector and browser
verification entry. The approved model/revision and shipped asset bytes remain
unchanged. Three default Jest controls execute the actual loader with declared
model/transport doubles: shared-revision valid ranking, tokenizer refusal and
model-load refusal. An altered manifest revision reproduces the old consumer's
stale constant (one intended failure, two refusal positives); the repair passes
all three. These tests certify caller contracts, not real WASM inference.

Both canonical CI and bounded manual full verification now invoke the existing
CPU/image/installer verifier on the native hosted x64 runner, using an owned
temporary model cache removed by an EXIT trap. The seven job contracts and
existing deadlines are preserved; this step has a five-minute bound. Actual
hosted native acceptance is recorded separately before merge. Local review
controls, typecheck and all 112 workflow-boundary tests pass in
BATCH_12_REVIEW/638_REVIEW_LOCAL. Residual advisory remediation and production
provider acceptance in #494, and asset-reader validation in #637, remain open.
