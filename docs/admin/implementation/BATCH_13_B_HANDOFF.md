# Batch 13 Lane B — Constitution asset admission

## Scope and source

Accepted base `c8970e3953717fc0f0ca3a54e22f7e3e509eec0f`, tree `1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8`. Exclusive branch `codex/batch13-constitution-asset-admission`; owned managed checkout `/Users/roger/.codex/worktrees/0ed4/audit_app`. Thread `01a1372d-e734-72c2-b955-706fa340f671`, title “Batch 13: Constitution semantic asset…”. Main was still the assigned base at the fresh prepublication readback; no rebase occurred.

Publication identity is appended after the scoped draft is opened. The final committed implementation/test blobs are compared with all successful rehearsal inputs; the final checkout is replayed before final publication. The external publication receipt supplies the exact final tip, tree and draft URL without a self-referential commit hash in this document.

This lane addresses [#637](https://github.com/Rodgers31/audit_app/issues/637). The broader dependency acceptance criteria for [#494](https://github.com/Rodgers31/audit_app/issues/494) remain unmet. Source admission does not certify hosted integration, deployment, all queries, native Linux inference, model-byte hostility, or legacy generation provenance. No package, lock, model builder/loader/manifest, shipped embedding asset, workflow, shared fixture or sibling-lane code changed. The dirty primary and peer sources/runtimes remain untouched.

## Contracts

`semantic-search.ts` now validates the asset boundary before model import/loading:

- Required model ID equals `embedding-model.json`, dimension is exactly 384, count is a positive safe integer, article count matches count, and byte length equals `count × 384 × 4`.
- Entries contain integer chapter/article IDs belonging to the actual Constitution metadata, a nonempty title, and no duplicate article identity.
- Every stored Float32 vector contains finite values and has L2 norm error strictly below `0.0001`, matching the accepted builder's output contract. Zero and oversized finite vectors refuse.
- Any explicitly supplied revision equals the pinned manifest revision. The accepted builder and shipped index omit revision; that legacy omission remains compatible. An omitted revision is not evidence of generation history. This lane does not authenticate arbitrary legacy assets by hash.

The query encoder must return a 384-element Float32Array with tensor dimensions `[1,384]`, finite values, and the same normalization bound before scoring. Admission failures log only a bounded reason, without query or payload, and return the existing semantic-unavailable `[]`. Network/model failures retain the existing unavailable behavior. No new retry/deadline/skip policy was introduced.

`runSearch` uses this shared boundary for keyword hybrid search and preserves BM25 fallback. `LearnHero` warm-up enters the same loader. Existing warm rejection is cleared when search observes it; a later valid asset can reload. Query refusal retains an otherwise valid loaded index and validates the next output again. Article-number lookup does not load embeddings. Builder/native-verifier boundaries are separate and unchanged.

## Executed evidence

External root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH12_CONTINUATION_V1/NEXT_AUTHORS_V1/B_constitution_asset_admission`.

Each command packet preserves complete raw stdout/stderr, runner JSON where available, actual command/exit/environment, generator hash, full required source hashes before/after, owned process-group and OS-temporary-directory cleanup readbacks. These local records are not GitHub-hosted logs. Counts overlap and are not additive unique coverage.

| Packet | Actual result |
| --- | --- |
| `red-base-unit-v2` | Exact accepted consumer, unchanged final regression fixture: 63 cases executed, 20 pass / 43 expected assertion failures / 0 pending. Stored/query NaN becomes NaN score; explicit incompatible revision admits a hit. |
| `green-unit-v1` | Same fixture bytes after repair; 66 focused cases pass, 0 fail/pending (63 new plus 3 existing loader cases). |
| `full-unit-v1` | Complete default Jest: 150 suites, 2161 pass, 0 fail, one exact existing pending PostgreSQL reader in `BudgetTab.debtAbsence.test.tsx`. All 63 new mandatory cases execute. |
| `typecheck-v1` | Standalone TypeScript check exits 0, source unchanged. |
| `production-v2-build` | Locked Next production build exits 0, compile/lint/types and 42-page generation complete. |
| `production-v2-browser` | Nine actual Chromium cases pass, zero skips/pageerrors/unexpected egress. Network-unavailable, NaN stored, short stored, wrong dimension, wrong model, stale explicit revision, absent index, malformed JSON, genuine WASM. |
| `production-v2` | Owned API/preview/browser orchestration exits 0; preview group/API thread/OS temp absent and both ports bindable afterward. |
| `spec-review-v1` | Independent focused Jest 66 pass; independent actual-source VM 23 controls including exact-base NaN reproduction; no actionable finding. |
| `standards-review-v1` | Independent focused Jest 66 pass and default discovery; independent VM 34 controls; normal/optimized recorder outcome controls; no blocker. |

Seven malformed/absent browser controls preserve the exact rendered keyword baseline and make zero model/runtime requests. Genuine WASM uses approved real model bytes, instantiates the actual locked runtime and changes the presidential-term top Article 180 fallback to Article 142; health-care top Article 43 remains. This proves measured queries on macOS ARM64, not every index/query or a native Linux target. Model doubles in admission tests do not establish inference.

Preserved failures: original 180-second storage timeout; first v2 cache-binding refusal; `red-base-unit` npm pretest refusal before Jest; first direct red fixture's explicit-undefined default corrected before the canonical red; `production-v1-build` missing public Supabase configuration after successful compilation/lint/types; reviewer invocation/generator mistakes retained separately. None is relabeled passed or counted as successful acceptance.

## Runtime, isolation and cleanup

Node 22.19.0, Darwin ARM64; Next 15.5.27, Jest 30.5.2, TypeScript 5.9.3, Transformers 4.3.1, Playwright 1.58.2, ONNX Web `1.31.0-dev.20260914-8d85527a0`. Exact accepted lock SHA256 `46569a23bd8d750b57e2d0dc44b0ddf6c8498a27c22ea82d0a8e5c80b88858dc`; 902 installed records checked for version/resolved/integrity with no mismatch. Compatible dependencies were borrowed read-only through an owned symlink, with actual tooling repair check reporting zero changed files. Npm's pretest correctly refuses that symlink; direct Jest/Next CLI rehearsal is explicitly distinct from lifecycle/npm-entry acceptance in a fresh real installation.

The four retained fixed-revision public model files were checked with the actual manifest verifier, then supplied read-only to actual WASM. No model download or dependency install occurred. Python 3.13 is used only for lane recording/storage tools; there is no backend/database/minimum-SQLAlchemy claim.

API `http://127.0.0.1:18062` always returns an explicit 503 unavailable state. Preview is `http://127.0.0.1:13062`. Build/preview public Supabase URL is the same inert API endpoint and key is literal `batch13-constitution-inert-anon-key`; there are no live credentials or authentication requests. Unit environment leaves public Supabase inputs unset, preserving the canonical cohort and Lane C's separate fixture scope. Browser contexts deny all unexpected external requests. No financial-source write, database/role, provider, worker, container/network/volume, migration, release or production deployment occurred.

Temporary fixtures use unique owned OS directories and finally cleanup. Browser/context cleanup and exact preview process group cleanup are retained. Final local build-output/symlink disposition and remote readback are recorded externally after publication; peer/cache/runtime assets are retained unchanged.

The repaired coordinator storage guard is used with the canonical current Python, fresh distinct receipts and unchanged shared 10 GiB baseline/budget/180-second bound. Earlier guard failures remain historical failures. Initial fresh passing growth was 5,009,580,032 bytes; later phase measurements are in `storage-*.json` and are shared observations, not lane attribution.

## Replay and coordinator next steps

From a reviewed real frontend installation, normal `npm test -- --runInBand` discovers both focused suites. Targeted command: `npm test -- --runInBand --runTestsByPath __tests__/semanticAssetAdmission.test.ts __tests__/semanticSearchLoader.test.ts`. No gate is disabled for a real installation. Run `npm run build` with explicit inert public API/auth inputs and serve an owned production preview on assigned port 13062. Set `DEPENDENCY_PREVIEW_URL=http://127.0.0.1:13062`, `NATIVE_VERIFY_CACHE_DIR` to the verified fixed-revision model cache and `PLAYWRIGHT_BROWSERS_PATH` to the verified installed browser; run `node tests/constitutionAssetBrowser.cjs`. Its mandatory cases are not prerequisite-skipped and its fixture selector is unchanged.

Coordinator owns combined exact-source hosted verification, Actions, review/merge gates, parent issue census/closure and any deployment decision. Keep #494 partial. No author merge, Actions enablement, paid review, issue closure or production step is supplied here. Consider the final source/remote readback and complete unchanged integrated gate before disposition of #637.

Proposed skill lesson (coordinator decides): a default argument can transform an explicit missing-input test into a valid fixture. Here `assets(undefined)` initially substituted default metadata; distinguishing omitted arguments from explicit undefined before the canonical red/green replay corrected that control. No global skill was edited.
