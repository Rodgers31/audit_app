# Legacy writer boundary inventory

Scope: #581 on pinned #584 head `9e97ca3f1ca43f103a8655447a86d889456a218a`.
Shared native API, models, migration and dispatch policy are consumed unchanged.
The earlier complete repository inventory remains in
`batch8-exclusion-evidence/writer-inventory.md`; this document records this lane's
ownership decisions. `writer-callsite-search.json` contains the executed search.

| Entry | Write boundary and lifetime |
| --- | --- |
| `etl/Dockerfile` → `python -m etl.worker` → thread → subprocess `etl.backfill` | Worker performs read-only schema readiness before scheduling. The actual child loader owns writes; the parent scheduling advisory key 874321 has no writer authority. `run_once` uses the current interpreter and propagates nonzero child exit. Child claims survive parent death. |
| `etl.backfill.run_backfill` | Checks readiness before discovery. Actual document call acquires ownership before reference rows; refusal propagates; failed summary raises instead of exiting successfully. |
| `etl.scheduler` → monitor → `KenyaDataPipeline` | Both package and documented standalone imports work. Startup checks readiness; monitor/scheduler failure propagates. Claims cover the actual loader call, including nested reference/data commits. |
| Pipeline `download_and_process_document` and KNBS fallback | Audit and generic document writes use public loader methods. Ownership refusal escapes generic download/source catches and KNBS fallback; unavailable database loader raises instead of returning fake document id 1. Discovery by itself remains available. |
| `load_document`, `load_audit_findings_document` | Outermost public coroutine holds all thirteen claims until synchronous return and every session closes. Nested country/entity/fiscal calls share the same scope. Parsers, financial transformations, publication fields and source-manifest scope are unchanged. |
| `ensure_country_exists`, `ensure_entity_exists`, `ensure_fiscal_period_exists`, `load_sample_kenya_data` | Each standalone public mutation is guarded. Nested calls reuse the owning thread/task and Engine identity. |
| `get_db_session`, `SessionLocal` | Manual ORM session lifetime owns the same thirteen domains. Shared sessions release only after the last close, independent of close order; closed sessions cannot reopen. Query/add/execute/commit are supported. External Connection binds, raw connection escape, alternative binds and transfer to another task/thread refuse. |
| `etl/seed_all_counties.py`, `seed_ministries.py`, `seed_minimums.py` | Reach guarded public country/entity/sample methods. |
| `etl/seed_county_metrics.py` | Uses guarded country method and manual `get_db_session` through its commit/close lifetime. |
| `get_data_summary`, `etl/post_ingestion_check.py` | Read-only session is plain ORM and does not take writer claims; it can run during ingestion. |
| `_load_*` helpers | Private implementation helpers are reached internally through guarded public document calls and receive that owned session. The search found no production caller outside the loader. Existing tests inject standalone sessions directly into private helpers; these are not supported public writer entry points. Direct Engine/raw database/manual scripts outside this loader remain in Batch 8's quiescence inventory. |

The fixed, lexically ordered set is audits, counties_budget, county_officials,
debt_timeline, economic_indicators, fiscal_summary, national_budget,
national_debt, national_gdp, pending_bills, population, revenue_by_source and
stalled_projects. They share Countries/Entities/FiscalPeriods/SourceDocuments
with legacy writes, or write the same financial tables. A finer document-type
set could omit a nested reference effect; broad admission is the deliberate
choice. Independent learning_hub and IMF WEO tables remain concurrent.

There is one dedicated continuity transaction per domain. The legacy engine uses
NullPool to avoid starving its own writer/observation sessions with thirteen
pinned connections. Capacity and production transaction-pooler evidence remain
#583 gates; no process-global or timestamp-expiry shortcut is used.

RUNNING and terminal IngestionJobs have `writer=legacy_etl`, claim correlation,
and `counts_scope=ownership_only`, with counts zero. They describe authority and
return, not a financial row census. Cancellation, commit/storage uncertainty,
backend death or missing receipt retains authority across restart. Normal
synchronous failure can release only after all sessions return and the shared
API validates its coherent FAILED observation on each original lock backend.
