# Independent Spec review — #582

Review source: `git diff 9e97ca3f1ca43f103a8655447a86d889456a218a -- backend/bootstrap.py`, plus the lane's untracked ownership tests/fixture/evidence. No product or test edits by this reviewer. Fixed base resolves to `9e97ca3f1ca43f103a8655447a86d889456a218a`; at initial review `HEAD` is that base and the changes are uncommitted.

## Review summary

**Valid P1 readiness defect, corrected and independently verified.** The assignment requires “truthful readiness/provenance, empty-database startup” and “competing bootstrap skips without destructive budget writes.” The initial normal native-first startup took the coarse early return before shared ownership; `main.py:1704-1709` then marked ready. The independent red control recorded ready=True, zero counties, zero bootstrap jobs and one native handler. The author excluded only national_budget from that courtesy check (`bootstrap.py:943-946`). The exact control now passes on both current and minimum ORM runtimes: ready=True, 47 counties, one bootstrap receipt, only the native handler. Red/green raw outputs and source identities are below.

**Valid fixture-isolation gap, corrected.** The original connection-death control queried all granted advisory-lock PIDs in the cluster. The author now filters to its owned current database before asserting exactly one backend and terminating it (`test_batch9_bootstrap_ownership.py:220-224`). This is a test isolation finding, not a product ownership failure. Independent controls used separate databases and cleaned only their own resources.

**No unresolved scoped Spec findings.** Bootstrap enters the shared seam before reference writes (`bootstrap.py:1043`), invokes the handler inside its savepoint (`:873-891`), commits before acknowledgement (`:1151-1157`), and retains failed ownership (`:903-908`). The unchanged seam commits proof/release on its lock-holding transaction (`seeding/exclusion.py:153-188`). The author matrix now passes 20 process controls on each runtime, including empty/repeated current/superseded startup (`test_batch9_bootstrap_ownership.py:179-192`), both acquisition orders and failure/kill/connection loss. Raw receipts match the frozen source hash; the previously pending local gates are satisfied for #582's national_budget path. #584 acceptance and coordinator operational checks remain dependencies.

The unchanged non-budget coarse deferral still has a broader false-ready case. Author reproduction records audits RUNNING → ready=True with zero counties in `other-domain-readiness.txt`; it is being tracked separately, with no scope expansion here. This review does not certify every bootstrap readiness path.

## Executed independent evidence

Command (exit **1**, expected red):

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/roger/.codex/worktrees/1183/audit_app/backend DATABASE_URL='postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183' BATCH9_BOOTSTRAP_POSTGRES_URL='postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183' /Users/roger/Documents/projects/audit_app/venv/bin/python docs/admin/implementation/batch9-bootstrap-evidence/spec-readiness-control.py > docs/admin/implementation/batch9-bootstrap-evidence/spec-readiness-red.txt 2>&1
```

Raw result: [`spec-readiness-red.txt`](spec-readiness-red.txt). Reproducer: [`spec-readiness-control.py`](spec-readiness-control.py). CPython **3.13.9**, SQLAlchemy **2.0.46**. Control script SHA-256 `71b8b9d4470c7c76e97b08aee20046cdf351b8658dd75e13e0f748833cf2752f`; loaded bootstrap SHA-256 `51fe8db458e211ca20331f293ac691f4c14287bea68f7b0bd1ac42c3fd37ec68`.

Actual separate processes: `python -m seeding.cli seed --domain national_budget --no-dry-run`, then `python -c "import asyncio, main; asyncio.run(main._startup_sequence()); print('BOOTSTRAP_READY', main._app_ready.is_set())"`. The fixture substitutes only inert registry handlers; both entrypoints remain real. It blocks external socket transport and supplies its own JWT/settings. The native process remained gated while startup exited 0 with `BOOTSTRAP_READY True`; SQL measured zero county entities and zero bootstrap receipts. After releasing the gate the native process exited 0. The final assertion failed with `Startup reported ready without the required county reference data`.

Control created/dropped only `batch9-bootstrap-spec-1e33f4f9bcd54a6baeb60c09129d2639` and `spec_bd9fa381041e44338c0a9909230e3651`; its child process exited and temporary files were removed. Author tests were paused during the control. No hosted workflow or production/provider/storage call was executed. PostgreSQL evidence is combined-candidate verification with the held #584 seam, not production acceptance.

Exact same command with output redirected to `spec-readiness-green.txt` exited **0**. Raw result: [`spec-readiness-green.txt`](spec-readiness-green.txt). CPython **3.13.9**, SQLAlchemy **2.0.46**, loaded bootstrap SHA-256 `4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`, unchanged control SHA-256 `71b8b9d4470c7c76e97b08aee20046cdf351b8658dd75e13e0f748833cf2752f`. Observed startup exit 0, ready=True, 47 counties, one bootstrap job and one entered handler before native gate release; native exit 0 after release. Created/dropped only `batch9-bootstrap-spec-1d4ce221d5d844afb72ee47d83807833` / `spec_54f038f3d44540659483d81a03fa0e7e`.

Minimum supported ORM command (exit **0**):

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/roger/.codex/worktrees/1183/audit_app/backend DATABASE_URL='postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183' BATCH9_BOOTSTRAP_POSTGRES_URL='postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183' .local-dev/batch9-bootstrap-min/venv/bin/python docs/admin/implementation/batch9-bootstrap-evidence/spec-readiness-control.py > docs/admin/implementation/batch9-bootstrap-evidence/spec-readiness-green-minimum.txt 2>&1
```

