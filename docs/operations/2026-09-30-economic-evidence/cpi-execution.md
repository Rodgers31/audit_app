# CPI publication prevention and correction rehearsal — 30 September 2026

This implements prevention for #380 and prepares a correction for **only** economic indicator IDs 67, 86 and 87. No production correction, live seed, cache refresh, source retirement, Actions run or deployment is authorized by this development work. The prepared execution receipt is synthetic; it is not a current production plan.

## Source and measure

KNBS January 2025 PDF page 2, Table 1, Overall CPI column: January 142.68, December 141.66; base February 2019=100. The December 2024 PDF page 2 independently gives December 141.66. Both captured PDFs were visually reviewed again and their bytes are checked on every tool invocation. January SHA-256 is `ca9654579a2a0b8d14301de005cea70f1db2943c8d40cb111be3b8b1e0ccd44d`; December SHA-256 is `75e6f741704874180edd8378ec6219c5920f15082496e6bf47aa00e0f7570614`.

`cpi-correction-proposal.json` retains the full captured preimages and exact proposed replacements. Its approved source-shaped definition is pinned at SHA-256 `543e1ad07a7c30081c93b51b74450c22883611656ec03ff2b6c5dd62dfa50722`. A changed manifest requires renewed source review and a new pin. The new sources also bind the reviewed Table 1 payload digest, so changing both a fact and its extraction cannot reuse the old approval.

| ID | Exact stored type | Date | Before | Proposed | Source ref |
| --- | --- | --- | --- | --- | --- |
| 67 | cpi | 2025-01-31 | 143.08 | 142.68 | knbs_jan2025 |
| 86 | CPI | 2025-01-31 | 143.08 | 142.68 | knbs_jan2025 |
| 87 | CPI | 2024-12-31 | 142.47 | 141.66 | knbs_dec2024 |

IDs, types, dates, scope, original confidence and creation timestamps remain. The index unit is `index_2019_02_100`, with exact document/page/hash/extraction lineage and ACTUAL basis. Proposed `publishable=true` is contingent on all execution checks. Sources 1715 and 1823 are preserved byte for byte; 1823 remains the shared debt placeholder used by population79. The correction never normalizes or deduplicates CPI case/type identities, rescales values or changes annual inflation.

## Implemented prevention

The unsupported CPI fixture supplement is retired. The fetcher also excludes CPI from remotely configured supplemental fixtures and records an error; the dedicated writer refuses direct CPI inputs before changing any source or fact. This deliberately retires its CPI publication role instead of presenting replacement literals as live ingestion. The independently based annual World Bank `cpi_index` continues through the existing domain.

Both observation readers (`/economic/indicators` and county profile indicators) use the shared economic gate in `services/publication_gate.py`. CPI requires explicit publication approval, no quarantine/bootstrap marker, finite nonnegative value, national scope, exact February 2019 monthly index semantics, an available KNBS PDF source in Kenya, document hashes, matching extraction/page, reviewed table payload digest and matching observation value. Unpublished rows remain stored. List shape is unchanged; `X-Economic-Withheld-Count` and `X-Economic-Withheld-Reasons` describe omissions in the examined query prefix. County profiles add equivalent count/notes. Filtering occurs before the public limit. The API exposes source URL, page, hash, measure and base for allowed rows.

`publication_status=source_bound` means stored source evidence matches; the request does not refetch the publisher PDF. Other economic measures keep their existing policy and are marked `not_checked_here`. This work does not establish their independent source acceptance. No direct frontend CPI consumer was found in the full frontend tree search; the directly measured impact is API publication.

Bootstrap/web paths are already retired and retain their previous regressions. The legacy root ETL loader can insert another CPI row, but cannot overwrite the corrected rows in the exercised path; its inserted row defaults to unpublished and the shared reader gate withholds it. This is a conditional synthetic probe, not a claim that the legacy loader currently runs in production. Seeder diagnostics return counts/vintages rather than CPI values; the national summary and budget strip read named inflation/growth series, not CPI index levels.

## Execution and refusal contract

Use `scripts/verification/cpi_source_correction.py`. It reuses the existing #379 guarded correction's canonical JSON hashing, exclusive/fsynced receipt writing and explicit PostgreSQL/TLS connection handling without invoking that OAG executor or changing its files. This dependency should remain available when the coordinator consolidates the sessions.

The sole database input is the explicitly supplied `CPI_CORRECTION_DATABASE_URL`. There is no dotenv or default DATABASE_URL fallback. Remote TCP requires the existing documented TLS modes. CLI exceptions omit driver messages/DSNs. The direct `run()` function enforces the same mode, dialect, plan-digest and receipt requirements.

