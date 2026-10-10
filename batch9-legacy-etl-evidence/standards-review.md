# Independent Standards review

Reviewed working ETL changes against `9e97ca3f1ca43f103a8655447a86d889456a218a`. Sources: `CONTEXT.md`, historical `TESTING_GATES.md`, Batch 8 exclusion contract/handoff, and current persistence, no-silent-fallback, and boundary-shape skills. No applicable AGENTS/CLAUDE or separate coding standards file was found. Tooling-enforced style was excluded.

## Documented invariant findings

- **P2 — manual session lifetime:** `etl/writer_ownership.py:194` closes the creating context when each session closes. Closing two valid sessions in creation order makes the first context finalize while the second remains alive; the last close never retries finalization. Batch 8 contract requires normal terminal acknowledgement to release native ownership; Batch 9 also requires normal success to permit the next run. Actual `DatabaseLoader.get_db_session()` calls on temporary SQLite committed two inert effects, then closed both sessions normally: first close raised, 13 claims remained, and the next run was refused. `standards-session-probe.py/json` records exact command, Python 3.13.9/SQLAlchemy 2.0.46 and hashes. Track the shared lifetime independently of session close order.

- **Schema-validation gap — conditional on incomplete storage:** `etl/writer_ownership.py:47` checks tables/columns but accepts storage missing `uq_seeding_active_domain`. Batch 8 contract lines 12–14 require that index as durable authority. An actual native retained claim, followed by removing only this index in temporary SQLite, still passed readiness; the actual legacy manual session committed another effect. `standards-readiness-probe.py/json` preserves the executed control. This does **not** establish schema drift in the author's migrated PostgreSQL; either verify this essential constraint before entry or retain a concrete schema-validation operational gate. The shared native seam also assumes the same schema.

## Heuristic smells

- Possible **Duplicated Code**: `writer_scope` exception branches and `OwnedSession.__exit__/close` repeat failure/uncertainty classification. A small state-owned helper could keep that policy consistent. This is discretionary, not a documented violation.

No PostgreSQL services were accessed or modified. Minimum SQLAlchemy 2.0.23/Python 3.12 and process acceptance remain author verification gates; this review does not claim those executions.
