# Consolidated Python dependency qualification

Combine the original Python proposals (#871, #872, #876, #877, #878, #879, #881 and #882) with captured native group #890 (`e69b993cdefa6b11459f239671015e658fa8304d`). All 25 native changed version occurrences are present. The separately proposed Gunicorn 26.2 and pandas 3.1 major upgrades were deliberately qualified here; future routine groups still exclude majors. The backend SQLAlchemy <2.1 cap remains intact. ETL and the dormant worker test profile use their separately tested SQLAlchemy 2.1.6 graphs.

## Compatibility fixes

ETL explicitly selects the existing psycopg2 DBAPI while preserving URL credentials/options. Remove an unused serving-database import that otherwise pulls undeclared web dependencies into the ETL-only environment and falls back to mock models. Declare HTTPX/Tenacity because the ETL source code imports them directly.

Export pandas 3 missing table cells as absence while retaining literal text, financial values and the original frame. Reject non-scalar cells before text conversion can manufacture a year. Actual pre-change/final pandas comparisons preserve supported output, source hashes, nulls, zeros and Decimal values; source validation is not loosened.

Test-only repairs use Starlette's actual state mapping with pytest 9.2, exercise both serving-session factories in the dead-database witness with explicit fixture authorization, and compute a lease timestamp before assigning its paired token/expiry under SQLAlchemy 2.1 autoflush. Original refusal/status/financial assertions and database constraints remain in place. Genuine pre-fix failures and post-fix successes are retained.

Batch 66 preflight admits driver 2.9.13 consistently at connection and report boundaries. Keep exactly two independently verified CPython 3.12/3.13 manylinux x86_64 wheel hashes. Reject the bot's 67-hash expansion, foreign platforms and source distributions. Existing source, receipt, credential, byte/query/time limits and workflow controls remain intact.

## Final resolved graphs and execution

Fresh backend runtime/dev and ETL runtime/test graphs contain 87/120/53/65 installed distributions. The backend runtime inventory equals the initial qualified graph; the extra weekly development updates remove ten old isort-chain packages and add librt. The ETL runtime changes only the captured Boto3 patch against that initial graph. All complete inventories pass pip-check and unfiltered pip-audit/OSV with zero matches or skipped distributions. The fresh worker profile has exactly its 93 declared pins, no transitive drift and zero findings in both full scans. Resolved versions and receipt hashes are bound in PYTHON_VALIDATION.json; this qualification does not promise future floating resolutions.

Final normal and true optimized Python cohorts pass without failure/error/skip: backend 1,560, health/auth 34, actual PostgreSQL 76, ETL 111, targeted ETL coverage 60, tool/SDK controls and the final account fixture 45. The worker graph independently passes 177 framework/API/account cases, 228 preflight cases, 34 boundary cases plus 65 unittest subtests, and 76 actual PostgreSQL cases per mode. Counts overlap and are not an all-repository total. The preflight child still uses its authenticated normal interpreter even with an optimized parent.

Real pytest-cov produces measured line/branch reports for the backend cohort and 60 ETL cases. Two complete-ETL coverage runs hit the unchanged three-second PDF child deadline; controlled old/new plugin runs both reproduce this instrumentation overhead, while final uninstrumented ETL passes. No deadline, parser guard or assertion was weakened. These controls do not establish complete repository coverage.

Initial qualification also exercises real Java/Tabula/Camelot/PDF inputs, financial/source/replay/retention behavior in owned PostgreSQL, source-bound pandas baseline agreement and the actual Gunicorn launcher with clean SIGTERM/child teardown. New developer tools and Boto3 S3 helpers are executed with valid/invalid input and strict offline SDK stubs. No real object-store/provider action occurs. Original receipts remain historical; final addon receipts are separately bound.

Two new executable independent reviews clear the final core addon and two clear the worker addon. Their exact source/results and receipt hashes are bound in PYTHON_VALIDATION.json. A separately reviewed documentation-only change marks old restoration IDs as historical; all 16 other source files and all 25 native guards remain byte-identical to tested files. Original evidence is preserved.

## Remaining launch gates

Native worker-host qualification and current accepted production package parity remain UNMET. The archived production comparison has four shared-version differences (AnyIO, FastAPI, Starlette and SQLAlchemy); the 93-pin fixture is not a production worker release. Native x86 runtime, exact accepted Python/base parity, unchanged confinement/cgroup/capacity/reserve workload, and shutdown/restore proofs require their existing before-use process. Local Linux ARM64 results and downloaded x86 wheel identities do not substitute for those gates. No hold is waived.

## Release boundary and rollback

Merge-only maintenance. Publishing, uploads, workers and financial generation remain off. No production deployment, ingestion-pin update, migration, new paid service/check/resource or branch-rule change. Owned PostgreSQL fixtures must be positively removed after reviewers finish. The authorized Vercel Git disconnection preserves the current site and prevents Git-triggered Vercel builds.

Revert the complete replacement merge to restore the matching requirements, ETL semantics, preflight driver policy and test fixtures together. The coordinator retains a private inverse-tree proof against the actual parent. Superseded proposals are retired only after accepted merge and current-intent reconciliation.
