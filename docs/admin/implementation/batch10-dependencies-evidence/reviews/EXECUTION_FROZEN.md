# Final independent execution review

PASS for the selected local evidence-format boundaries on committed frozen source. Zero findings in the executed controls. This is retained-history integrity review only: no product security fix is selected, #494 remains OPEN, and full dependency acceptance remains unmet.

## Tested source identity

- Frozen HEAD: `0a01544aff9dc2f021dbb61b23e298d231d5427c`
- Frozen tree: `cd056986b30ddaaed2bc8b2d044f62a7d54f3382`
- Base: `f6c31e271297eece52f34102dc40a1e2ed7069a8`
- Base tree: `69ddfad6deb814dd08fdaee2db2d512d73e14c78`
- Base-to-frozen evidence-scope diff SHA256: `0be06714943ca840dd5d25c2d1ffc4c98945ecfbf23ab62c6e73a6d1810fa1c7`
- Pending diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty).

The worktree was clean before and after execution; all scope-file hashes and HEAD/tree match. All four scripts and all four archive/manifest bytes match their committed Git objects. The earlier initial report explicitly covered pending source on `041ad89`; this report covers the committed freeze.

## Executed boundaries

| Check | Result |
| --- | --- |
| Published verifier under `python3 -O` | Exit 0; 68 records / 482 files |
| Recorder suite under `python3 -O`, optimized children | Exit 0; 8/8 tests |
| Repaired bundle suite under `python3 -O` | Exit 0; 14/14 tests |
| Direct malformed-data CLI controls | 30/30 exit 1 with expected diagnostic |
| History v2 inventory, every member hash and path/entry safety | Pass; 790 members |
| Unsafe negative-name metadata / safe payload map | Pass; exactly 1 entry |

The direct controls exercise Boolean/float manifest versions and exit types; missing/empty command, cwd and source provenance; missing generator attribution; contradictory exit/signal and failed-child success; Jest verdicts, integer counters, suite/assertion inventories and contradictory counts; and audit integer counters and totals. Raw-record Boolean exit and float verification-exit controls keep valid integer manifest expectations, independently reaching `record exit type`. No inappropriate success occurred.

Python: Python 3.9.6. Every published/control call used explicit `-O` with `PYTHONOPTIMIZE=1`; `PYTHONDONTWRITEBYTECODE=1` prevented canonical bytecode writes. TMPDIR and disposable Git fixtures were owned under this external review directory. Canonical source, node_modules, model/shared caches and workflows were not edited.

Current verifier and repaired bundle tests match `repaired-generators/` members in `validation-history-v2.zip`. Their original `evidence-v1.zip` generator copies differ and remain historical; recorder/test-recorder bytes are unchanged. Every history archive member is a normalized relative regular-file path, with no duplicates, traversal, backslash, NUL or drive-colon path. The unsafe fixture name is JSON metadata in `negative-member-names.json`; its payload is at `negative-member-bytes/f201bab3be7c8ed3c97bc6df7ca6801c6252ba08bc6f893d6451c282be31b20a`, content SHA256 `629e3fc948fb5ca55eb9f2cc1cd815703841a4f6be23b038925fbe56bdc19c24`.

## Script and artifact hashes

| File | SHA256 |
| --- | --- |
| `verify_bundle.py` | `b80132793e28d27d967ced7ca54a9ca5950f2a35d84280ca2b79f3fc9fdb6bd4` |
| `test_bundle.py` | `35909dafa369573dbfbbde0e9f139f3124451859facf4033645b93caf9c7c660` |
| `test_recorder.py` | `36ddd86758663f1b99b2473b4fa8496ed6b18577771c63c6df81717860c40266` |
| `run.py` | `fcad1112b821edf38ddb0d87e838de33ebd6152ecc4a7818dbd3def011545557` |
| `evidence-v1.zip` | `6d6cb63a4c4e14acd08d7c5efdd688b98d3d5cd43a6300b1ad411c9c8787028b` |
| `evidence-v1.manifest.json` | `47ac26620c864613b2abd2c8718467da5aa14fcda74451587d9e91349f5e1fdf` |
| `validation-history-v2.zip` | `7716f3e5e2e16d42b7e8a099cf187026cae829b2407c19f246019f7795425073` |
| `validation-history-v2.manifest.json` | `0dc940eba919933d1a3f9f8a2f15efd857abbcf553b0633189057a91d5cb78db` |

## Evidence and limits

Exact calls, stdout/stderr and output/input/identity hashes are in `/Users/roger/.codex/visualizations/2026/10/10/01a123ab-8b43-7830-9262-8f05ab1b8a60/batch10-dependencies/reviews/final-execution/independent-frozen-20261010T032910486870Z/logs`; `FINAL_EXECUTION.json`, `frozen-source-identity.json` and `post-execution-source-identity.json` retain the complete source and control receipts. Independent drivers are retained and hashed by the adjacent report inventory. Every correctly rejected malformed fixture was removed only from its owned temporary directory after digest/receipt capture; none needed retention as an inappropriate success.

README and FINAL_VERIFICATION truthfully distinguish the interrupted earlier reviewer from completed reviews and current repairs from historical generator copies. The selected malformed controls check structural/semantic consistency. Modifying both a trusted manifest and its archive is outside original-capture authentication.

Unexecuted: product remediation/security acceptance or closure; historical application/build/Jest/native/model/CSS/browser reruns; installs, containers, network/provider actions, shared cache mutations and resource-exhaustion cases; packer regeneration or replay of every historical negative overlay; exhaustive optional-field schema validation. Historical provider/cleanup statements were read as retained documentation, not rerun or independently asserted here.

Actual delivery-HEAD readback after the final reviewer-report-only commit remains pending the root request; this report signs off the exact frozen source identity above.