Raw result: [`spec-readiness-green-minimum.txt`](spec-readiness-green-minimum.txt). CPython **3.12.15**, actual SQLAlchemy **2.0.23**, same bootstrap/control hashes as current-runtime green. Same observed ready/counties/jobs/handler counts and both process exits 0. Created/dropped only `batch9-bootstrap-spec-c479e893716044099cb2e99d569813e5` / `spec_36f5fe5a3b56487ab004663d9bb73a86`.

## Final author evidence inspected by this reviewer

I read the final process test/fixture and frozen product diff; I inspected these recorded runs, not re-executed them. The exact commands, scoped environment, generator hash and source hashes are in each matching JSON receipt.

| Selection | Current runtime | Minimum runtime |
| --- | --- | --- |
| Real ownership/startup/weekly process matrix | [`ownership-current-final.txt`](ownership-current-final.txt): **20 passed**, no skips/xfails | [`ownership-min-final.txt`](ownership-min-final.txt): **20 passed**, no skips/xfails |
| Reference/readiness/supplied-session regressions | [`regressions-green-final.txt`](regressions-green-final.txt): **143 passed** | [`regressions-min-final.txt`](regressions-min-final.txt): **143 passed** |
| Additional scoped regression selection | [`additional-scoped.txt`](additional-scoped.txt): **45 passed** | Not claimed |
| Empty owned migration chain | [`migration-current.txt`](migration-current.txt): `migration_head e572b8c9a001 claims_RLS True claim_rows 0` | [`migration-min.txt`](migration-min.txt): same actual output |

Counts describe separate selections and are not combined. The process test `test_empty_then_current_superseded_database_startup_keeps_readiness_and_provenance` runs the actual startup twice, checks stable county identities, two `fixture_superseded` receipts, two completed national_budget receipts and two released claims. Startup exits require actual ready=True (`test_batch9_bootstrap_ownership.py:58-61`). Raw current output lines 365-444 show both startups, the second county fast path, and both `BOOTSTRAP_READY True` results; the minimum raw output shows the same path. The native-first selection also asserts an existing inert BudgetLine remains, so “no destructive budget writes” is not inferred solely from handler markers (`test_batch9_bootstrap_ownership.py:141`).

Final process evidence identities were independently checked with `shasum -a 256`: bootstrap `4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`; process test `369f5bad8d5c004367f4130bdd37c1aa897510c235403fe0ab58990f857b52d0`; fixture `1fa4a8c281eada8de0fbcc718db44e9d7e3e6de62b69fececfc1e9c83d8c8be5`. Raw current output hash `113b8d9a0f0649a752d97c501a19c493e68734c95bd44e589c71018d2b675e16` and minimum `38802735ae1994f6a194f6e5147883c2f57c5b2286ee64c751be3d012d27636e` match their JSON receipts. No additional runtime execution was needed because the product source is unchanged from the independently verified controls.
