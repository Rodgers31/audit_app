# Financial guard traversal cost — #500

The second hosted backend run37171600493 at2b04f151 reached the unchanged main-module guard after an148.792-second interval since the previous test verdict. That is an output interval, not an isolated pytest duration. The structural detector repeatedly walked the full AST for every assignment when collecting same-name Load uses.

The repair builds the same whole-module Load-name index once. It preserves nested-scope same-name behavior, parent identity, breadth-first ordering, every structural exemption, suppression, detected site, context fingerprint and scanned path. No test, quarantine, assertion or workflow time budget is removed or relaxed.

## Executed comparison

On the same native macOS/Python3.13.9 runtime with coverage tracing, the full `backend/main.py` detector took **107.12s before** and **13.39s after**. Both returned the identical four raw findings. This measurement is local, not an Ubuntu timing guarantee.

Old-versus-new detector outputs matched across all **444** currently scanned source modules. Six additional controls compared structural-node identity sets on the exact same AST: nested shadowing, compare-only threshold, unused value, annotated threshold, arithmetic use and multi-target assignment.

- Unchanged main source SHA256: `365253eb0ecfdf2450b32a5ff1fd58708ba2cc4abbffec9977ebe3fa4cef9bb6`
- Unchanged reviewed inventory SHA256: `ef8580ffc028eb1f1c033737a5282f8fe9c41dfb52b8fb717f0ca4a2e7009a9c`
- New guard source SHA256: `963c15916f223ad7d33a37c62d1a2114a7344015a7fda5eb41b19554dfdf8f87`
- Whole-source parity receipt SHA256: `707547ac6428cb0176c33105d81be04f4845d6ca7c82c7190aa1cec02861aaeb`

The combined original financial guard, bounded backup and reviewed acquisition cohort passes **504 tests, zero skips**, and offline workflow boundaries pass27 tests. A first coordinator command named a nonexistent separate portability test file and collected no tests; its corrected command/result is retained separately, not reported as a passing run. The measured full hosted backend requirement remains pending at this commit.

Independent read-only review additionally passed16 exact-node-ID controls, including comprehension/lambda/nested shadowing, annotation/walrus loads, cross-function arithmetic, multi/tuple targets and repeated-name stress. Its receipt SHA256 is `341ccc12c7232e3aec84be87f5ec3e5866d4791087bfc2fe39bfecf8c8a797f5`. The index is built once; repeated assignments may still inspect their same-name Load list, so this change does not claim a universal linear complexity bound for the complete detector.
