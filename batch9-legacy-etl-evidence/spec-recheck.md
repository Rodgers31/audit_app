# Independent Spec recheck — #581

Rechecked the working candidate against pinned base `9e97ca3f1ca43f103a8655447a86d889456a218a`. The initial `spec-review.md` and red receipts remain unchanged. **All three original blockers are resolved in the reviewed candidate; no new blocking spec finding.**

Independently reran each original immutable generator on CPython 3.13.9 / SQLAlchemy 2.0.46. Commands used clean environment, disabled dotenv/bytecode, and the read-only primary interpreter. New `spec-*-independent-green.json` receipts record generator/source hashes, head and command; a separate read-back comparison verified each generator matches its red receipt and each green source hash matches the reviewed files.

1. **Refusal visible:** actual download → full pipeline → monitor now propagates the real `DomainOwnershipError`; result is `refusal_propagated=true`, `monitor_success=false`, exit 0 for the control. `etl/kenya_pipeline.py:2233`, `:2308` also avoids the KNBS generic fallback (`:2148`). Receipt: `spec-refusal-independent-green.json`.

2. **External transaction lifetime refused:** `loader.SessionLocal(bind=conn)` now raises `DomainOwnershipError` before claiming/writing. `engine_for` requires an Engine (`etl/writer_ownership.py:41`); raw Connection escape and mapper/table rebinding refuse (`:250`, `:255`, `:258`), and resolved binds cannot switch engines (`:213`). Receipt: `spec-session-independent-green.json`, owned temporary SQLite. Manual sessions now finalize at the last close (`:243`), preserving claims while other group sessions exist. PostgreSQL transaction/connection-death acceptance belongs to the author's process controls and was not rerun here.

3. **Standalone scheduler imports:** documented top-level `scheduler` imports with an inert optional schedule dependency; package/standalone branches exist for runner and loader (`etl/scheduler.py:27`, `:78`). Receipt: `spec-scheduler-independent-green.json`, import-only. Author startup/process verification remains separate.

The unavailable loader now visibly refuses writes and startup checks; it cannot report a fabricated document id (`etl/kenya_pipeline.py:170`). Readiness checks require the active-domain unique partial index before each acquisition (`etl/writer_ownership.py:54`, `:88`). The thirteen-domain lexical acquisition and shared acknowledgement API preserve the chosen conservative shared-reference design. No financial transformation/publication change identified in the product diff.

This recheck does not certify minimum-runtime PostgreSQL, hosted CI, production quiescence/pooler capacity, #583 reconciliation, or held dependency PR #584. Those remain separate acceptance gates. No PostgreSQL/service or product/test mutation was performed by this reviewer.
