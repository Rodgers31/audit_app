# Round 10 integration — publication and observability
Date: 1 October 2026. Base main: 8b8cb325348459e642e6c9e8c986d82aae765399.
Integrated worker commits: ebfac25b (supported regional observations) and fa126dbf (cold pipeline health).

## Verification
- The combined main.py function AST exactly matches the reviewed worker functions: regional helper/consumer changes from session1; pipeline-health changes from session5. Other existing functions remain identical to base. Combined canonical Python3.13 AST SHA256: 1ed3afc376726e1796f211999712f5d341aff775a474cdce631633f12a73c09a.
- Removed the five unsupported peer inventory entries, preserving the four main contextual values, all other contextual signatures and the remaining legacy inventory.
- Coordinator selected backend suite: 542 passed, zero skips, exit0, 220.47s. Included regional observations, actual no_data/populated sustainability HTTP, debt measure compatibility, worker lifetime/cancellation, economic status ownership, shared cache, read-only system routes, whole-tree financial literal inventory and publication guard boundaries.
- Frontend: 61 passed across DebtPageClaims, debtSustainability.types and debtSsrPrefetch, zero skips. TypeScript --noEmit --incremental false: exit0, no diagnostics.
- Worker independent adversarial acceptance: regional76 and health16 executed controls passed. Those are separate worker receipts, not additional coordinator reruns.
- Tests used owned loopback PostgreSQL16 on127.0.0.1:55461, unique UUID schema, an allowlisted child environment, disabled dotenv/seeder/warmup, empty Redis and no app lifespan. The test schema was dropped. Source HTTP controls were synthetic/mocked.

## Scope and limits
Unavailable peers remain explicitly absent; provider values carry measure/year/source and supported zeros remain zero. The production debt page still has no active peer strip. The successful peer helper retains its TTL; failing providers retry and can consume existing timeouts. No production performance/egress or source-value authentication claim is made.
Pipeline health owns its SQL session in a bounded worker and reports unavailable snapshots truthfully. No hard SQL timeout or production billing acceptance is included.
Actions stayed disabled; no paid reviews, live data writes, migrations, source-document correction or deployment were requested. Documents1823/2541 and accepted population79 were not accessed or repaired.
Worker discoveries are either fixed in these patches or separately assessed. The GDP poverty-result gap is recorded under existing issue137, with fresh original/current PostgreSQL controls; no duplicate ticket is created.
