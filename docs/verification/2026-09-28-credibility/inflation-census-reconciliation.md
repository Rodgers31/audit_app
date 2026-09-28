# Inflation census reconciliation — issue #347

## Evidence and diagnosis

- Base: `a7faedb509b63e8ac68557bf90456cb6f2828629`; branch: `codex/inflation-census-reconciliation`.
- [22 September nightly](https://github.com/Rodgers31/audit_app/actions/runs/35679503870) printed 15 `inflation_rate` rows and a 15-row census baseline. Its economic job fetched 11 World Bank inflation years and reported `items_created=0`, `items_updated=6`; the log does not list the 15 row identities.
- [28 September nightly](https://github.com/Rodgers31/audit_app/actions/runs/36370404355) printed 11 rows, down four (27%) from the 22 September high-water mark. The available failure log has no identities or coverage for the missing four. The existing job metadata writes `(type, date, value)` deletion tuples (`backend/seeding/domains/economic_indicators/__init__.py` before this change), but the stored production metadata was not accessible here.
- The local source fixture demonstrates *possible* legacy off-cycle rows (`2024-06-30`, `2025-01-31`) in `backend/tests/test_inflation_monthly_live.py`. They are **not** asserted to be the four missing production rows. The exact live cause remains unverified.
- A separate writer defect was reproduced: if a live response includes 2022 and 2024 but omits 2023, the old sweep deletes an official 2023 year-end row solely because it lies inside the delivered span. A partial response does not establish that the stored observation is wrong.

## Change

- `writer.py` now validates coverage dates and refuses malformed coverage before deleting anything. It deletes only national off-cycle rows within validated live coverage; a correctly dated annual or monthly observation is retained even if a later source response omits it. The 12-removal/type ceiling remains.
- The economic job now persists exact removal receipts (row ID, type, date, stored value, entity, source document) and delivered coverage dates. The existing fetcher merge rule is retained so a fixture cannot overwrite a previously sourced row when a live response skips that date.
- The row census now saves the annual inflation row identities with its count. A >10%, at-least-two-row drop is explained only if every missing ID matches a successful, non-dry-run economic job's off-cycle receipt and coverage after the high-water census. Losses without that full match still fail. Other labels and tolerance constants are unchanged. Old count-only baselines cannot receive an automatic exemption.

## Red/green and boundaries

All tests used `PYTHON_DOTENV_DISABLED=1`, `DATABASE_URL=sqlite:////tmp/auditgava-inflation-census-test.sqlite`, empty `REDIS_URL`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, `AUTO_WARMUP_ENABLED=false` before imports, with the existing `/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python`. The tests use isolated in-memory SQLite fixtures; no PostgreSQL-specific operation is asserted by them.

- Before the fix, `python -m pytest backend/tests/test_inflation_census_reconciliation.py -q` gave **3 failed, 2 passed**: a missing official year was deleted, malformed coverage deleted a row, and four exact authorized removals still made the census FAIL. These failures were assertions on the observed behavior, not import errors.
- After the fix, `python -m pytest backend/tests/test_inflation_census_reconciliation.py backend/tests/test_inflation_monthly_live.py backend/tests/test_row_count_regression_gate.py backend/tests/test_bootstrap_leaves_live_indicators_alone.py -q` gave **59 passed**. The cases include source-backed annual/monthly gaps, exact authorized supersession, partial or wrong-source receipts, old count-only baselines, empty coverage, and the over-limit removal guard.
- `git diff --check` passed. Adversarial review caught and reversed an attempted merge change that would have allowed a fixture row to overwrite a sourced row during partial live coverage.

## Bounded production read for the coordinator

Run only with a SELECT-only database role over encrypted transport. This query has **not** been executed in this session. Review the removal tuples and source detail for runs from 22–28 September, then compare the surviving rows and source documents. Historical count-only censuses cannot supply missing row IDs; if the old job metadata also lacks sufficient coverage/provenance, do not infer the exact four identities from the net count.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '8s';
SHOW transaction_read_only;

SELECT id, started_at, status, dry_run, errors,
       metadata -> 'superseded_rows_removed' AS removed,
       metadata -> 'supersession_coverage' AS coverage,
       metadata ->> 'source_detail' AS source_detail
FROM ingestion_jobs
WHERE domain = 'economic_indicators'
  AND started_at >= TIMESTAMP '2026-09-22 00:00:00'
  AND started_at < TIMESTAMP '2026-09-29 00:00:00'
ORDER BY started_at DESC
LIMIT 20;

SELECT id, started_at,
       metadata -> 'row_counts' ->> 'Inflation Rate records' AS inflation_count,
       metadata -> 'inflation_rows' AS inflation_rows
FROM ingestion_jobs
WHERE domain = '__row_census__'
  AND started_at >= TIMESTAMP '2026-09-22 00:00:00'
  AND started_at < TIMESTAMP '2026-09-29 00:00:00'
ORDER BY started_at DESC
LIMIT 12;

SELECT e.id, e.indicator_date::date AS observation_date, e.value,
       e.entity_id, e.source_document_id, d.publisher, d.url,
       e.metadata ->> 'measure' AS measure,
       e.metadata ->> 'source_label' AS source_label
FROM economic_indicators AS e
LEFT JOIN source_documents AS d ON d.id = e.source_document_id
WHERE e.indicator_type = 'inflation_rate'
ORDER BY e.indicator_date DESC, e.id DESC
LIMIT 40;

ROLLBACK;
```

## Acceptance remaining

No production database was read or changed, no source was fetched for reseeding, and this code has not been deployed. Keep #347's inflation portion open until the coordinator identifies the actual removed tuples and source coverage, classifies each as authorized or unexplained, and verifies a deployed nightly's row-census outcome. An old 15-row baseline without identity snapshots remains a FAIL until its seven-day window expires or independent source reconciliation establishes the loss; this change does not reset it. There are no additional out-of-scope findings to file from this investigation.
