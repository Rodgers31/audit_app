# Scoped writer and loader transfer reduction (#481)

Base: `77a68925756ade06e06f31ee4347e992e772ace0`. This slice changes two ingestion query paths. It does not establish a share of historical Supabase usage or Free-plan headroom. No provider, production database, workflow, deployment or ingestion operation was performed.

## Changes and preserved boundaries

The economic writer resolves each distinct source URL once per invocation. Existing sources select only ID, country ID, publisher and URL, including all identity fields used by receipt association. Publisher declarations remain ordered; undeclared records preserve the stored publisher. Existing metadata, title and acquisition fields are not rewritten. New sources enter the invocation cache only after their flush succeeds. Duplicate URLs still raise; the caller owns transaction rollback. No cache survives into a later invocation.

The audits loader projects existing Audit rows to the twelve identity/comparison/provenance fields it actually uses. Both the batched snapshot and the confirming lookup use the same projection. Existing management responses, recommended actions and other omitted columns remain stored. Duplicate detection, confirming a snapshot miss, fresh-extraction handling, actual inserts/updates, source scoping and the publication gate remain active.

**Full Extraction JSON remains selected.** `source_hash_of` hashes its entire canonical payload, including keys not rendered publicly. Dropping those keys would change stored source hashes. This change introduces no completed-load shortcut: changed payloads are loaded and missing Audit rows are repaired on the next run. Homepage/budget handlers, cache behavior, financial formulas and source acquisition are outside this slice.

## Executed local measurements

The actual writers/loaders ran against the existing isolated SQLite ORM fixture. The probe replayed their SELECTs on that same owned connection and summed UTF-8 string lengths of raw DBAPI values, including stored JSON encoding. These are **selected-value byte estimates**, excluding protocol, TLS, pooler, connection and provider accounting. They are not packet captures, production averages or billed savings.

| Controlled operation | Before queries / rows / bytes | After queries / rows / bytes |
| --- | ---: | ---: |
| Economic writer: 20 records, two existing sources with 64 KiB retained metadata each | 20 / 20 / 1,315,360 | 2 / 2 / 98 |
| Economic writer: 20 records, two new sources | 20 / 18 / 3,240 | 2 / 0 / 0 |
| Unchanged Audit rerun: two rows with 64 KiB action and response text each | 1 / 2 / 263,344 | 1 / 2 / 974 |
| Same Audit fixture, forced snapshot misses confirmed against existing rows | 3 / 4 / 526,688 | 3 / 4 / 1,948 |
| Complete Extraction payloads for each Audit fixture | 1 / 2 / 131,689 | 1 / 2 / 131,689 |

The fixtures first assert writer results, source preservation, sourced zero, exact complete Audit snapshots and no duplicate facts. Byte/query limits follow those assertions. The final new tests executed against the original base production function bodies loaded **in memory**, without changing repository files: **5 failed, 4 passed**. Failures were the expected source-query and unused-column transfer guards. The behavior controls passed on the baseline. The changed code passes all nine.

Additional controls execute ordered publisher declarations, undeclared preservation, ambiguous source refusal, savepoint rollback, an actual injected fact INSERT failure for existing/new sources, fresh invocation re-resolution, changed complete payload hashes and missing-row repair. Original loader suites exercise duplicate audits, a row arriving after the snapshot, fresh rows, multiple documents, source/citation/provenance rules, county attribution, re-extraction preservation and partial recovery. Receipt suites retain actual acquisition trust and association checks.

## Reproduction and results

Use the existing backend Python environment and an isolated checkout without `.env` files. The author launcher supplied a new allowlisted environment: dotenv disabled, an inert SQLite URL before application imports, seeder/warmup false, Redis empty, testing enabled and no inherited credentials/destinations. Application lifespan was not run. The repository's `db_session` supplied the actual in-memory SQLite database.

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
DATABASE_URL=sqlite:////tmp/audit-free-egress-inert.sqlite \
AUTO_SEEDER_ENABLED=false AUTO_WARMUP_ENABLED=false \
TESTING=true ENVIRONMENT=testing REDIS_URL='' \
python -m pytest \
  backend/tests/test_ingestion_query_transfer.py \
  backend/tests/test_audits_loader_roundtrips.py \
  backend/tests/test_blue_book_loader.py \
  backend/tests/test_audit_loader_county_entities.py \
  backend/tests/test_county_volume_loading.py \
  backend/tests/test_extraction_recovery.py \
  backend/tests/test_extraction_preservation.py \
  backend/tests/test_economic_source_ownership.py \
  backend/tests/test_response_receipts.py \
  backend/tests/test_receipt_ingress_trust.py \
  backend/tests/test_oag_project_evidence.py -q -s --tb=short -rs
```

Author result: **221 passed, 5 skipped, 3 existing warnings in 5.47s**. Five receipt tests require an explicitly assigned disposable PostgreSQL URL; that lane was not executed. SQLite does not establish PostgreSQL/provider billing or operational acceptance. Exact commands, allowlisted environment, source hashes, baseline launcher and raw outputs are retained externally under `REMAINING_FREE_EGRESS_IMPLEMENTATION`.

## Remaining Free-plan acceptance

#481 remains open. Verify the deployed query version, then measure provider egress deltas with ordinary API/ingestion/deployment timestamps over at least seven representative days. The existing 120 MB/day planning target is total uncached traffic, including any private receipt downloads; it is not an additional storage allowance. Storage pilot/recovery readbacks and any social workload need explicit budgets. Retained raw source objects have a separate storage allowance and recovery/retention requirements.

The original investigation's cumulative query counters cannot identify these paths' current billing share. Reduced selected bytes and a quiet visitor count do not establish that the organization can safely return to Free. No billing downgrade, schedule change, evidence deletion, cache toggle or publication shortcut is part of this implementation.
