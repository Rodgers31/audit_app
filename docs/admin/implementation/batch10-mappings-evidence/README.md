# Bounded ETL dispatch evidence

## Coordinator correction — 2026-10-10, #610

The active schema2 index validates **historical execution packet integrity** and
always reports `classification=HISTORICAL_EXECUTION_PACKET` and
`current_checkout_acceptance=false`. References below to “current” executions or
the “final executable source” describe the original author's historical packet,
not a later checkout or integrated candidate. Original 519/275-case runs have
not been rerun or rebound to sibling startup/IMF changes by this publication.

`retained-source-86aa4c3.zip` retains the exact 1,160 declared source files from
commit `86aa4c3a7a29383ed256273bd0097cfc81b3336d`, tree
`051cd539ef2219e9659dd339c720b3ba9e2596c7`. Of these, 1,158 were measured by the
four original executions. The old verifier and package-guard test were two later
publication-only additions; their presence in the archive does not add executed
cases. The archive is deterministic, built from frozen Git blobs, and verified
against the complete original inventory. Safe relative paths, regular members,
complete membership, unique names and content hashes are required.

`python -B docs/admin/implementation/batch10-mappings-evidence/verify_package.py`
checks that archive and every original execution/asset. It deliberately does
not compare later live backend source to old hashes. To verify an **explicitly
materialized historical corpus**, pass
`--retained-source-root /absolute/path/to/extracted-historical-source`; every
retained source file, hash and complete census must then match. Source tampering
still refuses. Copied tests materialize the archived source and use this mode,
so valid sibling changes cannot contaminate their positive fixture. Both modes
are read-only and work under normal/optimized Python; neither certifies the
current checkout. Fresh candidate and integration pytest runs are external.

Strict validation requires nonempty unique JUnit identities, actual nonempty
green counts with exact primitive types, the expected publication generator,
recorder aliases and hashes, and portable execution command/environment/runtime/
cwd/timestamps/source/exit metadata matching the unchanged archived original.
History is append-only. The previous manifest/verifier/README bytes and new
publication provenance are in `history/coordinator-610/`; all original execution
receipts, generators, logs, JUnit and earlier history remain unchanged. The
current verifier and index supersede the old validator, not the old run identity.
See `COORDINATOR_610.md` for scope, actual red controls and final replay locations.
`publish_coordinator_610.py` preserved the frozen source and first schema2
publication. `publish_coordinator_610_v2.py` separately publishes the final census
refinement; its generator and intermediate publication identity are bound in the
active index. The intermediate manifest/verifier/README are retained as well.

## Original author handoff (historical context)

The implemented native units are OAG→audits (preserved), Treasury→fiscal_summary, CoB→counties_budget and KNBS→population. CONTRACT.md states their actual mixed-publisher and persistence scope. OpenData and CRA are unavailable prerequisites tracked in #602. Dispatch is default-off; the worker source selection defaults to OAG. This packet is local ownership/dispatch acceptance with inert effects, not financial-source or production acceptance.

`python docs/admin/implementation/batch10-mappings-evidence/verify_package.py` performs a read-only check of the complete current receipt inventory, executed source hashes, archived generators, raw logs and nonempty JUnit results. It also works under `python -O`; it writes no verdict. Run `pytest backend/tests/test_batch10_etl_mappings_receipts.py` for actual copied-package source/output/generator/exit/empty tampering and inherited-verdict preservation controls in both modes. test_batch10_etl_mappings_package_guards.py adds the8 boolean-schema, duplicate/pruned-coverage and hidden JUnit failure controls reproduced by the independent reviewer.

Four current execution receipts bind the final executable source: 519 dispatch/native/admin controls and 275 legacy/bootstrap controls on each of Python3.13.9/SQLAlchemy2.0.54 and Python3.12.14/SQLAlchemy2.0.23. PostgreSQL17.11 is isolated on author-owned loopback ports55522/55485. Current logs are gzip archives of the exact raw bytes; `raw_log_sha256` binds their decompressed content. Original receipts remain unchanged in history/. Portable receipt source inventories exclude unrelated tracked documentation/frontend files, while retaining every backend/ETL Python source, fixture and migration consumed by these cohorts.

history-index.json labels every earlier root execution explicitly historical/superseded. The final pinned-base mapping control produced six intended 503-versus-202 failures and two preserved OAG passes with the same inert real-CLI fixture. Its schema prerequisite is the additive candidate schema, because old constraints alone would prevent exercise of the old API mapping behavior. The baseline archive is the actual pinned commit, and its dispatch/CLI/helper bytes were verified against Git. Eight independent-review regression cases subsequently produced8red→8green. Cold actual Python import controls then exposed missing shared native CLI scope; the unchanged fail-closed acceptance control went red→green after readiness repair. Two original OAG failed-receipt controls exposed a compatibility issue; all originals are unchanged and the final519 cohort passes them.

Every completed receipt uses exact durable command/domain/token/generation/acknowledged job identity and exact `seeding_claim_id`. New mappings require that tag for every terminal receipt. For accepted historical OAG FAILED/COMPLETED_WITH_ERRORS receipts only, an absent key may coexist with exact durable ownership/job proof; explicit null/empty/wrong tags still refuse. Such a receipt reports failure only.

The adapter executes the actual native CLI with a bounded loader seam and restores its session/loader globals. A missing per-source handler disables that source; an unavailable shared CLI/config/audit-scope prerequisite disables all sources before acceptance. Death, expired lease, duplicate invocation, malformed identities/observations and lost acknowledgments never free uncertain ownership. Retained ownership in one domain permits independently owned domains to progress.

Reviewer archives preserve actual independent Spec/Standards/adversarial generators, controls, receipts and raw output. Final committed-package replays and source/commit readback are written externally after publication so that no appended repository receipt can change the corpus it certifies. Final handoff links those locations. Warm-cache handler checks alone were insufficient; cold Python module discovery is part of this acceptance.

The selection includes all original dispatch/API/native exclusion cohorts, complete new upgrade/downgrade/re-upgrade/grant/RLS/history checks, and full legacy/bootstrap ownership/session/receipt/fixture-safety cohorts. The historical opt-in Batch7/Batch8 migration scripts expecting the pre-Batch9 head are not this current-schema acceptance and were not run. No frontend changes are needed: existing controls render API source availability. Deployed UI/role/operator acceptance, every-writer fencing, production reconciliation and activation remain pending under #554/#583. Hosted run38014890047 remains tied to its historical tested commit; it does not certify this change.

The initial manifest/verifier bytes are preserved in history/ and explicitly superseded by publication-history.json. The canonical manifest is a current publication index, regenerated by revise_package.py after this verifier repair; the four original execution receipts are unchanged. The appended metadata guard tests are separately replayed against the final published corpus and do not add cases to the earlier ownership cohorts.
