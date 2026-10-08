# Shared test schema setup cost

Base: `71d44f45e0ecd0ace05b13f37d2518df5e37c1a9`. Refs #500.

The backend shared `_setup_tables` fixture was autouse: every case created and
then dropped the full shared SQLite schema, including pure source inspections,
optional PostgreSQL cases that skipped, and GDP cases with their own database.
The hosted backend-only run stopped at the existing 15-minute budget; recorded
verdict intervals motivated this profile but are not pytest phase durations.

Cache clearing remains autouse, before every case. Shared schema creation/drop
now belongs to the explicit `_setup_tables` dependency of `db_session`. `client`
and all seed helpers transitively consume it. Each shared consumer still creates
and drops a fresh schema; no shared transaction or persistent-schema shortcut
was introduced. The JSONB compile shim, network guard and rate-limit controls are
unchanged. Repository searches found no existing import of the shared engine or
TestingSessionLocal outside the independent integration fixture; direct binds in
consumer tests come from `db_session`. The new lifecycle test inspects the already
loaded parent conftest plugin without importing a second engine.

## Covered before/after profile

Command, run separately on each state in backend with the same Python 3.13 venv:

```text
python -m cProfile -o PROFILE -m pytest tests/test_gdp_provenance_identity.py tests/test_apis_no_invented_county_rankings.py --cov=. --cov-report= --durations=5 -q
```

| Measure | Before | After |
| --- | ---: | ---: |
| Passed / existing optional-PG skips | 591 / 143 | 591 / 143 |
| Pytest elapsed seconds | 33.89 | 11.48 |
| Metadata create_all calls | 877 | 143 |
| Metadata drop_all calls | 734 | 0 |
| main.clear_all_caches calls | 734 | 734 |

The 143 GDP-owned schema creations remain. Its real router/HTTP identity, source,
locator, zero, invalid amount and conflicting evidence cases are unchanged.
This local covered+cProfile comparison shows a 66.1% elapsed reduction for the
selected cohort; it does not predict the entire hosted suite's duration or claim
PostgreSQL execution. Existing optional PostgreSQL skips remain unchanged.

## Regression and consumer gates

- Baseline lifecycle regression: **1 failed, 2 passed**; the no-consumer case
  observed the unnecessary full shared schema.
- Fixed lifecycle/cache cases: **7 passed**. Two successive consumers commit rows
  and alter a registered table; each starts with empty rows and original columns.
  A subsequent nonconsumer proves schema teardown completed.
- Deliberately disabled teardown: the new teardown control fails. The real
  teardown was restored and all seven cases passed again.
- Covered shared-handler cohort: **251 passed** across lifecycle, router cache
  isolation, county identity HTTP, audit listing observations and figure
  qualification handlers. A final standalone lifecycle/cache run adds the new
  teardown case after that cohort.
- Critical Python lint and diff check passed. No original case, assertion, data
  pin, marker, timeout or production code changed.

Receipts in the shared verification artifact directory:
`REMAINING_SCHEMA_PROFILE_{BEFORE,AFTER}.log`,
`REMAINING_SCHEMA_PROFILE_COMPARISON.json`,
`REMAINING_SCHEMA_LIFECYCLE_{RED,GREEN}.log`,
`REMAINING_SCHEMA_TEARDOWN_NEGATIVE.log`, and
`REMAINING_SCHEMA_SHARED_COHORT_GREEN.log`.

Root owns hosted acceptance. No provider writes, Actions changes or CI timeout
changes were performed.
