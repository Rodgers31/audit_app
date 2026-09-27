# Public evidence containment and reviewed cleanup

Session 1, 27 September 2026. No production mutation, deployment or merge is authorized by this document. The cleanup manifest contains **retired, unverified claims as historical before-images**, not publishable evidence.

## Public metadata contract

`Entity.meta` is private storage. Public list/detail serialization reconstructs only:

- `county_code` and `metrics[FY].county_code` as three-digit strings (identity correctness is session 2's separate responsibility).
- `governor` / `deputy_governor` with a named publisher and HTTP(S) source URL. Their provenance is restricted to `source`, `source_url`, positive integer `source_document_id`, `extractor`, and `fetched_at`.

There are no frontend consumers of raw entity metadata. County identity/search consumes the code; officeholder pages consume the sourced name/provenance. Financial, population, project and audit evidence use their dedicated publication paths. Unknown keys, including future keys and nested extras, are private by default. Both response models validate metadata, in addition to the handlers. Malformed metadata must not hide an otherwise valid entity.

The comprehensive and national missing-funds routes use the extracted unaccounted-finding reader shared with #325, including its citation-based display. Retired metadata claim arrays remain excluded. #327 supplies the sourced project reader. Resolve integration in favor of those dedicated readers while retaining the hostile-metadata regressions. The metadata filter is not permission to erase any `Audit` or extraction.

`/etl/kenya/sources` is a source catalogue with explicit unknown health, null timestamps, and `live_check_unavailable`. The unshipped developer checker is no longer imported. Measured pipeline observations are available through `/data/freshness`. Repository search found no frontend consumer of the retired live-check response.

Unextracted audit rows whose stored document origin is `oag_national_audit_data.json` or `oag_audit_data.json` are retired fixtures, not findings waiting for citations. Publication and withheld counts use that origin predicate, never document IDs. A genuine extraction remains subject to the ordinary gate. Backfill marks retirement explicitly; code contains exposure before cleanup.

## Exact proposed data change (#319 item 5, #322 item 1)

`cleanup-manifest.json` records complete before/after metadata and full audit before-images. Production verification used `BEGIN READ ONLY`, checked `transaction_read_only`, and executed a refused INSERT inside a savepoint before reading audit rows. The entity snapshot came from the public list route. No production changes were made.

| Stored data | Observed affected rows | Proposal |
|---|---:|---|
| `economic_profile` | 47 entities | Remove modelled profile only |
| `stalled_projects` and its count/value/paid summary keys | 21 entities, 25 projects | Remove retired fixture payloads |
| `missing_funds_cases` | 3 entities: 3, 4, 45 | Remove retired hand-written cases |
| `audit_summary` | 8 entities: 3, 4, 19, 25, 26, 30, 35, 45 | Remove fixture summaries |
| audits 870–894, document 1836 | 25 audits; no extraction or page; no inbound FK constraints | Delete only after backup, manifest refresh and explicit release-owner approval |

All 47 IDs and every removed key/value are enumerated in the manifest. Document 1836 is retained. #319 items 1–4 (documents 1840/1707/1718 and population row 79) are outside this cleanup. No schema migration is included.

The **25 audit rows and 25 stalled-project JSON records are different datasets**. The manifest's `retirement_basis` records exact fixture hashes and row mappings. Audit rows match the document's named fixture origin, each row's `NAT_001`–`NAT_025` provenance, full finding/recommendation text and seven provenance fields; missing extraction/page alone is not the retirement test. All project fields match `stalled_projects.json` after the writer's county grouping, including its three aggregate fields. Economic profiles match all five bootstrap fields, missing-funds arrays match the complete county fixture arrays, and audit summaries match fixture counts/amounts. Their exact stored before-images remain the execution guard.

## Dependencies, backup and recovery

1. Deploy and verify the API containment. Stop fixture writers before cleanup: #325 removes audit fixture writers; #327 replaces stalled projects. Main's bootstrap still writes modelled economic profiles, so remove that specific writer before approving the profile purge. The runtime filter makes public responses safe while this remains pending.
2. Re-read the affected rows under an enforced read-only transaction. Refresh the reviewed manifest if anything differs. Coordinate with session 2's county-code migration; the SQL compares the **entire** metadata object and refuses drift.
3. Take a database backup covering `entities`, `audits`, `source_documents`, `extractions`, and their schema. Record backup location/hash and demonstrate restore to a disposable database. The manifest is an additional row-level recovery record, not a substitute for a database backup. Freeze relevant writers for the authorized execution.
4. Generate review files locally: `python tools/prepare_legacy_evidence_cleanup.py docs/operations/2026-09-27-public-evidence/cleanup-manifest.json /tmp/evidence-cleanup`. The generator has no database connection capability. Both SQL files end in `ROLLBACK`; an authorized operator must review the exact files and final commit decision separately.
5. Cleanup locks `entities`, `audits` and `source_documents`; checks each before-image, the complete document-1836 snapshot and audit coverage; and refuses newly introduced audit references. Existing foreign keys remain enforced. Review 47 updated entity IDs and 25 deleted audit IDs before committing. Abort on any mismatch; do not relax predicates.
6. `recover.sql` restores the exact metadata/audit before-images only when post-cleanup metadata still matches and IDs are free. It refuses newer data rather than overwriting it. Recovery may restore retired storage while API filtering continues to protect the public response.

Local PostgreSQL rehearsal in `audit_session1_cleanup`: removed all targeted metadata and the 25 audits; recovery restored 47 profiles and 25 audits. Separate probes changed metadata, document provenance, or added an inbound audit foreign key; each caused the forward script to abort. Probe changes rolled back. No rehearsal targeted production.

## Local validation receipts

- Main: `cd backend && python -m pytest -q --ignore=tests/integration` — **2,707 passed, 10 skipped**. A separate county/API selection passed 249 tests. The complete suite's nine PostgreSQL-dependent integration failures reproduce on unchanged main when the integration database is unavailable; they are not counted as passes.
- New metadata/retirement/source-status regressions copied onto unchanged main failed before the fix (21 added failures, separate from those nine environment failures). Numeric metadata routed through county metrics was separately reproduced before fixing the shared resolver (two failures).
- #325 dependent correction: 67 focused backend tests and 23 frontend tests passed. New attribution and stale-report regressions failed on the prerequisite head before the correction. TypeScript and scoped ESLint passed. A Chromium browser test verifies institution, county destination, PDF page link, filtering and clearing.
- #327 dependent correction: 40 focused backend tests passed. New list and comprehensive citation/identity cases failed on the prerequisite head. TypeScript and scoped ESLint passed.
- Independent adversarial harnesses passed: 158 metadata probes, 104 retirement/backfill probes, and 70 citation/attribution probes in each dependent checkout. They included malformed JSON, nested unknown claims, role conflicts, enormous page references, and positive controls retaining genuine unresolved findings.
- Combined consolidation checkout (`95a1f0d` plus the focused changes): 158 selected backend tests and 140 additional sourced-project tests passed, covering both new citation paths and public containment. TypeScript and 23 frontend tests also passed. Retain #325's extracted missing-funds reader, #327's `stalled_block`, and the deletion of the obsolete national-bootstrap test when resolving the main commit. The sourced project reader must receive the original `entity.meta['stalled_projects']` through its own evidence gate; do not feed it the public metadata DTO, which deliberately has no project arrays.
- The cleanup/recovery and drift refusal were exercised on a disposable PostgreSQL database, as described above. No cleanup SQL was run against production.

## Release verification (still open)

After the release owner deploys, check uncached responses from `/entities?entity_type=county&limit=100`, `/entities/{id}`, `/counties`, `/counties/{id}/comprehensive`, `/counties/{id}/audits`, `/audit/findings`, `/accountability/missing-funds`, `/audits/federal`, and `/etl/kenya/sources`. Account for CDN/browser/API cache expiry or the coordinated invalidation secret; a local green test or code issue closure does not prove adoption.

Verify no retired keys/claims, real unresolved findings and their citations retained, assembly/executive labels distinct, geographic county count stable, PDF fragments matching PDF page numbers, and no invented source status/date. Verify withheld counts exclude retired fixtures but retain genuine unsourced findings. Keep #322/#304/#296/#319 open until their deployment/data conditions are met.

## Source receipts and pending code

The OAG County Governments FY2020/21 Volume II PDF identifies the County Assembly of Wajir on PDF page 38 (printed page 30), including paragraph 78's sitting-allowances finding. Local extracted row 3433 retains the assembly name; the previous derived response discarded it. [Report page](https://www.oagkenya.go.ke/wp-content/uploads/2023/02/REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-II-COUNTY-ASSEMBLIES.pdf#page=38).

Opinion wording follows the [OAG's definitions](https://www.oagkenya.go.ke/faqs/what-do-the-various-audit-opinions-mean/). Swahili Qualified/Adverse labels use the English technical term pending competent review under #307; this is not a claimed Swahili translation.

Attribution/headline/UI corrections are preserved in `codex/audit-attribution-after-325`, based on #325 at `e88449fae4e9a4d49ec58a14fd3816db722a0905`. Audit list/county citation corrections are in `codex/audit-citations-after-327`, based on #327 at `3ee591107535280839ff0763b3cf10ddf69ff876`. Only focused commits from those branches should be applied once prerequisites land. They share identical `audit_citations.py`; do not import whole unmerged consolidation diffs.

Transplant commits `2e11db6` (#325 correction) and `e93a669` (#327 correction) individually after those prerequisites land. The main containment commit is `4bdaaf3`. The disposable combined rehearsal ends at `03c0ca3`; its last one-line integration resolution preserves the project reader as described above. This local rehearsal is a receipt, not a release branch.

Backend GitHub CI does not run for prerequisite-branch targets. Main-targeted CI after transplant/retargeting remains a release gate in addition to the local receipts.

## Review corrections, 2026-09-27

- The cleanup renderer uses explicit validation in normal and optimized Python. Five invalid snapshots were rejected before either SQL file was written; the valid manifest generates identical review-only SQL in both modes.
- `budget_execution_history` uses the same dated financial summaries as the entity API, including authoritative totals, source documents, reported zero and missing spending. `health_history` is empty with `dated_health_components_unavailable`: the old utilization-only grade was not the current composite and cannot be presented as historical health.
- Money-flow and county budget responses derive CoB attribution from the selected document's publisher and report series. A Treasury total remains a Treasury-sourced figure. Non-CoB and mixed-publisher totals retain document evidence without receiving a CoB code.
- Both missing-funds routes read extracted, publication-gated findings. No raw metadata fallback or inferred monetary total is restored. Shared source-reader and UI files match #325 so either PR remains usable independently.
