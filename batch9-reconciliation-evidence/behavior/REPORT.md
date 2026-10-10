Independent behavior verification completed on owned loopback PostgreSQL fixtures only.

The same 91 executed checks passed separately on Python 3.12.15 / SQLAlchemy 2.0.23 (`min-final-stable.json`) and Python 3.13.9 / SQLAlchemy 2.0.46 (`current-final-stable.json`), with zero skips and no source drift. These are overlapping selections, not 182 unique tests. Both receipts identify the exact command, runtime, environment, dependency HEAD, product/fixture hashes and unchanged generator bytes, then read the recorded verdict/hash back from disk.

Confirmed and repaired findings:
- `min-second.json` recorded successful planning over an explicit null legacy ownership tag. The author repaired key-presence handling; both final runs refuse it.
- `min-stable.json` and `min-valid-red-rollback.json` reproduce a valid apply failure on SQLAlchemy 2.0.23: ORM-annotated Table DML confused the ingestion `metadata` column with declarative `MetaData`. The latter receipt also proves claim/observation/audit rollback. Pure Table-column repair passes both final runtimes.

Executed persistence controls:
- Malformed direct request/evidence/policy/plan objects; bool/NaN/infinity; absent/unsigned/empty/self-submitted policy; Unicode blank operator/artifact fields; stale/future/mismatched artifacts; live/uncertain signed writer states; wrong version/hash/backend/time and elapsed-time fence-release policy all refuse.
- A genuinely new TCP session is refused by closed database admission. A separate OS process trying to reopen admission times out while the same pg_database row is locked FOR SHARE.
- Valid native reconciliation preserves all original acquired/entered/entry/returned/job evidence and a subsequent native enter_domain/acknowledge/close path succeeds.
- Valid truly untagged legacy RUNNING observations receive FAILED status plus one audit, preserve preexisting metadata/errors and invent no claim.
- A public effect-table change after the signed census refuses apply and retains the RUNNING observation/claim with no audit.
- Actual `python -m seeding.reconcile_operator` backend termination before apply returns uncertain and retains ownership. Actual SIGKILL after planning followed by restart refuses the old backend plan.
- Actual backend termination during an UPDATE paused by an owned pg_sleep trigger returns uncertain; claim, job and audit mutations all roll back together.
- Explicitly injected report-boundary loss wraps real operator.main and real apply_plan, exiting only after the actual commit succeeds and before reporting. Independent readback finds one durable audit/released claim/FAILED job; a new operator session refuses the old plan. This injected reporting boundary is not runtime acquisition or exclusion proof.

Earlier attempts remain honestly classified:
- `min-first.json`: FAILED verifier fixture setup after 69 checks (SQLAlchemy interpreted a literal JSON colon as a bind parameter). Original generator retained; v2 fixed only that fixture.
- `min-second.json`: FAILED; null-tag finding plus product source drift invalidated the subsequent plan. The finding remains a red receipt, not acceptance evidence.
- `min-third.json`: FAILED due product source drift, after confirming repaired null-tag refusal. No acceptance claim.
- `min-stable.json` / `min-valid-red-rollback.json`: FAILED valid-operation compatibility controls, with stable product source.
- `min-fixed.json` / `current-fixed.json`: PASSED earlier overlapping 82-check selection.
- `min-final.json` / `current-final.json`: PASSED 91-check selection; the author subsequently added tests to the helper file. Finalization guard refused stale helper attribution (`finalize-first-failed.json`), then unchanged v6 verifier re-ran with the current helper as `min-final-live.json` / `current-final-live.json`. Product bytes did not change during that repetition; this delta is fixture/test source attribution, not changed product behavior.
- `min-final-live.json` / `current-final-live.json`: PASSED repeated 91-check selection. The author then removed an unused product import and added dispatch assertions/removed unused test imports. Finalization again refused post-run source attribution (`finalize-second-failed.json`); the unchanged v6 verifier reran both runtimes as `min-final-stable.json` / `current-final-stable.json`. Finalization v3 compares these live sources and records database cleanup.

Limitations: these fixtures do not certify production provider/pooler behavior, deployed writer inventory, actual host/scheduler/effects attestations, operational fence feasibility, or external role admission control. Parent separately owns actual native CLI/worker/adapter process acquisition races, migration/RLS/grants and integration checks. No financial/provider/storage/API calls were made. No GitHub writes, commits or pushes were made by this verifier. All verifier-owned databases/processes were cleaned; temporary local policy/IO files were removed while receipts and immutable generators remain.

Generated by `batch9-reconciliation-evidence/behavior/finalize_behavior_v3.py`, SHA256 `132b1e2dd8d3043e123bc55ea53fdcdb146a540f2f463e5ebc40f92b0ad44caf`; source provenance in `final-summary.json`.
