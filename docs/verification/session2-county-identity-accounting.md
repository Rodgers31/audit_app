# County identity and accounting — Session 2

Base: `main` at `1bd397f398450245da83abc2e24502ab16ffb063`. No production writes, seed runs, merges or deployments were performed.

## Identity evidence and API contract

All 47 codes were checked against [KNBS's county categories](https://statistics.knbs.or.ke/nada/index.php/catalog/13/variable/F19/V753?name=county) and the [Constitution, First Schedule, PDF pages 164–165](https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf#page=164). The extracted KNBS table is pinned in `backend/tests/fixtures/knbs_county_codes.json`.

| Identifier | Nairobi | Mombasa | Meaning |
|---|---|---|---|
| Official code | `047` | `001` | Public `code`, bootstrap metadata, `/counties/code/{code}` or `code:{code}` |
| Legacy route ID | `001` | `047` | Existing bookmarks and map/list `id`; deliberately unchanged |
| Production Entity PK observed 2026-09-27 | `3` | `4` | Database relationship key; unpadded numeric route |
| Production slug | `nairobi-county` | `mombasa-county` | Stable identity route |

Codes are never substituted for primary keys or historical route IDs. The five accepted route forms resolve through county-typed identities; wildcard/substring institution matching is removed. Coordinates follow the resolved county. Nairobi City and official hyphen/slash spelling variants are covered. Bootstrap derives codes from the authoritative name mapping, never the legacy route map.

Read-only production inspection found exactly four incorrect metadata cells: two fiscal-year `county_code` values on each of Nairobi and Mombasa. This establishes incorrect codes, **not crossed financial records**. No evidence found here justifies swapping amounts, names, IDs, slugs, or foreign keys.

## Accounting contract

Entity list, entity period series, county list/map/plain detail/comprehensive, and all three money-flow routes use a shared publication function. Prefer one reported Total row; otherwise require both Recurrent and Development. Never add Total to its components, sectors, revenue, or another period. Preserve reported zero and absent spending. Publish fiscal period, currency, accounting basis, source documents/page references and absence reasons. Missing page locators remain explicitly empty; source presence is traceability, not a claim of independent verification.

Duplicate classifications, mixed periods/documents/currencies, malformed values, explicitly modelled/projected/quarantined rows, and unsupported sector-only totals are withheld. A national county aggregate is absent if a constituent county's amount is absent. Ratios and health-budget components use the same published amounts. The frontend honors the explicit summary, including genuine zero and explicit absence, while retaining compatibility with older API responses.

## Exact migration proposal and recovery

`session2-county-code-proposal.json` records the read-only API snapshot's four cell edits. `session2-county-code-proposal.sql` locks county identities, requires all 47 PK/name/slug triples to match the observed snapshot, checks every expected old cell, changes only those four JSON paths, emits before/after metadata, and ends with **ROLLBACK**. It has not been run against PostgreSQL or production. The pure proposal and representative BudgetLine/Loan/Audit relationships were exercised in SQLite, including reverse/idempotence checks.

Release owner procedure:

1. Deploy the corrected resolver/writer first and identify the actual backend commit/cache namespace. Freeze concurrent metadata maintenance during migration.
2. Take an external database backup and verify restoration in a separate database. Export the 47 entity rows and per-entity counts/IDs for every table referencing `entities.id`, plus source-document associations.
3. Regenerate the full 47-identity proposal from the database; compare with the four-cell snapshot. A mismatch, missing county, duplicate name, changed ID/slug or unexpected code requires new review. Coordinate with Session 1's metadata cleanup: its whole-JSON compare-and-set manifest must be regenerated after this metadata edit.
4. Rehearse the SQL with its terminal rollback, then inspect exactly two changed rows/four paths. Only after release authorization replace the terminal rollback with commit. Recheck foreign keys/counts and every unrelated JSON path.
5. For recovery, compare the four current paths to the proposed **after** values, then restore only their recorded **before** values. Abort on drift. Do not restore whole legacy metadata over Session 1's cleanup. Use the verified backup for larger recovery only under the release owner's procedure.
6. Refresh/advance application caches and verify all 47 public codes, both historic URLs, slugs, raw PKs, official-code routes, and source/period/amount agreement across cards and waterfalls. Keep #306/#328 open until deployed verification.

## Executed evidence

- Original #328 fixture: eight failures on the original entity implementation; Total 100 + Recurrent 60 + Development 40 + revenue 10 and an older half-sized period exposed 210/315, null-to-zero and unsupported aggregation.
- Independent identity attacks found and pinned alias 404s, wildcard matching and Mombasa receiving Nairobi coordinates through alternate URLs. All 47 × five identifiers × three views now pass, with invalid identifiers and explicit official-code endpoint coverage.
- Original money-flow implementation: 13 failed/8 passed on 21 independent cases. Current 21 pass (missing Total spending, printed 0, unsupported sectors, partial classification spending, and valid controls).
- Final backend suite excluding external PostgreSQL integration: **2853 passed, 10 skipped**. Final independent identity/money-flow suites: 82 passed; full bootstrap identity test: 47 county codes verified. Final entity accounting/health tests: 9 passed.
- Frontend API suites 28 passed; TypeScript no-emit check passed. Explicit summary zero/absence tests were executed red before the adapter fix.
- Full backend run before final fixture corrections: 2906 passed/10 skipped/17 failed. Three failures were stale sector-only expectations corrected to the new contract and rechecked. Fourteen integration failures depended on unavailable localhost PostgreSQL; nine also reproduced on untouched base. Five newly exercised lookup paths hit that same missing service. These are distinct groups, not fourteen baseline-identical failures. The five additional paths passed the focused PostgreSQL follow-up below; the nine baseline failures were not broadly rerun.

Adversarial agents executed malformed-number/provenance/source/date tests and real HTTP/SQLite relationship tests. The proposed SQL metadata migration remains unexecuted. The separate #336 receipt covers PostgreSQL writer concurrency.

## Focused PostgreSQL follow-up

Application code tested: `79db24d79fc75d7b1272455b4d63a92a52851208`. GitHub Actions [run 36309489454](https://github.com/Rodgers31/audit_app/actions/runs/36309489454) passed backend, frontend, ETL, security and quality checks at that head; deployment/migration jobs were skipped. The backend workflow excludes `tests/integration`, so that green run does not certify these five paths.

`backend/scripts/verify_county_identity_postgres.py` runs these exact existing test nodes:

| Test node | Newly exercised lookup |
|---|---|
| `tests/integration/test_api.py::TestCountiesAPI::test_invalid_county_id` | Invalid county identifiers now consult the authoritative county table. |
| `tests/integration/test_api.py::TestDataValidation::test_sql_injection_prevention` | Hostile identifiers pass through the database-backed resolver. |
| `tests/integration/test_public_routes.py::test_public_get_routes[route17]` | `/api/v1/counties/{county_id}/audits` |
| `tests/integration/test_public_routes.py::test_public_get_routes[route20]` | `/api/v1/counties/{county_id}/accountability` |
| `tests/integration/test_public_routes.py::test_public_get_routes[route21]` | `/api/v1/counties/{county_id}/summary` |

The three route-sweep cases use `county_id=1`. Previously, name resolution padded this to legacy route `001`/Nairobi without a database lookup. It now treats unpadded `1` as an Entity primary key and checks its type. Route indices above apply to the tested commit; adding the explicit official-code endpoint shifted the old sweep indices by one.

The follow-up used a disposable `postgres:17` container, bound only to `127.0.0.1:53333`, without persistent volumes. A fresh database contained synthetic versions of all 47 official county identities, National Government at PK 1, Nairobi at PK 3 and Mombasa at PK 4. Synthetic audit/source rows provided positive route controls; no production data was imported or changed. The script refuses non-loopback URLs, databases without the `audit_app_session2` prefix, nonempty databases and Python optimization that disables assertions.

Result: **5 passed**. Because the existing route sweep allows HTTP 500, the script additionally requires national PK 1 to return 404 on all three routes and 24 valid identifier/route combinations to return 200 with the expected county name. The valid identifiers are `3`, `4`, `001`, `047`, `nairobi-county`, `mombasa-county`, `code:001` and `code:047`. Raw output: `session2-postgres-identity.txt`.

Reproduce against a newly created empty local PostgreSQL database:

```sh
SESSION2_POSTGRES_URL=postgresql://postgres:LOCAL_PASSWORD@127.0.0.1:LOCAL_PORT/audit_app_session2_identity python backend/scripts/verify_county_identity_postgres.py
```

Independent harness checks additionally passed 34 URL/database guard cases across both scripts and three identity-verdict controls. Those checks used stubs without database connections: a wrong-county HTTP 200 and a nonzero pytest result both block success. Receipts: `session2-postgres-guards-final.txt` and `session2-postgres-identity-verdict-final.txt`.

This verifies the five requested paths with PostgreSQL. It does not claim a complete integration-suite pass or rehearse the proposed metadata migration.
