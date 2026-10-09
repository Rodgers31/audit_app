# Independent Spec review

Reviewed `e98a4be3998f7da4e2326a068802a879e393fb97` against pinned base
`f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`, current #554, frozen SPEC.md and
dispatch-contract-examples.json. Final uncommitted source recheck:

- `admin_etl_dispatch.py`: `3ba242157bd88e65e5d82647d777cc4d7457e48a`
- `admin_etl_dispatch_worker.py`: `a5fc5e8c0c99039f1099829872f263eca87ebae6`
- `admin_etl_dispatch_adapter.py`: `2ea040c52770dae16166b7868022c7961008604f`
- `routers/etl_admin.py`: `27b604e2c6b9eaba1364822d7aa6bafd172cda35`

1. **P1, remaining requirement, tracked #572:** SPEC.md:54 says
   “must prevent concurrent execution of the same protected domain” and
   “Keep conflicting work blocked until quiescence can be established”.
   The unchanged native CLI can start after the worker's RUNNING-observation check
   and bypass its domain block. The actual native-process race is retained as
   strict xfail/`--runxfail` red and disclosed in the handoff/change request.
   Retain default-off until exclusive ownership/quiescence or shared exclusion
   is accepted.

2. **P2, fixed during review:** SPEC.md:24/44 requires “real ISO UTC
   timestamps”. Independent schema replay emitted `-05:00` before repair.
   UtcDatetime now normalizes receipts/capability/leases; retained red/green and
   independent contract rerun pass. Inspected actual non-UTC PostgreSQL receipt.

3. **P1, fixed:** SPEC.md:28 requires
   storage responses to be “safe and truthful”. The reviewed capability path
   retained ready fields after commit failure. The exception branch now resets
   availability/generation/lease fields. Source and mounted PostgreSQL red/green
   checked.

4. **P2, fixed:** SPEC.md:32 says “Extra fields and coercion are rejected”.
   Direct semantic replay accepted numeric booleans. TriggerBody/type guards now
   reject malformed intent before storage; independently exercised four guards.

5. **P1, fixed:** SPEC.md:46 requires an “actual matching observation”.
   Completion accepted correlated but old/future, erroneous or negative-count
   observations. Final checks constrain native timestamps against the DB-clock
   claim, counts and completed errors; incoherence interrupts without releasing
   exclusion. Inspected eight executed PostgreSQL red/green cases.

No additional defects/scope creep found. Child-cleanup extraction preserves
behavior; atomic acceptance, actor replay, fencing and OAG-only mapping align.
Other mappings and coordinator UI/backend replay remain explicit.

Final router amendment independently checked against SPEC.md:32 (“Existing
valid legacy calls when disabled still return safe 503”). Strict dictionary
parsing restores valid legacy direct-call 503 compatibility while retaining
static 422 for malformed dictionaries; defaults/model bodies remain intact.
Existing direct controls: **4 passed**; independent malformed dictionary checks:
**3 rejected with static 422**. Inspected direct-compatibility red/green receipts.

Independent clean/inert `pytest backend/tests/test_batch7_etl_contract.py -q
-p no:cacheprovider`: **13 passed**. Initial SQLite-memory engine setup failed;
corrected to unused inert file URL. Inspected lost-ack replay PostgreSQL receipt;
no shared PG fixture reruns, live transport, primary edits or processes introduced.
