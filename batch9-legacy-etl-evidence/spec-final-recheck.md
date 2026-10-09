# Final independent Spec recheck — #581

**No blocking spec finding remains in the frozen candidate.** This final recheck supersedes the candidate scope of `spec-recheck.md`; earlier reports and receipts remain preserved.

Reviewed `etl/writer_ownership.py:142-161`: failure to persist the optional refusal observation logs a bounded diagnostic, closes continuity connections, and rethrows the original `DomainOwnershipError`. It neither invokes loader work nor weakens the retained conflicting claim. This preserves the assignment's “visible refusal/failure” when document/full-pipeline generic error handling would otherwise swallow a storage exception. No new financial, source-scope, dispatch-policy or shared-API change identified in this delta.

Independently replayed immutable `refusal_storage_control.py` through `run_receipt.py` on owned temporary SQLite: **PASSED**, exit 0, `refusal_exception=DomainOwnershipError`, `effects=0; retained=1`. Receipt: `refusal-storage-final-spec-independent.json`. Its wrapper hash and embedded control hash were read back and checked against their files.

Also independently replayed all three original immutable controls using new receipt names: `spec-refusal-final-independent-green.json`, `spec-session-final-independent-green.json`, `spec-scheduler-final-independent-green.json`. **3 PASSED, 0 failed, 0 skips.** Original red and final green generator hashes match. Final source hashes were checked against live product files. Refusal propagates with monitor success false; external Connection binding refuses; documented standalone scheduler imports.

Reviewed final SHA-256 identities:

| Product source | SHA-256 |
| --- | --- |
| `etl/writer_ownership.py` | `27c7b20eac3229118685cb278a9473ab1d843fad1c0350cc8fcb7879993b94e8` |
| `etl/database_loader.py` | `1528ab8ea1507de54b58d3ac0aea79c0b093a20e301e79fadf6848c2a098a043` |
| `etl/kenya_pipeline.py` | `36e0f2fd9db7d080180745ae976d846933e0f54e4c1c69228599a4211eb77401` |
| `etl/scheduler.py` | `3f6aabcb33aed050091ea6e1de4a9dee3e7135c55198c8940c8e6a0d87975dd7` |

Runtime: CPython 3.13.9 / SQLAlchemy 2.0.46, clean environment, dotenv/bytecode disabled, read-only primary interpreter. No PostgreSQL, provider/storage/network, service, product or test mutation by this reviewer. These controls cover the reviewed local behaviors; author PostgreSQL/minimum-runtime evidence, hosted CI, production quiescence/pooler capacity, #583 reconciliation and held PR #584 remain separate acceptance gates.
