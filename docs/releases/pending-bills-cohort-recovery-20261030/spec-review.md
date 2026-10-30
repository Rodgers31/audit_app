# Scoped acceptance: frozen recovery candidate3

No remaining finding in this review. Final manifest mapping `6a1bcb7aac9b1fd4b2c44843aa8d40852a9d9bea43b25a4446c7585e86faf8fc`: all 5,799 files and exact file set verified before and after execution.

**Final narrow run:29 passed, 0 failed/errors/skips,15.11s.** It executes three independent issuer attacks, permanent issuer/shape controls, the original three cross-ingestion desired regressions, the Nandi/complete-cohort and known-change/replay positives, cross-record/job witness replay refusals, qualification accounting, and the corrected receipt-lock probe.

The three issuer attacks are observed RED on frozen2 and GREEN on3: an unissued instance overriding intact(), an unissued subclass supplying that verdict, and a genuine issued witness with changed value plus an overriding verdict. Current checks reject all before any cursor transaction commits. Genuine qualification still runs; no approval/publication bypass is claimed for the older issuer weakness.

Original recovery behavior remains0 new drafts for unchanged refresh,0 new drafts with prior Nairobi backfill, and 1 draft for a genuine known-row change. A fully completed source admits genuinely new Nandi data once, then replay is unchanged. The actual prior late-withdrawal/value/cursor/receipt/entity races pass on2 and carry through byte-identical source/SQL checks; the exact bound automatic race controls also pass independently on2.

## Exact carry and executed boundaries

Frozen2→3 changes exactly five files: two product files, two tests and one release note. The product diff only replaces both virtual verdict calls with the issuer-owned exact-class/weak-registry predicate. All other files match byte-for-byte; input_fingerprints, lock_qualified_inputs and _qualified_witness AST bodies are identical. Full diff and hashes are in manifest-delta.json/delta-2-to-3.diff. This carries previously executed source, qualification, timing and SQL checks, rather than claiming they all ran again on3.

Executed dependency controls on2 reject changed country/source metadata, retained-origin metadata, fiscal period, cursor fingerprint, failed/newer jobs and genuine witnesses replayed for another record/job. Current national evidence qualifies despite a deliberately invalid unrelated historical receipt reference, exercising the final national scope refinement. Pre/post-completion commit faults report failure with truthful confirmed row counts and replay silently. Source REPORT/BUDGET selection remains covered by its positive/negative cases. No second full 46-qualification loop was observed: the actual current29case run measures 46 full qualifications and 47 report reads (46 row reads plus one final shared-report read).

Two real concurrency checks supplement count assertions. The entity-context writer on2 and the exact receipt writer on3 wait in PostgreSQL with wait_event_type Lock before and throughout real financial qualification. Each can finish only after the controlled consumer rollback. The final receipt probe's exact ID/wait/result are retained in lock-receipt*.json.

## Retained failures and limits

Frozen2 preliminary runs contain reviewer fixture failures, fully retained: an unordered verification read, assumptions that refusal counters stop at the first record, use of a telemetry helper after deliberately failing its job, matching an error message instead of its code, and a JSON literal misparsed as a SQLAlchemy bind. These were corrected in separate evidence files; no product expectation was weakened. The receipt SQL initially never reached PostgreSQL; it was not evidence of a lock failure. Frozen2's three real issuer REDs are separately preserved. Exact per-execution counts are in both case ledgers; they are not presented as one deduplicated repository suite.

All project execution used cached capped OFFLINE Docker, read-only frozen bytes and one owned network-none PG17/tmpfs fixture with unchanged full Alembic a756/currentb83 guards. The same owned fixture was reused sequentially for 2 and 3. No parentPG, worker-role grants, workers, providers, hosted runs, product edits or production actions were used. This report does not credit root's broader/optimized/latency runs or certify production recovery; those are separate evidence.

The sequentially reused owned PG container and private mode600 credentials have been removed; absence verified before the final receipt.
