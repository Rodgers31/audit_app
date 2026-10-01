# Round10 integration — economic and county observation identity

Base content: merged PR429 (03796f276d2b5a640fb2063eba59cda45c69dcff).
Worker changes: 7744f191 GDP/poverty;9840366 county identity;93b7ed9 release compatibility.

## Changes and acceptance
GDP/poverty reconciliation validates source/country/measure/currency/vintage identity independently of numeric equality. Historical contradictory claims refuse atomically rather than silently being relabelled. Shared documents and accepted population controls remain protected.
County instruments use explicit identity namespaces/references and dated source accounts. National Loan uniqueness remains unchanged; corrections are explicit, latest-stock/source conflicts withhold, zero/missing values remain distinct, and mixed legacy/new accounts do not claim reconciled coverage.
An executed release check found the original county readers broke on the predecessor schema. The integration repair first establishes both new tables' presence in one PostgreSQL catalog lookup per adapter batch. Both absent preserves existing sourced legacy accounts; partial schemas, query/permission/connection errors remain failures. No absence cache hides later schema adoption. Native SQLite inspection is covered separately.

## Coordinator execution
The accepted final controls cover669 unique selected test cases in two completed segments on unchanged integrated source:
- Core/default-fixture segment628 passed, zero skips. GDP observation/source identity, reconciliation, GDP/poverty publication compatibility, financial absence, county legacy/pending source rules, national writer, one Alembic head, nine release-compatibility controls and four changed-module literal gates.
- County segment41 passed, zero skips, exit0,12.42s. Actual PostgreSQL instrument identity, direct ORM/FK/check/unique guards, real county HTTP, correction/replay, migration existing/fresh adoption, locked refusal/rollback/recovery and national constraint preservation.
The core invocation also selected the41 county cases but their fixture refused a mismatched disposable port/database (40 setup errors and1 setup failure). They were rerun at the fixture's exact55415/round10_session4_415 destination in a newly owned container, all41 passed. This was harness repair; no production contract or test assertion was weakened.
An earlier coordinator attempt additionally mismatched GDP URL-query restrictions, ordinary SQLite fixture requirements and the release-test URL flag; it is retained as non-acceptance evidence. Corrected core execution preserves native SQLite fixtures and uses explicit allowlisted loopback PostgreSQL URLs. Final accepted cases have no skipped boundaries.
Workers also supplied their independently executed adversarial receipts. Coordinator release reviewer independently confirmed old/new actual Alembic HTTP, six PostgreSQL plus three SQLite author cases, ten hostile PostgreSQL and seven SQLite controls. Root read and integrated the reviewed three-file repair. No source-text-only runtime acceptance is substituted.

## Integration integrity and limits
Only the four reviewed county main.py functions differ from PR429; all other main functions match its reviewed content. National GDP source equals the reviewed worker source exactly. Combined main AST SHA256 e936625a3785c8ecbb53c84df2f6e7100f4f6ae35e085319ab0dc0f89295e000. The inventory retains all previous site dispositions and changes only this pin.
All DBs/schemas are newly owned synthetic loopback resources, dotenv/seeder/warmup disabled, Redis empty, no app lifespan or live seed. New migration adoption and real source ingestion remain separate: the county writer currently has only test callers. This merge supplies representation/reader capability; it cannot claim actual Kenyan instrument ingestion or production undercount correction.
No production correction or backfill, source retirement, protected-document mutation, secret/cache configuration, Actions run or paid review was requested. Historical GDP/poverty conflicts may remain after a refusing refresh. Existing issue137 records the independently confirmed poverty-fetch failure-result gap; source-independent pruning follows recorded canonical cleanup policy and is not filed as a new defect.
