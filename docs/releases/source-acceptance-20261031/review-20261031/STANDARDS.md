# PR861/PR862 — independent Standards tooling review

Scoped pass: **22 portable replay CLI tests plus 13 merge-guard tests per mode**, normal and true Python `-O`; 35/35 passed per mode, zero skips. These execute the actual pinned stdlib helpers with inert Docker/GitHub subprocess ports. No containers, PostgreSQL services, hosted checks, provider calls, production actions or credentials were created. Backend application tests were not rerun or credited here.

The original replay helpers produced five observed failures / one failed-child control pass: author-specific source root, ignored root overrides, missing committed companion inputs, unknown mode silently treated as normal, and receipt overwrite. The repaired helpers use script-ancestor or explicit reviewed source roots, committed `.py.bytes`/`selection.txt`, safe names and modes, fresh receipt output and refusal before child execution for invalid/missing roots or existing output. Tests include spaces in paths, explicit overrides, detached-script refusal despite a valid cwd, new output creation, missing/empty companion inputs, documented extracted `.py` fallback, failed child exit/receipt preservation and repeated unique output names.

Two findings in the first repair were independently executed and reproduced by root: blank source override selected cwd, and a dangling receipt symlink wrote its target outside the evidence directory. Both now refuse before the intercepted child; blank evidence roots are refused too. Original RED logs and the direct symlink creation receipt remain in this packet. The retained original-helper archive exactly matches both pre-fix helper hashes. Historical command receipts and sealed peer packets remain unchanged.

The two-PR guard is pinned to PR861/862 and the exact expected head/classified review material. Both normal paths, protected-branch refusal, unapproved truthy override values, unexpected failure, incomplete/pending/unresolved census, reported checks, late head/review changes and failed override were executed. Default protected-branch rejection returns **`maintainer_override_required`**, with no admin attempt; this is a stop verdict, not evidence of a merge. Exact boolean `True` is exercised only through inert test ports, requiring another fresh validated census. No new owner admin authorization has been supplied or inferred.

Two malformed-census guards initially failed: `isResolved="false"` was treated as resolved and `totalCount=True` certified one review. Root reproduced both; strict resolved/draft/pagination booleans and strict nonnegative integer counts now refuse them. This is input-shape hardening, not a demonstrated bypass from a normal typed GitHub response.

Final pins:

- Root replay helper: `f261d9a5642984781e9f223f5baf5dca61aba1dcc6dfaefecf4341de9a38b3bc`
- Selection companion: `2d94e8e1fb687d03c0499cb2b1e8b951f3ade0fa08b3c79a09362a67171a3d6a`
- Selection: `15ef3ae64ea94a47e4dca439c7c91154d815ffa4fc145507066fd24c1f598196`
- Merge guard: `d27f1da42207237a68c066498016ccc900b0f2f1ed930b159c6ac21e7dc0401e`

Before/after pins match. Only the root-owned release documentation/helpers and external guard changed; reviewer made no project edits. No backend diff or historical command/peer-packet change exists. All owned temporary CLI fixture directories were removed; user/shared containers were never accessed.

Replay the inert controls with `PORTABLE_CANDIDATE=<this packet>/candidate-2 python3 [-O] test_portable_replay.py`, then `python3 [-O] test_merge_guard_independent.py` and `python3 [-O] test_merge_guard_shapes.py`. The latter modules load the frozen `candidate-merge-guard.py`. Tests use the host's Python3.9 stdlib only and intercept all execution ports. They do not prove live Docker availability, real PostgreSQL fixture readiness, current GitHub census or a successful merge. Root must fetch a fresh real census immediately before each authorized normal merge; admin remains blocked without separate explicit owner permission.

`CASE-LEDGER.json` cites each final test method/log. `RECEIPT.json` records scope, effects and authorization limits. `ARTIFACTS.json` pins the sanitized packet.
