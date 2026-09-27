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

- Original #328 fixture: eight failures on the original entity implementation; Total 100 + Recurrent 60 + Development 40 + revenue 10 and an older half-sized period exposed210/315, null-to-zero and unsupported aggregation.
- Independent identity attacks found and pinned alias404s, wildcard matching and Mombasa receiving Nairobi coordinates through alternate URLs. All 47 × five identifiers × three views now pass, with invalid identifiers and explicit official-code endpoint coverage.
- Original money-flow implementation: 13 failed/8 passed on 21 independent cases. Current 21 pass (missing Total spending, printed0, unsupported sectors, partial classification spending, and valid controls).
- Final backend suite excluding external PostgreSQL integration: **2853 passed, 10 skipped**. Final independent identity/money-flow suites: 82 passed; full bootstrap identity test: 47 county codes verified. Final entity accounting/health tests: 9 passed.
- Frontend API suites28 passed; TypeScript no-emit check passed. Explicit summary zero/absence tests were executed red before the adapter fix.
- Full backend run before final fixture corrections: 2906 passed/10 skipped/17 failed. Three failures were stale sector-only expectations corrected to the new contract and rechecked. Fourteen integration failures depend on unavailable localhost PostgreSQL; nine also reproduce on untouched base. Five additional legacy/alternate lookup paths now require authoritative database resolution and hit that same missing service. This is not a clean PostgreSQL integration verdict; fresh CI with PostgreSQL is required.

Adversarial agents executed malformed-number/provenance/source/date tests and real HTTP/SQLite relationship tests. SQL migration execution and PostgreSQL concurrency behavior remain release/integration checks.
