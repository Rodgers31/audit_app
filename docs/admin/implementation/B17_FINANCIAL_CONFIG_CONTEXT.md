# B17 config financial-context review

Only the `backend/seeding/config.py` entry in the reviewed inventory changes. Base `78c305abe3cfb5b3d3f0ed800275f2f7e7bfb303`; new context AST SHA256 `0cc61922295009675f8ff3223ff6f1172dbf737d675b40da0f201d06a9ba810d`.

The only product delta is `opendata_ingestion_enabled: bool = False` and its validator, accepting bool or literal true/false. Removing exactly those two nodes yields the accepted base AST. Independent Standards executable `review_config_context.py` and `config-context-review.json` retain that comparison. The new setting has no numeric literal; its three consumers are boolean admission gates in builtin loading, worker readiness and the native handler. It never supplies a published amount.

The existing single raw scanner site, `audits_county_start_budget_seconds=240`, remains a scheduling deadline, with the same caller/metadata/fallback context and disposition. No new use of that value is introduced. Site signature, reason, disposition and tracking remain unchanged; only this entry’s AST digest and review pointers are refreshed. Every other inventory entry is preserved.

Validation uses the real scanner plus the mutation controls in `test_batch9_financial_review_context.py`; final exact-source receipts and independent re-read are in the external B17 workbook packet. This is a source-context review, not public financial-data qualification.
