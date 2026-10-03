# Source1707/1718 disposition for #319

This packet proposes retaining both IDs and their source history, archiving the
app artefacts, and removing them from public publisher inventory counts. It
contains no production execution receipt. The remaining prerequisite is the
release owner's guarded execution and actual API/rendered acceptance.

The updated [issue319](https://github.com/Rodgers31/audit_app/issues/319) makes
1707/1718 the only remaining disposition. The accepted Round20 publisher,
county-code, CPI, metadata/audit cleanup and population requirements are recorded
in [actual production acceptance](../../verification/2026-10-03-round20-production-acceptance.md).
This plan does not repeat those corrections.

## Origin evidence and exact disposition

| Source | Evidence | Exact prospective change |
| --- | --- | --- |
| 1707 | Captured URL `https://fixtures.example/budgets`, metadata `dataset_id=fixture-budgets`, title `County Budget Execution Summary` match the retained Git fixture and writer title/default publisher | Publisher `AuditGava (test fixture)`; status `ARCHIVED`; add `source_classification=test_fixture` and a disposition history object |
| 1718 | Captured label/title `Estimated based on CRA Equitable Share FY 2023/24`, generic CRA page URL and `data_quality=estimated` match the retained app generator and subsequent writer | Publisher `AuditGava (modelled estimate)`; status `ARCHIVED`; add `source_classification=modelled_estimate` and a disposition history object |

The exact before/after images are in [plan.json](plan.json). Preserve all original
metadata members and every other source column: IDs, country, document type,
title, URL, timestamps, file path, transport fields and digests. The original
publisher/status are also recorded in the added history object. No fact,
extraction, source1836 or legacy evidence record is deleted.

Historical receipts:

- Git `ec7706c8395d8ccf4dc86e9a9af7a1c0d9cc0777` contains
  `backend/seeding/fixtures/budgets.json`, the exact 1707 fixture URL/dataset.
  Its `counties_budget/writer.py` creates sources with literal Controller of
  Budget publisher and `dataset_title("budgets")`; `seeding/config.py` supplies
  the captured title.
- The same commit's `counties_budget/real_budget_fetcher.py` computes a 50%
  population/50% equal allocation, then supplies fixed sector shares, 85%
  expenditure and 92% commitment. An actual replay in an owned temporary
  directory produced **470 rows across47 counties**, all with the captured 1718
  label, URL and estimated quality. Generated file SHA256:
  `3f6b8cba2782192b7704fc117f512bb8e25c552f05ac4f3c61883903b896787f`.
- Git `ded5d74`'s writer uses the record's source label/title and quality while
  retaining the literal CoB publisher. Current generator entry points are
  withdrawn, exercised by `test_legacy_budget_generator_withdrawal.py`.
- [origin-receipt.json](origin-receipt.json) binds these historical blobs, replay
  sample and complete dated source images. Retained Git history begins after
  the rows' November2025 creation dates. This proves matching app origins and
  writer behavior; it does not identify the actual creation invocation.

The generator's claims about CRA/KNBS inputs do not certify those figures. This
disposition establishes app origin and removes an unsupported publisher claim;
it does not call the model an official CRA publication or assert a verified CRA
allocation. Fetching a current generic CRA page cannot establish historical
publication of the generated amounts.

## Fresh capture and logical candidate review

Root captured a repeatable-read, read-only transaction at
**2026-10-03 14:47:21–14:47:50 UTC**, with a 15-second statement limit, confirmed
`transaction_read_only=on` and refused INSERT SQLSTATE25006. Parent packet
SHA256: `20c505ef5b6244464f59905385b50328ff1d54ea8999ad5b9862b9cc2b85ef76`.

[fresh-reviewed-capture.json](fresh-reviewed-capture.json) preserves both complete
source images, all13 empty incoming source-reference sets, full FK catalogue,
30 JSON-column query receipts, protected15-table digests and sequence images.
The target source images match the earlier supplied packet exactly. These are
observations at the stated time, not permission to execute later.

All three broad ID/URL scan candidates were reviewed by exact semantic path:

| Candidate | Actual match | Disposition |
| --- | --- | --- |
| Extraction6398, source2539 | `extracted_json.finding_text`: Isiolo headcount `(1707) employees` | Unrelated numeric fact; preserve whole extraction |
| Ingestion job3156 | `metadata.documents[0].extraction_attempt.proposal.audit_ids[804]=1707` | Historical audit ID in source2392 reconciliation proposal; preserve job |
| Source2392 | `metadata.last_extraction_attempt.proposal.audit_ids[804]=1707` | Historical audit ID, not a source ID; preserve source and proposal |

Candidate whole-image canonical SHA256s and classifications are retained in the
reviewed capture. The raw candidate rows remain in root's hash-bound original
packet. `logical_matches=[]` represents the semantically reviewed active source
references; it does not erase or reinterpret those historical rows. No candidate
includes either target source URL. Source IDs and audit IDs remain distinct.

## Public invariant and verification

Before the fix, an actual isolated endpoint replay counted app fixture/model
origins as Controller of Budget documents. The new regression file ran against
unmodified production base `b19a69a5082a6f931dabb4b642903ff373260581` and returned
**6 failed,6 passed**: the fixture/model rows inflated total, publisher counts,
document-type/extraction counts and registration observation time. This proves
a local runtime defect; live summary/rendered baseline remains root-owned.

`publisher_inventory_criterion()` in `backend/services/source_evidence.py` now
excludes explicit `test_fixture`/`modelled_estimate` classifications and the two
exact retained legacy origin markers from all three summary queries in
`backend/main.py`. It does not infer authority from a government-looking URL.
Ordinary publisher forecasts with estimated quality and genuine archived sources
remain registered documents. Registration is still distinguished from downloads,
extractions and accepted publication; no transport or publication gate is relaxed.

Duplicate search: issue searches for Sources/summary and full bodies of271/276
were read. The earlier mispublisher/fixture work (271/276), Kenya source-status
304, and legacy county-budget publication407 are related; none supplies the
Sources-summary inventory invariant. This confirmed defect belongs to319's
remaining source/public acceptance scope; no separate issue was created here.

Executed verification:

```text
python -m pytest -q -p no:cacheprovider \
  tools/tests/test_source_disposition_pg.py \
  backend/tests/test_source_disposition_packet.py \
  backend/tests/test_source_inventory_origin.py \
  backend/tests/test_freshness_publication_evidence.py \
  backend/tests/test_legacy_budget_generator_withdrawal.py
95 passed, 3 warnings in 7.27s
```

Of these,18 controls actually execute generated SQL on an owned network-disabled
PostgreSQL17 container. Forward default rollback, committed forward, inverse
default rollback and committed inverse preserve exact source images. Separate
before/after-image, new FK reference, catalogue, outside-public FK, nested logical
ID and URL/fragment controls refuse atomically. The container was removed after
execution. Two initial local rehearsal startup failures were corrected: installed
libpq has no postgres server; the owned Docker fixture must await the final TCP
server rather than its transient initialization socket. Neither failure concerns
production or the disposition SQL.

Independent review found the initial compiler accepted eight malformed source
field types and a missing logical-column catalogue. The compiler now validates
all source field types, complete timestamp syntax/calendar values, nullable digest
and integer HTTP status, plus the exact30-column logical catalogue. Nineteen
added regression cases failed when those validations were removed and pass with
them restored. The runtime SQL also refuses added/dropped JSON columns. These
were confirmed tooling gaps in319; no production bypass/corruption is claimed.

The renderer rejects the original dated packet schema, missing columns, wrong
country/origin/publisher, boolean/float IDs, incomplete/duplicate FK capture,
nonempty dependencies, metadata type changes, nonfinite JSON and SQL delimiter
injection. No shared Python environment, production connection or existing
database was modified by this lane. Root independently executes adversarial
checks before accepting the implementation. A separate actual PostgreSQL JSONB
query executes the inventory predicate and retains official archived estimates
and null/array/boolean registration metadata without a database error.

Root reported independent final PASS against the frozen compiler/plan/forward/
inverse hashes:48 direct probes (47 required refusals plus healthy input),27
actual PostgreSQL forward/inverse/drift controls,11 actual endpoint controls,
and subsequent concurrency and7 PostgreSQL inventory controls. These are
independent review receipts owned by root, separate from this lane's95-test
command above. The compiler/source/public fixes are ready for root's exact
committed-blob comparison; production acceptance still remains outstanding.

## Guarded operation and inverse

[archive.sql](archive.sql) and [recover.sql](recover.sql) are generated by
`tools/prepare_source_disposition.py` from the fresh reviewed capture. Both end
in **ROLLBACK**. They are not migrations, writer defaults or automatic runtime
cleanup. The plan carries the canonical capture SHA256; regeneration follows:

```text
python tools/prepare_source_disposition.py \
  docs/operations/2026-10-03-round21-source-disposition/fresh-reviewed-capture.json \
  docs/operations/2026-10-03-round21-source-disposition
```

The SQL locks all inspected public tables during the coordinated writer window,
checks the exact incoming FK and logical-column catalogues and refuses an
outside-public incoming FK.
It checks every public `source_document_id` column, then scans nested declared
source/document ID keys and target URL strings in public rows. Numeric/string
equivalents and URL fragments are included; prose headcounts and `audit_ids`
remain unrelated data. A new reference causes refusal and a new reviewed plan.
This scope does not certify external textual citations or arbitrary undocumented
ID encodings; root must retain the recorded complete schema/query review.

The forward guard compares each **complete** row to its before-image. Only
publisher/status/metadata are assigned; a complete after-image check runs before
rollback/commit. The inverse requires the exact archived after-image plus the
same dependency guards and restores only those three fields. Newer title,
metadata, timestamp, classification or relationship changes prevent recovery.
No sequence value is advanced or reset by either UPDATE.

Root owns the final approval, coordinated writer window, current guarded dry
run, independently reviewed recovery and assessment of the existing accepted
logical backup/restore against this new two-row operation. The prior backup
supports the previously accepted operations; this packet does not claim a new
backup/restore or a production write.

## Original requirement → evidence → final prerequisite

| Requirement | Evidence now available | Final prerequisite |
| --- | --- | --- |
| Source1707 fixture disposition | Exact fixture URL/dataset/title writer match; complete fresh row; truthful archive plan preserving ID/history | Root approves exact disposition, performs guarded operation and reads committed row |
| Source1718 mispublisher/disposition | Actual historical generator replay and estimated metadata; app-origin publisher rather than unsupported CRA attribution | Same operation and complete committed row readback |
| Dependency/preservation requirement |13 empty FK sets; full catalogue; three unrelated logical candidates reviewed/preserved; protected15 digests/sequences | Repeat runtime guards, compare all protected cohorts/schema/sequences and candidate whole-image hashes after execution |
| Public source acceptance | Meaningful baseline reproduction, fixed summary invariant and ordinary official archive/forecast controls | Deploy exact code, signed cache refresh, actual API summary and rendered `/sources` acceptance |
| Recovery/release acceptance | Rollback-default forward/inverse and18 actual PostgreSQL controls; known inverse protection against new evidence | Root independently verifies final guards/recovery, assesses accepted backup scope, authorizes exact live actions |

Only after those actual after-state checks pass should319 close. Preserve
source1836, genuine47-county project metadata, population79, corrected CPI and
publisher/code cohorts. Actions remains OFF; this lane did not push, open a PR,
mutate an issue, contact an external recipient or trigger provider jobs.
