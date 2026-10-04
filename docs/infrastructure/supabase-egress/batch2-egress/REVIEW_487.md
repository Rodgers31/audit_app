# PR #487 review receipts

Review baseline: `8c590ffc1172d6c40401547e269d43f7d5fd9df5`, 2026-10-03.

Comment `4175471207` identifies a valid local-only connection invariant failure. Actual psycopg2 dialect arguments showed that caller `host`, `hostaddr`, `service`, `port`, and `dbname` query options could override validated authority fields. No remote connection was attempted. The fix rejects every caller query option before engine creation and pins the effective host and hostaddr to the same literal loopback address. This also protects the benchmark's worker and import-only engines. Checking parsed options alone is insufficient: SQLAlchemy discards blank values, so raw query syntax is rejected before parsing.

The behavioral regressions ran before the fix: 14 failed / 9 passed initially; an intermediate parsed-options guard still failed four blank-query cases. The final guard passes override, blank-query, effective driver argument, inherited libpq environment, and CLI refusal cases. An encoded password question mark remains valid. Refusal logs contain only a static outcome and exception class.

Comment `4175471226` correctly identifies unclear fixture attribution, but changing the smaller numbers to match the table would misstate the original receipt. An independent rerun loaded the actual `9000c25` writer implementations into an isolated local schema and reproduced:

| Baseline source fixture | Queries / returned rows | Selected-value byte estimate |
|---|---:|---:|
| National budget, 2 records / 2 URLs | 2 / 2 | 131,402 |
| National budget, 20 records / 2 URLs | 20 / 20 | 1,314,200 |
| Revenue, 2 records / 2 URLs | 2 / 2 | 131,404 |
| Revenue, 20 records / 2 URLs | 20 / 20 | 1,314,274 |

The README now distinguishes both fixture sizes explicitly. Baseline statistics again returned 80 rows / 5,253,971 estimated selected-value bytes. The guarded standalone benchmark still returns 10 rows / 356 bytes for statistics, 2 rows / 2 bytes for budget sources, and 2 rows / 46 bytes for revenue sources. Worker measurements remain unchanged, including the measured two-connection maximum with zero overflow.

All measurements use the assigned disposable loopback database. These estimates exclude wire/protocol/pooler overhead and cannot close issue #481's seven-day provider or hosting acceptance gates. No production database, provider, deployment, schedule, or credential configuration was changed.

Final validation used the existing Python 3.13 environment with no dependency installation:

```sh
EGRESS_TEST_DATABASE_URL="$LOCAL_FIXTURE_DSN" PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=backend "$PYTHON" -m pytest \
  --confcutdir=backend/tests/egress backend/tests/egress -q --tb=line
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" \
  docs/infrastructure/supabase-egress/batch2-egress/benchmark.py \
  --database-url "$LOCAL_FIXTURE_DSN"
```

Result: **54 passed, 2 existing SQLAlchemy deprecation warnings, 5.58 seconds**; benchmark exited zero. `$LOCAL_FIXTURE_DSN` supplies the explicit assigned port/database documented in the README. Guard-only tests inspect effective dialect arguments and intercept unsafe engine creation without connecting to rejected inputs.
