# Batch 12 SQLAlchemy transfer compatibility handoff

Addresses [#625](https://github.com/Rodgers31/audit_app/issues/625). The budget receipt transfer regression now inspects the executed select expression and actual cursor results instead of one release's PostgreSQL SQL spelling. Product query code is unchanged. Coordinator review, combined hosted verification and merge remain; propose narrow #625 closure only after acceptance.

## Source and publication

- Accepted base: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`; tree `3a680eef19822ef0ac83aa6890c3b41deee97058`. GitHub main matched before worktree creation.
- Implementation commit: `734e0c1175af827bdc2faea30f46a9d563f20ec3`. This handoff is a subsequent documentation-only commit. Final pushed head, draft PR URL/status and remote readback are in external `STATUS.md` / `remote-pr-continuation.json`.
- Branch: `codex/batch12-sqlalchemy-transfer-compatibility`; [branch PR listing](https://github.com/Rodgers31/audit_app/pulls?q=is%3Apr+head%3Acodex%2Fbatch12-sqlalchemy-transfer-compatibility).
- Managed worktree: `/Users/roger/.codex/worktrees/batch12-orm/audit_app`.
- External evidence: `/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/ORM_COMPATIBILITY`. All runtimes, pristine backend snapshot, mutation copies, raw stdout/XML and scripts remain outside source. Primary/peer checkouts were never edited.
- Changed paths: this handoff and `backend/tests/test_budget_qualification_transfer.py` only. No dependency, model, migration, workflow, global fixture, product, skip-policy or threshold changes.

## Repair and behavioral controls

The test retains five actual `qualify_rows` context SELECTs, selected widths `[6,4,2,2,4]`, the original `<100_000` selected-value UTF-8 byte ceiling, original oversized unrelated fields, retained response receipt and all other fixtures/cases. It checks the extraction selected-column names, JSON-getitem expression operator, actual `extracted_json` left operand and `response_receipt` path; replays captured cursor SELECTs; requires one receipt row with the exact IDs/extractor and complete receipt value; and compares the full allocated-amount qualification to the existing expected contract after the session closes. Existing 32 complete qualification cases and six other-table publication-context cases remain unchanged. `scope-proof.json` confirms only the transfer test function's AST changed.

The shared caller remains `services.figure_qualification.qualify_rows`; searched consumers include budget overview/county/public handlers in `main.py`, `routers/data_provenance.py`, `services/budget_execution.py` and the R2 acceptance script. Other qualification tables retain their original full-context queries and tests. This is a regression-test repair, not a caller/product behavior change.

The independent adversarial agent copied the actual backend externally and changed exactly the budget query from `Extraction.extracted_json["response_receipt"].label("response_receipt")` to `Extraction.extracted_json.label("response_receipt")`. The final real test failed on both supported releases for selected-value transfer size, before qualification-output checks; no fake tiny result or source-text substitute. Mutation files/diff/report and raw outcomes remain external under `adversarial/` and `batch12-orm-*-mutation-*`.

Original product bytes match accepted base SHA256 `90a9b9a51d0d36962f72af53ac090a86097b6ecda5a2e3e16dde18cfad67c89b`, independently rechecked after mutation runs. Mutations never touched the worktree, so no product restoration was required.

## Actual verification

Fixed dependency inputs came from this base's `backend/requirements-dev.txt` and resolved freeze; current SQLAlchemy resolved to **2.0.54**, minimum **2.0.23**. Other resolved versions stayed fixed across each paired runtime. Final runtimes: native Python **3.12.15**, SQLite **3.53.1**, pytest **8.3.3**, psycopg2 **2.9.13**; complete freezes/identities retained. Initial Docker baseline separately used Python **3.12.14** / SQLite **3.46.1** on pinned image `f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`.

| Control | Minimum 2.0.23 | Current 2.0.54 | Evidence directory/file |
| --- | --- | --- | --- |
| Pristine baseline, entire original file, Docker | 38 pass + intended rendering failure | 39 pass | `baseline-minimum`, `baseline-current` |
| Pristine baseline, entire original file, native | 38 pass + same rendering failure | 39 pass | `native-baseline-minimum`, `native-baseline-current` |
| Final entire file | 39 pass, zero skips | 39 pass, zero skips | `native-final-minimum`, `native-final-current` |
| Final entire file, Python `-O` / pytest assertion rewriting | 39 pass, zero skips | 39 pass, zero skips | `native-optimized-minimum`, `native-optimized-current` |
| Related handler/publication/transfer cohort | 997 pass + 1 existing skip | 997 pass + 1 existing skip | `native-cohort-minimum`, `native-cohort-current` |
| Real PostgreSQL receipt transport | 1 pass, zero skips | 1 pass, zero skips | `batch12-orm-pg-positive-v2-*` |
| Whole-JSON actual-query mutation, SQLite | 1 intended failure | 1 intended failure | `batch12-orm-mutation-*` |
| Whole-JSON actual-query mutation, PostgreSQL | 1 intended failure | 1 intended failure | `batch12-orm-pg-mutation-v2-*` |
| Complete backend configured critical flake8 selection | exit 0 | exit 0 | `lint-v1-minimum.json`, `lint-v1-current.json` |

The related cohort comprises `test_figure_qualification_handlers.py`, `test_publication_guard_boundaries.py`, `test_public_query_transfer.py`, `test_provenance_query_transfer.py`, `test_provenance_vintage.py`, `test_ingestion_query_transfer.py`, `test_no_published_figure_from_hash_or_clock.py` and `test_budget_execution_live.py`. The sole skip is the unchanged empty quarantine parameter set in `test_no_published_figure_from_hash_or_clock.py::test_quarantined_modules_still_carry_their_debt[relative_path0-expected0-reason0]`. Current/minimum case identities/outcomes are exactly equal. Every changed/required transfer case executed. Raw stdout contains no XPASS/XFAIL. Cohorts overlap and are not additive; this is scoped dual-version proof, not a complete minimum-version backend suite.

Positive selected values: SQLite **82,967** bytes; PostgreSQL **83,033** bytes. Whole-JSON mutant: SQLite **164,983** bytes; PostgreSQL **164,989** bytes. These are selected UTF-8 value estimates from cursor fetches, not PostgreSQL wire bytes, billed/provider egress or deployed performance. `case-reconciliation.json` binds inventories and hashes; each complete run retains stdout, JUnit XML, source-before/after hashes and child exit.

PostgreSQL supplement uses an owned native **16.2** binary pinned by SHA256 `3b104e694edc503952d34d799a9623ba79f37b5e7f4687343628b898c119478d`, loopback **55564**, database `batch12_orm`, owner `batch12_orm_owner`, UTF8 and unique `batch12_orm_*` schemas. External `pg_native_plugin_v2.py` runs the unchanged final test/fixture against PostgreSQL. SQLite permits the fixture's intentionally oversized VARCHAR title/path values; the original PG seam correctly refused them before qualification. The v2 owned transport schema widens only those two columns to TEXT to preserve exactly the original payload. This is not production schema/migration acceptance or proof that oversized titles are valid production input.

## Interruptions and cleanup

`interruptions.md` preserves the initial readiness/import probes, disk exhaustion during first candidate Docker attempts, unavailable Docker daemon, native socket-path startup refusal and original PG VARCHAR setup errors. Incomplete/errored attempts remain separate and are not negative or positive acceptance. Original recorder/plugin bytes and failed logs were preserved; new producer names/paths bind the native fallback and corrected PG seam.

All native test schemas report absence after each PG session. Native server PID **21013** was verified against its exact executable/data directory, stopped with scoped `pg_ctl`, and then absent (`ps` exit 1); postmaster PID file absent and loopback55564 successfully rebound. `cleanup.json` / `native-pg-cleanup.log` retain the proof. Data directories and literal evidence are retained inertly.

**Historical pre-cleanup checkpoint:** Docker cleanup was unverified because Docker Desktop reported unable to start. No shared daemon restart or broad cleanup was performed. Exact owned containers are `batch12-orm-python` (`8d1bb5db09c6fefa1a47d57362d78ecc1d75fde0c9a4e127c1054decea4b95b7`) and `batch12-orm-postgres` (`db903cf666adc7045a52a3599b1749e035da8bf480cfc6efe9518397788bd80c`); saved `resources-initial.json` contains their image/mount/anonymous-volume IDs. The bounded continuation below resolves that earlier cleanup limitation with fresh resource readbacks. Do not infer container absence from daemon unavailability. No application bug or extra issue was discovered beyond #625; setup/environment failures need no duplicate product ticket.

## Remaining gates and lesson

No production provider/database writes, migrations, deployment, activation, repository Actions changes/dispatch or merge occurred. No paid review was requested. Production and broad admin completion remain unchanged. Dependencies #494 and audit storage #611 are independent; this lane needs no shared-file/migration exception. Coordinator owns independent review and immutable combined hosted checks (configured backend/critical lint and the complete integration gate), plus final #625 acceptance. Owned Docker cleanup is verified below.

Suggested narrow skill update: add to `receipt-provenance` an owned-loopback transport example that separates setup refusal from a genuine mutation refusal. Here an unchanged SQLite oversized-string fixture caused PostgreSQL VARCHAR(500) insertion errors; only after a documented owned-schema transport adaptation did the actual whole-JSON mutation fail for **164,989 transferred-value bytes**, while the positive fetched receipt remained **83,033 bytes**. Require original error retention, identical payload/assertion bytes and separate schema-adaptation disclosure. Shared global skills were not edited.

## Approved cleanup continuation — 2026-10-12

Draft [PR #635](https://github.com/Rodgers31/audit_app/pull/635) remains open for coordinator review/integration. This round updates only this handoff. Product/test bytes and the 60 enumerated retained evidence files, including baseline, accepted and genuine-mutation stdout/XML packets, were independently compared before/after resource cleanup and remain identical; no 39-case or related-cohort rerun, dependency install, fixture copy or production operation was performed. Prior acceptance remains bound to `01fec69719a1fd5003ada657d74a54fd7be16b79`; final documentation head and remote body/status are read back in external `STATUS.md` and `remote-pr-continuation.json`.

The human-approved host cleanup is separately recorded at `/Users/roger/.codex/cleanup-reports/audit-app-2026-10-12/CLEANUP_RESULT.md` and `execution-20261012T195441Z/FINAL_VERIFIED.json`. This lane read the current coordination/storage contract and ran normal Python `storage-guard.py check` against the unchanged global baseline of **188,380,164,096 bytes** and shared **10 GiB** growth allowance. Fresh lane receipts are under `storage-checks/`; the resume receipt reports `WITHIN_GROWTH_LIMIT`, **zero measured growth**. The fresh after-cleanup receipt also reports `WITHIN_GROWTH_LIMIT`, with **667,648 bytes** shared-tree growth; this is a combined measurement, not an attribution to this lane. No baseline reset or relocation to evade the quota occurred. Existing worktree, compatible frozen runtimes and original source-bound evidence were preserved; cache-looking retained inputs were not deleted.

Docker **29.8.2** responded to a fresh readiness query. Successful complete container censuses prove both exact original owned IDs already absent; this round does not claim to have removed them or infer their earlier termination cause. The remaining exact anonymous volume `69abb440aa54c40cd37fbd6f8200ea13a6199456f25e35bfc5eb9a184d9ee025` matched its original saved PostgreSQL container mount and creation timestamp, and the complete all-state volume attachment census was empty. The Docker database had only been initialized/read for identity; all behavioral fixtures and their retained evidence use the preserved SQLite/native PostgreSQL paths, so no accepted/failing input depended on the disposable volume's contents. The existing initialization identity and complete resource packets were preserved.

Only that exact unreferenced owned volume was removed, without force. A fresh successful full volume census proves its absence, a fresh container census proves both original IDs absent, and a native bind proves loopback **55564** free. No containers were created, started or removed in this round; no images, networks, peer resources, historical packets or source fixtures were removed. The immutable fresh `docker-cleanup-continuation-20261012.json` binds the producer bytes, source checkpoint, original resource snapshot, raw commands/exits, resource identities, evidence hashes and absence/port proof; producer `docker-cleanup-continuation-v1.py` remains external. Original `cleanup.json` and earlier unverified/error packets remain unchanged historical records. Independent read-only adversarial checks also confirmed live Docker absence, loopback binding, producer hash, all 60 enumerated evidence hashes and unchanged product/test Git blobs. No owned Docker cleanup blocker remains.

Next action: coordinator independent review and exact combined hosted integration/acceptance. #625 remains open pending that review/merge decision. The owned TEXT-width transport adaptation remains a fixture qualification and does not establish production-schema acceptance.
