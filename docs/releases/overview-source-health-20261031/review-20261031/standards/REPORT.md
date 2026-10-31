# PR863 — optimized assertion evidence review

**Finding refuted for the retained runners.** Five owned offline runs used the exact retained `python -O -m pytest` shapes and cached image `sha256:571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`. Every process recorded Python3.12.15, `sys.flags.optimize == 1`, `__debug__ == False`, and pytest's `AssertionRewritingHook`. Historical packets and product code were not edited.

| Executed control | Actual result |
| --- | --- |
| `run_review.py` optimized shape, direct false test assert | 1 passed runtime check; 1 expected assertion failure; child exit1 |
| `run_final_review.py` optimized shape, same canary | 1 passed; 1 expected failure; exit1 |
| `run_canonical_affected.py` optimized shape, same canary | 1 passed; 1 expected failure; exit1 |
| Unmodified original31-case module + runtime check | 32 passed; exit0 |
| Original module with only expected cooldown26→27 + runtime check | 31 passed; 1 expected failure; exit1 |

The counterfactual fails specifically inside the original `denied` helper's header assertion, showing actual `Retry-After:26` versus deliberately wrong27. `wrong27-runtime.json` records the helper's rewritten bytecode names (`@pytest_ar`, `AssertionError`) and its actual loader. The false assertion canaries also fail with the expected assertion message, rather than an unrelated import/setup error. All70 recorded outcomes are explained:66 passes and4 intended failures, zero unexpected failures or skips.

The review's general caution has a valid narrower scope: Python `-O` removes ordinary, unrewritten `assert` statements. Pytest's warning explicitly concerns assertions **not in test modules or plugins**. With the retained default assertion mode, collected test modules are rewritten into explicit checks, including their helper functions. These executions prove that boundary; they do not claim assertions in arbitrary imported application modules survive optimization. The application remains optimized, as intended. No `--assert=plain`, custom assertion plugin or optimization bypass was introduced.

Only container names, new output mounts, controlled test selections and an inert per-run metadata filename label were substituted to preserve historical receipts. For the first runner's retained normal command, `-O` was inserted exactly where its existing `--optimized` branch inserts it. Source projections stayed read-only; the original31 module was copied byte-for-byte for the baseline, and the mutant changed exactly one expected-value literal. Exact argv and child exits are in the five command/execution receipts; `MUTATION.json` pins the original/copy/mutant.

Each run used network-none Docker, one CPU/1GiB/256PIDs, inert SQLite and the retained explicit OFF flags. No provider, production, hosted, paid, PostgreSQL or shared-container action occurred. All five containers auto-removed. All33 artifacts in the prior sealed packet still match their old hashes; selected inputs also match before/after.

`CASE-LEDGER.json`, `RECEIPT.json`, `INPUTS-{BEFORE,AFTER}.json` and `ARTIFACTS.json` seal this bounded review. `python3 run_assertion_controls.py` replays it with the separately retained historical source projections/command receipts and cached image; its success requires all deliberate child failures to occur. This is a check of optimized-test validity, not a new broad application or production acceptance claim.
