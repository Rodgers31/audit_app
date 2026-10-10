# Local proposals for the coordinator

These are proposed shared-skill improvements only. No shared skill was modified.

- `verify-boundary-shapes` / `dependency-auditor`: bind complete installed package inventories and declared entrypoints, including minified distribution and maps; checking only patch targets misses export redirection and extra/missing files.
- `no-silent-fallbacks`: use `lstat` before omission handling; a dangling package/parent link is not a genuinely absent omit-dev dependency.
- `regression-fixture-on-fix`: reproduce direct AST/append/flatten recursion separately from parser depth; snapshot the precision and conversion actually used after callbacks rather than validating mutable values once.
- `receipt-provenance` / `tool-verdict-discipline`: require explicit error/expectation fields, nonempty complete environment policy, exact owned home/config/PATH relationships, original producer bytes, actual raw child exit and nonempty test inventory. Zero exit alone can retain graph diagnostics; collection alone is not execution.
- `pair-programming-discipline`: every mutation command must supply an explicit absolute owned workdir. Preserve a real isolation mistake and exact recovery evidence; never replace it with a read-only claim.
- `verify-test-prod-parity`: copy every actual read-only fixture prerequisite and install real Git/browser/native dependencies in the owned platform fixture. Do not turn setup errors into product failures or fake unit-test provider configuration to make a cohort green.
- `deps-upgrade`: invoke npm through the exact selected Node and actual npm CLI, use separate empty user/global configs, keep CPU-only optional-runtime controls explicit, and report optional/extraneous graph output even when npm exits0.
- `claims-need-receipts`: preserve failing generators/results unchanged; later corrections receive new identities. A committed handoff names its measured predecessor, while final remote HEAD/tree belongs in an append-only external binder. Keep historical integrity, scoped local behavior and coordinator issue acceptance distinct.