Preparation and default apply/recovery start `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`, verify `transaction_read_only=on`, set statement timeout 8 seconds and lock timeout 2 seconds, prove that INSERT is refused with SQLSTATE25006 under a savepoint, and roll back. Reflected full row/source/country preimages preserve additional database columns absent from the ORM. Exact type/date/scope duplicate probes refuse PostgreSQL NULL-scope duplicates. Existing source URL and table-page identities must be unique and match the exact reviewed publisher, title, URL, MD5, SHA-256 and payload. Conflicts are refused, never relabelled or overwritten.

Full-image and payload comparisons use canonical encoded JSON, including retained columns: JSON `true` differs from `1`, and `67` differs from `67.0`. Forward correction checks the full allocated/reused source and extraction images again after observation updates. Recovery checks the original shared sources, country and retained allocated evidence again after inverse updates, before commit. Trigger-induced context drift rolls back every change; a durable intent file alone still does not establish a committed operation.

An explicitly authorized commit takes short table locks protecting the three-row/source/extraction identity probes against concurrent inserts/writers, then rebuilds the canonical plan inside that transaction and compares its digest/full preimages. New source/extraction IDs are returned by PostgreSQL; symbolic refs resolve only to the actual allocated/reused records. It writes an exclusive/fsynced intent receipt **before DML**, verifies all corrected full images and the actual shared reader gate, and writes `<intent>.resolved.json` with the full concrete after-images and source/extraction records **before COMMIT**. Failure of either durable write, SQL, source checks, or final checks rolls back all DML. Sequences may have gaps after refusal; no fact correction is partially committed.

The resolved receipt says `prepared_before_commit_check_database_for_outcome`, since a lost commit acknowledgement cannot be certified by a precommit file. The CLI reports `committed` only after commit returns. Do not infer completion from the presence of either file.

## Commands for a separately authorized operator

First deploy the prevention code and retired fixture; preserve both exact PDF files and the execution receipts. Supply the dedicated connection variable through the approved secure mechanism; do not put credentials in logs or command history. Use absolute artifact paths for every argument. `<...>` below denotes a reviewed path/value, not a credential recommendation.

```sh
python scripts/verification/cpi_source_correction.py \
  --manifest docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json \
  --january-pdf <exact-january-pdf> --december-pdf <exact-december-pdf> \
  --output <new-full-production-plan.json>
```

Have the release owner review the freshly captured full plan and its canonical SHA-256 (`digest(plan)` from the existing correction infrastructure). The committed captured manifest may refuse current drift; that means renewed review, not a bypass or deletion of the mismatched field.

```sh
python scripts/verification/cpi_source_correction.py \
  --manifest docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json \
  --january-pdf <exact-january-pdf> --december-pdf <exact-december-pdf> \
  --plan <reviewed-full-production-plan.json> --expected-sha256 <reviewed-plan-digest> \
  --output <new-readonly-validation.json>
```

Only after separate exact-plan production authorization, add `--commit` and use a new durable intent output. This session grants no such authorization. Code merge approval is insufficient. No workflow, seed, broad cleanup or refresh is involved in these commands.

## Exact recovery

For an uncertain commit, compare the live full rows under default read-only mode with the original plan and the resolved after-images. If they match the before-state, no correction committed; refuse recovery and review a new output path/attempt. If they match the exact resolved after-state, validate the resolved receipt's canonical digest and use `--recovery <intent.resolved.json> --expected-sha256 <resolved-receipt-digest>` in default mode. Any row, duplicate identity, shared source, allocated evidence or country-context drift refuses recovery. A mixed or unknown state requires investigation; do not overwrite it.

A separately authorized recovery adds `--commit --output <new-recovery-intent.json>`. It restores just the three full before-images, including `publishable=false`; the publication gate withholds their unsupported values. Reviewed source/extraction evidence remains archival; shared documents are never deleted or relabelled. Keep the CPI supplement retired throughout recovery. An automatic ingestion run cannot overwrite these rows through the generic domain. A later reapplication requires a new plan accounting for the retained allocated evidence and its new digest.

## Local acceptance and limits

Executable source-shaped regressions cover real HTTP/list/profile readers, legacy fixture/direct writer refusal, finite/zero/absence/base/value/hash/measure/source conflicts and a paired row/extraction drift. Disposable PostgreSQL exercises read-only INSERT refusal, full preimage/unknown-column drift, exact type identities, safe allocations/reuse, commit/recovery, concurrent writer refusal, durable receipt failures and SQL rollback, stored Numeric NaN, six constrained Infinity refusals plus direct reader rejection, actual next domain ingestion, legacy ETL insertion and preservation of the captured 11 annual-average tuples. All database writes in these tests are disposable and synthetic; original selected tuples do not reconstruct original full annual row metadata.

The source artifacts and session-specific red/green/CLI receipts are listed in the external Round 6 Session 1 handoff. #380 remains open through deployed/public source acceptance and separately authorized stored correction; #293 still needs current-version dedicated-job acceptance; #347/#378 still need original historical evidence and later explicitly authorized full pipeline acceptance. Actions remains off.
