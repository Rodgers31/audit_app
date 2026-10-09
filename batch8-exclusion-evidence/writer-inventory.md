# Scheduled / independent writer inventory (#572 finding 3)

Source: base `97fe77462b4e63ffad7dc393b8bf97d3e51571f7` (line numbers at base unless
noted). Produced by a read-only research pass, then key receipts re-opened by the
author (marked ✔). Claims sourced only from docs are labelled UNVERIFIED.

Covered = reaches `seeding.cli.run_seed_command` → `seeding.exclusion.enter_domain`.

| # | Entry point | Launch / default | Covered | Writes | Overlap with native domains |
|---|---|---|---|---|---|
| 1 | `seed.yml` → `python -m seeding.cli seed --all` / `--domain X` | cron `0 2 * * *`, `0 3 * * 0` ✔ (`seed.yml:8-9`); `--all` `:555`, `--domain` `:561` ✔; job concurrency group `seed-production-database` ✔ (`:52-54`); `migrate` job runs `alembic upgrade head` first ✔ (`:389-401`) | **Yes** | every registered domain's tables + `ingestion_jobs` | — (native path) |
| 1b | `seed.yml` bootstrap job → `initialize_reference_data()` | Sunday run or `run_bootstrap=true`; `needs: [migrate, seed]` | No | as #5 | as #5 |
| 1c | `seed.yml` validate → `record_row_census` | after seed | No | one COMPLETED `ingestion_jobs` row (`staleness.py:732-742`) | none in practice |
| 2 | `etl.worker` → thread → `python -m etl.backfill` → `KenyaDataPipeline.download_and_process_document` → `etl/database_loader.py` | `ENTRYPOINT ["python","-m","etl.worker"]` ✔ (`etl/Dockerfile:35`); `etl` service in `docker-compose.prod.yml:161` ✔ and other compose files; image built by manual `docker-build-deploy.yml`; `ETL_RUN_ON_START` default `"true"` ✔ (`etl/worker.py:46`); own advisory lock `874321` ✔ (`etl/worker.py:11`) held only by the scheduling loop, jobs run in fire-and-forget threads ✔ (`etl/worker.py:108-112`) | **No** | inserts `audits` ✔ (`etl/database_loader.py:526-537`), `countries`, `entities`, `fiscal_periods`, `source_documents`, `budget_lines`, `population_data`, `gdp_data`, `economic_indicators` | **audits**, entities, fiscal_periods, source_documents, budget_lines, population_data, gdp_data, economic_indicators |
| 3 | `etl/scheduler.py` (`schedule` lib) → `run_full_pipeline` → same loader | no launcher in repo (docstring `python -m scheduler` only) | No | as #2 | as #2 |
| 4 | Web light discovery APScheduler jobs `etl_oag_light`/`etl_cob_light`/`etl_treasury_light` and `POST /api/v1/admin/etl/run` (`main.py:7863, 7961-7994`) | lifespan `_setup_etl_scheduler`; scheduled only if `etl.kenya_pipeline` imports — not in backend-only images, yes where compose mounts `./etl` | n/a | **no DB writes** — report/known-URL files and email; deep mode refused (`main.py:7735-7736, 7879-7884`) | none |
| 4b | Parliament APScheduler jobs → `etl.parliament_orchestrator` | `PARLIAMENT_PIPELINE_ENABLED` default `"0"` | No | `source_documents`, `parliament_source_documents` | `source_documents` only |
| 5 | Bootstrap `initialize_reference_data` on web boot | `main.py:1704` ✔, every web worker start; always on | **No** | `countries`, `fiscal_periods`, `source_documents`, `entities`, entity-linked `gdp_data`, bootstrap-tagged `loans` deletes, terminal `ingestion_jobs`; **calls the `national_budget` handler directly** ✔ (`backend/bootstrap.py:841,865`, from `:1063`) incl. `budget_lines` deletes | **national_budget out of band**; reference tables. Does **not** write `audits` |
| 6 | AutoSeeder (`services/auto_seeder.py`) | `main.py:1711-1716` ✔; `AUTO_SEEDER_ENABLED` defaults true in production | No | reference `entities` (47 counties + national); other domains refuse | `entities` table, rows disjoint from audits' entities |
| 7 | `routers/etl_admin.py` `POST /trigger/{source}` | admin HTTP | n/a | `etl_dispatch_commands`, `admin_audit_log` only | none |
| 8 | `admin_etl_dispatch_worker` → adapter → `run_seed_command` | no launcher in repo; `ADMIN_ETL_DISPATCH_ENABLED=="true"` required (`admin_etl_dispatch.py:35-36`); mapping `{"oag": "audits"}` only (`:19`) | **Yes** | audits domain | — |
| 9 | Alembic `9f033e9c86d3` → `backfill_publishable_audits` | `ci.yml` `run-migrations` on push to main/develop ✔ (`ci.yml:361-403`), `seed.yml` migrate | No (one-time) | `audits.publishable`/`quarantine_reason` | audits (once) |
| 10 | Manual scripts `backend/scripts/normalize_fiscal_periods.py`, `scripts/verification/oag_boundary_correction.py`, `backend/scripts/cleanup_stale_bootstrap_loans.py` | by hand | No | `budget_lines`, `audits`, `extractions`, `fiscal_periods`, `loans` | audits, extractions, budget_lines, loans |

UNVERIFIED from this repository: which hosts actually run the compose `etl`
service, whether its database is the same as `seed.yml`'s `DATABASE_URL`, and the
production web host (no render/Procfile/fly config in the repo).

## Writers of the audit tables

1. Native CLI `audits` domain — covered.
2. Dedicated dispatch → adapter → CLI — covered.
3. `etl/database_loader.py` via `etl.worker`/`etl.backfill`/`etl.scheduler` — **not covered**: no claim, no RUNNING `ingestion_jobs` row, different advisory key.
4. Alembic `9f033e9c86d3` — not covered, one-time.
5. Manual scripts — not covered.

## What the exclusion actually guarantees

Native ↔ native and native ↔ dedicated dispatch, for every domain the CLI runs.
It does **not** exclude #2/#3 (legacy loader, writes `audits`), #5 (bootstrap runs
`national_budget`), #1b, #6, #9 or #10. A statement that native and dispatch are
exclusive *with all writers* additionally requires quiescence:

- no `etl` compose service / `etl.worker` / `etl.backfill` / `etl.scheduler`
  process against the same database;
- no web process boot/restart and no weekly bootstrap job during a
  `national_budget` run (or route bootstrap's call through `enter_domain`);
- no manual scripts in #10, no first application of `9f033e9c86d3`;
- `PARLIAMENT_PIPELINE_ENABLED=0` (default).
