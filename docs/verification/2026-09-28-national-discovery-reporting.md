# National discovery failure reporting — verification

Implementation: `232f5ca1e8f39a2a0b9c2cb8ac8ea9caf8eb1af1`, based on main `1d5fa9f664b16d40edfb1171aa9f8782b5ec2a71`. Addresses #369; diagnostic follow-up for #347. No production seed or data change.

## Executed evidence

The worker observed the full-domain regression fail before correction: discovery raised while a known document processed successfully, but the result contained no discovery error. The corrected result records discovery status/counts/errors, permits known-document processing, and lets existing CLI persistence report COMPLETED_WITH_ERRORS. Successful empty discovery is distinct from failure, partial discovery and intentional budget deferral. Freshness checks validate the latest discovery receipt, including tied jobs and absence of a receipt.

Worker tests: 290 passed across audit domain, CLI budget, staleness, hollow-run, OAG review/county/volume/coverage, inflation reconciliation/monthly, and row-count suites. Coordinator ran the same 11 files on the full combined integration `0f6fa11` (which also includes the citation/publication changes): 290 passed, five dependency/fixture warnings. Independent verification executed direct discovery and freshness calls with synthetic upstream failures, mixed success, malformed media, negative/bool/missing counts, newer partial/tied missing receipts and budget deferral; expected failed/partial/WARN outcomes held. Eight selected full-domain tests also passed independently.

Tests used PYTHON_DOTENV_DISABLED=1, isolated SQLite DATABASE_URL, REDIS_URL='', TESTING=true, AUTO_SEEDER_ENABLED=false and AUTO_WARMUP_ENABLED=false. No production environment was loaded. The code still refuses partial source extraction and unreconciled replacement proposals.

## Inflation incident remains unresolved

Read-only Actions logs show 15 inflation rows on September 22–24 (runs 35679503870, 35810411856, 35947298790) and 11 on September 28 (36370404355), but do not identify the missing four rows. No baseline was reset and no removed identities were guessed.

The bounded diagnostic in [inflation reconciliation](2026-09-28-credibility/inflation-census-reconciliation.md) still requires authorized SELECT-only production access: at most 20 economic jobs, 12 census jobs and 40 current inflation rows, with an eight-second statement timeout and rollback. If historical jobs lack row identities or deletion receipts, a dated pre-loss snapshot is needed. Current rows alone cannot establish what disappeared. This diagnostic was not executed against production.

## Release acceptance

Before closing #369, verify a deployed audits job's discovery receipt, errors, status, source_mode and freshness outcome. Historic jobs without the new receipt deliberately warn until a new run supplies evidence. Keep #347 open for identity/source reconciliation and document 2392's refused 335 retirements/two revisions. Keep #234 open for controlled newer-volume ingestion, source/year/institution reconciliation and public API/browser refresh acceptance. No production rollout is included in this PR.
