# Exact local commands and final results

All commands were run in the attached owned checkout. Public PostgreSQL fixtures
use one owned loopback database; the independent adverse suite creates/removes
only its `batch7_adversarial` schema. Run these sequentially, never against a
production or another lane database. The owned container has been removed.

```sh
cd /Users/roger/.codex/worktrees/batch7-etl-worker/audit_app
docker run --detach --rm --name audit-batch7-etl-worker-db \
  -e POSTGRES_USER=batch7_worker -e POSTGRES_PASSWORD=batch7-inert-local \
  -e POSTGRES_DB=batch7_etl_worker -p 127.0.0.1:55481:5432 postgres:16-alpine
```

Fresh owned PostgreSQL successfully traversed the actual existing migration chain
to `d8f4a619b203`, then upgraded the additive head. The retained migration tests
execute actual downgrade/re-upgrade and nonempty/active-worker refusal checks.

```sh
cd /Users/roger/.codex/worktrees/batch7-etl-worker/audit_app/backend
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHONDONTWRITEBYTECODE=1 \
  PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app/backend \
  DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  /Users/roger/Documents/projects/audit_app/venv/bin/python -m alembic upgrade head
```

Final combined replay, exact tested source `c8cfc5931f22a4cc121005e3f5285845a9480336`:
**281 passed, 1 strict xfailed (#572), 3 warnings in 25.39s**. The prior combined
run exposed the two repaired direct-call compatibility regressions; it was not
claimed green. Independent tightened adverse replay: **70 passed in 1.94s**.

```sh
cd /Users/roger/.codex/worktrees/batch7-etl-worker/audit_app
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHONDONTWRITEBYTECODE=1 \
  PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch7-etl-worker/audit_app/backend \
  DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  BATCH7_ETL_TEST_DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  BATCH7_ETL_ADVERSARIAL_DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker \
  /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest \
  backend/tests/test_batch7_etl_postgres.py backend/tests/test_batch7_etl_process.py \
  backend/tests/test_batch7_etl_migration.py backend/tests/test_batch7_etl_contract.py \
  backend/tests/test_batch7_etl_adversarial.py backend/tests/test_admin_operations_lane.py \
  backend/tests/test_admin_operations_adversarial.py backend/tests/test_etl_admin_endpoints.py \
  backend/tests/test_web_ingestion_ownership.py backend/tests/test_ingestion_query_transfer.py \
  backend/tests/test_seeding_cli_budget.py backend/tests/test_seeding_utils.py -q
```

Before fixing each independent finding, the exact same clean env ran the retained
test selectors. Observed red/green selectors:

- `test_batch7_etl_postgres.py -k capability_transaction_failure`: 1 failed → 1 passed.
- `test_batch7_etl_contract.py -k normalize_offsets`: 1 failed → 1 passed.
- `test_batch7_etl_adversarial.py -k 'nonboolean_semantic or incoherent_correlated'`:
  8 failed → 8 passed; full independent final suite 70 passed.
- `test_admin_operations_adversarial.py -k direct_duplicate_trigger`: two failures
  in combined run → 4 passed after strict dictionary normalization.
- `test_batch7_etl_process.py -k independent_native --runxfail`: **1 failed**,
  observed two inert committed effects rather than one; tracked #572, unresolved.

The migration, CLI session, command storage and native process execute. Auth and
domain handlers are inert; root product lifespan is never booted. No fixture
fetches or publishes actual source data. Socket transports in native adverse/
process fixtures permit only the owned PostgreSQL resource.

Repository-pinned critical flake8 gate: output **0**, exit 0, every changed
Python file including the migration and native fixture. Exact tool location is
in `resource-manifest.json`; arguments were
`--select=E9,F63,F7,F82 --count --show-source --statistics`.
`git diff --check` passed; staged secret-pattern inspection found no private
keys, JWTs or real provider credentials. Text receipts only trim trailing spaces.

Cleanup actually executed:

```sh
docker exec audit-batch7-etl-worker-db psql -U batch7_worker -d batch7_etl_worker -Atc \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='batch7_etl_worker' AND pid<>pg_backend_pid(); SELECT count(*) FROM pg_namespace WHERE nspname='batch7_adversarial';"
docker stop audit-batch7-etl-worker-db
lsof -nP -iTCP:55481 -sTCP:LISTEN
pgrep -f '^/Users/roger/Documents/projects/audit_app/venv/bin/python -m admin_etl_dispatch_(worker|adapter)'
```

Results: SQL **0 / 0**; stop printed owned container name; lsof/pgrep no output,
exit 1 (no owned listener/process). No other resources were stopped.
The full repository/coverage and disabled hosted security/quality gates remain
unexecuted. Actual UI/backend replay and production activation are coordinator
acceptance work; local fixtures cannot close those gates.
