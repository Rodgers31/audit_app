# Replay the Spec review

Use this evidence directory or an isolated copy. Set SPEC_NODE to the official Node 24.22.1 executable and SPEC_SOURCE_ROOT to the candidate checkout. The Python scripts default to the exact original review paths. Use an owned TMPDIR for routine replay. The final helper also supports macOS ancestor aliases: the retained 63-case final replay deliberately omits TMPDIR to cover the earlier /tmp-to-/private/tmp refusal. No tool here starts the application, a worker or a supervisor.

The final comparison runs:

```sh
python3 run-final-direct.py
python3 run-shadow-controls.py
python3 run-deep-source-controls.py
```

run-final-direct.py compares complete current configs/diagnostics with the immutable pre-migration baseline, compares the 347-rule catalog, and executes actual flat and native public APIs. It never overwrites the baseline. Original eslintrc source is kept solely as an owned compatibility fixture; its dependencies are linked read-only from the candidate except for the genuine historical matcher.

The historical-graph and fixtures package manifests/locks are isolated research prerequisites. If reproducing in a new directory, install them there using the corresponding npm with scripts disabled. They are not application dependencies. The historical tree deliberately contains old vulnerable package versions; its audit output must not be confused with the final application's retained five-low/zero-production report.

probe-installer-hostile.cjs accepts the absolute frontend path and uses one owned fixture under runs. It reconstructs reviewed original bytes, tries 49 invalid filesystem/metadata states and six malformed direct modes, and verifies no file bytes/modes/links change on rejection. It also checks exact cold/repeat and omission results. Launch with Node --max-old-space-size=512 and a bounded wall timeout; the actual receipt records the command and outcome.

run-shadow-controls.py uses a fresh child/fixture for each of eight parent roots. run-deep-source-controls.py uses five real source requester locations. Each source child first proves a valid check, then proves genuine historical code is selected, then requires an identity-specific refusal. This avoids accepting an unrelated loader error as a successful security rejection.

The permanent candidate selection is Node --test scripts/lint-matcher-migration.test.cjs scripts/tooling-repair-install.test.cjs from frontend, with the official Node directory on PATH and TMPDIR set to an owned canonical directory. final-permanent.receipt.json retains stdout/stderr, actual exit, environment and duration.

capture-final-binding.cjs accepts the checkout root. It verifies all seven complete file/link inventories, thirteen resolution contexts, modern lock graph and unchanged production inventory, then records staged source hashes. The supplied binding identifies the reviewed bytes; it is not a substitute for rerunning behavior when those bytes change.

Setup/transition/noncanonical-root diagnostics are retained in the original evidence directory where relevant. They are not accepted passing controls. The curated report retains the two genuine source-context RED results, final GREEN results and the explicitly described noncanonical-root limitation separately.

The curated package excludes all installed package trees. Research package manifests/locks use `.json.txt` names; restore `.json` only inside an isolated replay copy before fixture installation. For the native public-API baseline, copy the currently pinned @eslint/eslintrc 2.1.4 package into owned original-packages/eslintrc; its unchanged CJS bundle supplies the old-library comparison. The archived prototype ESM RED predates the repair and is retained as a receipt, not a claim that the repaired tree should fail.
