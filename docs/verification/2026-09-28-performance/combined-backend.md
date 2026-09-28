# Combined backend performance verification

## Copilot review follow-up

The coordinator reran the original combined set plus
`test_audit_attribution_contract.py`, `test_review_findings_pr135.py`,
`test_unaccounted_reader_public_contract.py`, and
`test_federal_review_cache.py` after the review fixes: **285 passed**, four
existing warnings. This includes the five fixture assertions reproduced red
at the reviewed PR head, generation-fencing races, and the batched extraction
query-count regression. See `federal-review.md` and the updated audit receipt
for individual red/green evidence. Render Docker selection was verified from
its live settings; the cache receipt distinguishes it from the alternate
image-publishing workflow. The remaining cold-miss event-loop work is tracked
in [#363](https://github.com/Rodgers31/audit_app/issues/363).

The commands and 251-test result below record the initial consolidation.

Base: `37c6c37c565b3190ae0f72fb5fa895daf68abe24`.

The audit projection, county projection, and cache/runtime sessions were
combined on `codex/supabase-query-performance`. Their detailed receipts are
in this directory: `audit-query-projections.md`, `county-query.md`, and
`cache-runtime.md`.

## Coordinator checks

On 2026-09-28, the combined branch passed **251 tests** across these files:

```text
test_audit_query_payload.py
test_county_query_volume.py
test_public_response_cache.py
test_audit_dashboard.py
test_audit_dashboard_absence_and_labels.py
test_audit_findings_source_url.py
test_audit_citations_conflicts.py
test_audit_headline_derived.py
test_freshness_publication_evidence.py
test_audits_publication_gate.py
test_data_freshness.py
test_model_responses_are_cacheable.py
test_cache_invalidation_endpoint.py
test_cache_key_is_build_scoped.py
test_health_detailed_reports_cache.py
test_cache_namespace_pinning_warning.py
test_failures_are_not_cached_long.py
test_router_cache_isolation.py
```

Run from `backend/` using Python 3.13 and `python -m pytest` with the files
above, `-q --maxfail=5`, and this isolated environment:

```sh
PYTHON_DOTENV_DISABLED=1
DATABASE_URL=sqlite:////tmp/audit-performance-combined.sqlite
REDIS_URL=''
AUTO_SEEDER_ENABLED=false
AUTO_WARMUP_ENABLED=false
TESTING=true
```

Four warnings concern existing SQLAlchemy deprecations and the optional
Levenshtein accelerator. The two query sessions also exercised their changed
queries against a disposable local PostgreSQL 17 container, including the
historical string-encoded extraction fallback. The county session compared
complete responses before and after its change, excluding generated timestamps.

`git diff --check` passed. Local critical flake8 could not run because the
shared virtual environment does not include flake8; the repository CI remains
responsible for that gate.

## Scope and limits

- All measured payload reductions are fixture measurements, not a prediction
  of the production bill. No Supabase production query or deployment was used
  for these tests.
- Publication gates, response fields, source evidence, and missing-data
  behavior remain covered. The 30-second pipeline-health cache also addresses
  issue #290.
- The memory byte limit and health counters apply to each cache instance;
  they are not a process-wide memory limit or a durable request-count metric.
- Each process has its own fallback cache when Redis is absent. Cross-process
  cache sharing requires Redis. Pipeline-health still performs blocking work
  on a cold cache miss; this change reduces repeated work.
- Newly discovered data defects are tracked separately: #358 (sourced zero
  becomes null in the federal findings total) and #359 (county audit-list
  citation omits its stored page). They are not fixed by these performance
  changes.
