# Writer inventory addendum: CRA recommendation domain (#602)

Addendum only. The historical inventories
`batch8-exclusion-evidence/writer-inventory.md` and
`batch9-legacy-etl-evidence/writer-inventory.md` are unchanged and keep their
original receipts. Base: accepted main `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`.
Executed search: `writer-callsite-search-602.txt` (this directory).

## New effect domain

`cra` writes exactly two shared tables: one `source_documents` row
(publisher `Commission on Revenue Allocation`, the single reviewed URL, metadata
`artifact_sha256`) and one `extractions` row bound to it (`extractor
cra_table_5_2_v1`, page 39, the four Table 5.2 recommendations in raw KES). It
writes no budget, revenue, indicator or audit table and no reference row
(`countries` must already exist; bootstrap stays #603's).

## Every writer that can reach those rows

| Writer | Claim held before effects | CRA interaction |
|---|---|---|
| Native CLI `seed --domain cra` (and `--all` only when `SEED_CRA_INGESTION_ENABLED=true`) | `cra` native claim via `seeding.exclusion.enter_domain` | The writer itself; re-proves claim, observation shape, run window and live execution lock on its own transaction (`writer.require_ownership`). |
| Dedicated dispatch worker → adapter → CLI (`cra` → `cra` mapping, migration `e602b11a0001`) | `cra` dispatch claim entered once by `_enter_dispatch` | Same writer; dispatch observation must carry exactly the correlated command/token. |
| Legacy loader (`etl.database_loader` public writes, manual sessions, backfill/worker/scheduler) | All `LEGACY_DOMAINS`, now including `cra` (lexical order, before any loader effect) | Legacy writes shared `source_documents`; with `cra` enrolled it cannot run while CRA owns the domain, and CRA cannot start while legacy owns it. Proven by `backend/tests/test_batch11_cra_legacy_ownership.py` (red on the base set). |
| Other native domain writers (`seeding/domains/*/writer.py`, extractors, `fetch_documents.py`, `response_receipts.py`) | Their own domain claims | Write their own publisher/URL rows. CRA reads only rows matching its exact publisher + URL + artifact hash; an unexpected duplicate is refused as ambiguous, never merged. |
| `etl/parliament_pipeline.py` (`PARLIAMENT_PIPELINE_ENABLED` default off) | None (Batch 8 row 4b) | Disjoint publisher (`Kenya Parliament Digital Library`) and URL; cannot create or alter the CRA identity. Unchanged prerequisite of the Batch 8 quiescence inventory. |
| Bootstrap (`backend/bootstrap.py`) | #603 admission | Writes reference/source rows for its own fixtures; CRA does not depend on or alter them. Owned by #603. |
| Maintenance scripts (`backend/scripts/*`, `tools/verify_sourced_record_cleanup.py`) | None | Operator-run, outside the seam; covered by the Batch 8 quiescence inventory and #583. |

## Signed recovery

`seeding/reconciliation.py` maps `SOURCE_DOMAINS` dynamically, so a retained
`cra` dispatch claim reconciles through the same signed plan/apply path; the
mapped reconciliation cohort parametrizes over `SOURCE_DOMAINS` and therefore
executes `cra` cases (receipts in the handoff). No recovery check was changed.

## Not covered here

Production pooler/capacity evidence and activation stay with #583; deployed
operator acceptance stays with #554.
