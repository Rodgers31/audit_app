# Independent reviews

Source base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`; reviewed implementation head: `13583591682eeaf054e9f4f17b1fb5c3f106a1f2`. Origin #494, parent #545, frozen Batch 7 spec. Standards and Spec agents reviewed the same pinned-base diff independently in parallel. A separate adversarial agent executed hostile runtime/browser cases. Raw reports and hashes are indexed in `artifact-manifest.json`.

## Standards

One initial P3 documented-standard finding: `frontend/README.md` Contributing rule 5 requires JSDoc for complex functions. Add function documentation for recursive package inspection and the browser verification driver. No other documented-standard violations or actionable Fowler-baseline smells found. Independent read-only inspection confirms 963 package versions/URLs/integrities are retained and all three added scripts pass syntax checks.

**Resolution:** author added JSDoc to traversal and both verification entry points. The Standards reviewer inspected the comment-only additions and repeated syntax checks: zero unresolved Standards findings. Scoped ESLint also exits 0. This follow-up changes documentation only; runtime implementation remains the reviewed implementation.

## Spec

No concrete implementation defect or scope creep found. Independent read-only checks confirm unchanged locked package identities, successful actual pruned Sharp decoding, identical browser results and all four CSS hashes. Raw audits support production 5→0 and full 38→38. Disclosed upstream advisories and platform/hosted limits justify keeping #494 open.

One initial delivery-only gap: complete committed review receipts, the referenced delivery record and linked artifact hashes before delivery. **Resolution:** this report, `DELIVERY.md` and `artifact-manifest.json` complete those records; final independent documentation replay is retained externally. No runtime change was needed.

Standards: one initial P3, resolved, zero open. Spec: one initial delivery-documentation gap, resolved, zero implementation defects or scope creep.

## Adversarial execution

One confirmed P2 false green: a real nested `next/node_modules/braces` package remained callable while the first verifier checked only root resolution and announced absence. Author reproduced the exact original success verdict before editing (`adversarial-nested-red.log`), implemented inspection of all installed npm directories and strict dependency-map shapes, and retained the rejecting replay (`adversarial-nested-green.log`). The real installed decoder positive control continues to pass. The persistent real-installation regression passes five tests (parent plus four subcases): decoder control, nested actual locked braces, malformed manifest, all Sharp decoders missing. It accounts for legitimate Sharp WASM fallback rather than falsely declaring one missing platform binary fatal.

Exact reviewed-head independent replay checks the real pruned runtime, absent/empty/malformed roots, full/baseline installations, missing Sharp/native support, nested forbidden packages, malformed dependency maps and all four additional exclusion names. The final runtime verifier reports the precise 16-name exclusion list rather than a general security verdict. No unresolved finding. A reconstructed original verifier also fails the persistent regression, but its pre-edit byte identity was not captured; that reconstruction is supplementary. The directly executed original false-green receipt is authoritative.

Eight browser failure cases correctly reject unavailable/bad URLs, absent browser/model fixtures, corrupted ONNX/tokenizer and denied/corrupted WASM. Positive controls require real WASM and changed semantic ranking against BM25 fallback. They execute the actual app/UI/runtime with hostile resource bytes, not mocked search functions.

Independent adversarial execution covers macOS arm64. Author-owned Linux x64/native/build/prune controls are separately recorded. Neither review certifies arbitrary package/model authenticity, every query, deployed readiness or missing platform/hosted gates.
