# Retained evidence for #494

This is a blocked-path investigation, not a remediation PR or residual-risk exception. See [the committed handoff](../BATCH_10_DEPENDENCIES_HANDOFF.md). All frontend source bytes still equal `f6c31e271297eece52f34102dc40a1e2ed7069a8`.

From the repository root, Python 3.9+ can verify the published packet without dependencies or network:

```sh
python3 -O docs/admin/implementation/batch10-dependencies-evidence/verify_bundle.py docs/admin/implementation/batch10-dependencies-evidence/evidence-v1.zip docs/admin/implementation/batch10-dependencies-evidence/evidence-v1.manifest.json
python3 -O docs/admin/implementation/batch10-dependencies-evidence/test_recorder.py
python3 -O docs/admin/implementation/batch10-dependencies-evidence/test_bundle.py docs/admin/implementation/batch10-dependencies-evidence/evidence-v1.zip docs/admin/implementation/batch10-dependencies-evidence/evidence-v1.manifest.json
```

The archive inventory and SHA256 are pinned by the adjacent committed manifest. Original generator source is archived; the current verifier and its repaired tests are committed and also saved in validation-history-v2.zip. They check exact members, streams, historical generator identities, child/wrapper exits, stability verdicts, final Jest counts/assertion inventories, audits and regenerated builder structure/numerics. The current 14 bundle controls and 8 recorder controls reject missing/empty/malformed input, tampered archive/member/generator, Boolean/float versions or counters, contradictory signal/exit, failed child disguised as success, output collision and source mutations. Guards remain active with `python -O`; set PYTHONOPTIMIZE=1 to include recorder test children. The packet includes many expected nonzero commands: treating all receipts as green would be incorrect.

To reconstruct a candidate, create an owned disposable checkout from the pinned Git base, extract its `candidates/<name>/` overlay from the archive, and delete only paths in that candidate's `observations/candidate-deltas.json` `deleted` list. Do not apply overlays to the primary/shared checkout. Use the exact archived lock with engine-strict `npm ci --include=dev --include=optional`, owned npm cache and `ONNXRUNTIME_NODE_INSTALL=skip` for optional GPU download. Actual CPU inference must still run. The official candidate's 107 migrated templates explain why this overlay is not adopted here. Its optional WASM graph is invalid in the captured installs.

Runtime reruns need Node matching frontend engines, the exact pinned model files from `observations/model-manifest.json`, installed declared dependencies and a Playwright Chromium installation. `compile-css.cjs FRONTEND NEW_CSS` uses actual PostCSS/config/content scanning and refuses an existing output. `css-render.cjs FRONTEND CSS_A CSS_B` executes computed styles in Chromium (baseline/baseline exits 0; baseline/official exits 1). `probe-current-callers.cjs FRONTEND` resolves dependencies through actual Tailwind, Next lint and argparse callers. `native-controls.mjs FRONTEND` uses `BATCH10_BUILDER_MODELS` and `NATIVE_VERIFY_CACHE_DIR` to run real ONNX CPU Identity inference and repeated pinned-model inference. `builder-init.mjs` uses those variables plus `BATCH10_BUILDER_ROOT` as a Node import preloader for the unchanged actual builder in a fresh owned fixture; it disables remote model access. `preview.cjs FRONTEND 13014 browser` verifies a free port, runs production Next, fetches CSS, runs the existing browser verifier and reads back cleanup. All public/internal API and synthetic build Supabase targets must be inert loopback. Do not supply synthetic Supabase values to unit tests.

`run.py NAME CWD COMMAND...` requires an existing external directory in `BATCH10_DEPENDENCIES_OUTPUT`. Names/outputs are exclusive. It records starting source/generator identities and retains nonzero exits; Linux nested commands' real environment is evidenced by their explicit `docker exec` command/identity logs, not the host wrapper's environment summary. Generated application outputs, CSS and model files need their own digest binding, supplied by this packet; the recorder alone is not a universal evidence system. Historical snapshots in `historical-generators/` are byte identities and need copying to the normal evidence path inside an owned Git fixture to execute.

Supersession:

| Earlier observation | Accepted scope / later observation |
| --- | --- |
| `candidate-official-upgrade` exit 127 | Setup error; `candidate-official-upgrade-corrected` executed official tool, later candidate inventories bind bytes |
| `baseline-caller-reproduction` | Metadata-resolution setup error; `baseline-callers-corrected` reproduces real primitives |
| `baseline-build` | Missing build fixture settings; `baseline-build-corrected` builds |
| `baseline-full-jest` | Child pass but unstable external-output placement; preserve failure verdict |
| `baseline-jest-clean-outputs`, `retry-budget-isolated`, `linux-jest` | Wrong auth fixture settings; `retry-budget-existing-fixture-env`, `mac-full-jest-parity`, `linux-jest-parity` use existing CI unit environment |
| `candidate-official-tree`, `candidate-official-fresh-tree`, `candidate-refreshed-tree` | Same real invalid optional graph; further fresh resolution also fails (`candidate-supported-tree`) |
| `recorder-red/` | Actual earlier generator attribution defect; repaired recorder's mutation controls pass |

The full native/build/browser results are historical baseline executions on the exact unchanged application tree. Separate reviewer logs and final published-fixture readback are in FINAL_VERIFICATION.md. No historical hosted run is asserted to test this branch.
