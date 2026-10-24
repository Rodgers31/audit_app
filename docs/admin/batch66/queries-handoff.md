# B66 queries author handoff

Scope: #481 / #774 compact endpoint reads. Frozen base: `924f1a4f27e1952f97d2291d8878d88603132237`. Author chat: `01a16c44-b483-7c51-974e-1cffef9f5833`. Branch: `codex/b66-compact-endpoint-reads`. Owned managed worktree: `/Users/roger/.codex/worktrees/b66-queries/audit_app`.

## Implementation

`backend/main.py`, only pipeline-health helpers: `_pipeline_health_database_stats` executes one SQL statement with ten scalar results, replacing seven scalar count terminals and three full-model first-row terminals. Count terminals already returned scalars; this change does not claim they formerly transferred table rows. The statement retains national existence, latest population year, latest economic date/year, all counts, and distinct debt-category semantics. Ordered scalar subqueries preserve PostgreSQL DESC NULL-first behavior, unlike MAX; counting the distinct-category subquery preserves the NULL category, unlike COUNT(DISTINCT category). One PostgreSQL statement provides a consistent statement snapshot under READ COMMITTED.

The existing worker-owned session, dedicated physical executor/semaphore, shielded cancellation, session-close error handling, cache/single-flight, 30s TTL and transient-failure behavior remain intact. A failed execute/materialization/session close clears database data and emits an error. No partial success or fabricated empty database is returned.

`backend/social/media/service.py`, only `library`: count remains scalar and page read selects twelve Asset DTO fields plus Upload identity/version. Plain SQLAlchemy rows reuse the unchanged `_dto` and cannot deferred-load ORM columns. The joined upload primary key distinguishes an absent upload (version 1) from an existing invalid zero/NULL version (validation failure). Ready/deleted/MIME restrictions, escaped search, kind, UUID tie-break ordering, default20/max50, count/page/has_more and complete DTO remain unchanged. Preview, storage identity/fences, inspection, write/quota/retention/recovery/authorization paths are untouched.

Changed tests: `backend/tests/test_compact_endpoint_reads.py` and narrowly adapted `backend/tests/test_pipeline_health_worker.py`. The worker probe now implements execute/one; materialization failure replaces the obsolete fourth-query partial-read failure. Real SQL worker expectation is one statement; all ownership/cancellation/cache assertions remain.

## Evidence and reproduction

External evidence root (not committed): `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_66_LAUNCH/queries/`. Keep `STATUS.json`, `DEPENDENCIES.md`, resource manifest, raw failures and source-bound receipts there. `run_tests.py` records command/runtime/inert environment, source hashes before/after, raw output/JUnit hashes, exact testcase identities and child exit; receipts are read back after writing. Runtime Python3.13.9 from the existing supported executable, not root3.14/backend3.9. No dependency install, production environment, credentials or provider database was used.

Owned PostgreSQL17.11 uses cached image `postgres:17` (`sha256:2d2b8998d310…`), loopback56971, database `b66_queries`,512MiB/0.5CPU, tmpfs data and no volume. Test opt-in is `B66_QUERY_POSTGRES=1`, not an arbitrary DATABASE_URL. Each case gets an isolated schema containing only needed tables and FK parents, then drops it. The disposable date column is deliberately nullable for historical-shape controls; current mapped schema is NOT changed. Invalid persisted version controls deliberately relax only the owned fixture constraint. These are local semantic tests, not production schema certification.

Targeted command, cwd worktree `backend/`:

```sh
env -i PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp \
  B66_QUERY_POSTGRES=1 DATABASE_URL=sqlite:////tmp/b66-queries-bootstrap.sqlite \
  PYTHONDONTWRITEBYTECODE=1 DISABLE_STARTUP_SEEDING=true \
  /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -m pytest \
  tests/test_compact_endpoint_reads.py tests/test_pipeline_health_worker.py -q
```

Prepare ONLY an owned fixture after checking the port; the author used:

```sh
docker run -d --name b66-queries-pg --memory=512m --cpus=0.5 --pids-limit=128 \
  --publish 127.0.0.1:56971:5432 --env POSTGRES_HOST_AUTH_METHOD=trust \
  --env POSTGRES_DB=b66_queries --tmpfs /var/lib/postgresql/data:rw,size=268435456 \
  postgres:17 -c max_wal_size=64MB -c min_wal_size=32MB -c checkpoint_timeout=30s
```

Wait for owned `pg_isready`; remove this exact container with `docker rm -f -v b66-queries-pg` afterward. Never replace this with a production URL, existing unrelated container or broad prune. Missing opt-in produces explicit PostgreSQL skips; SQLite alone does not satisfy this lane's PostgreSQL evidence.

Retained checkpoints:

- `baseline-01` reproduced media overfetch but had eight fixture import errors; not a clean snapshot proof.
- `baseline-02` reproduced both query defects but ran out of bounded PostgreSQL tmpfs at the final fixture. The original over-broad create-all fixture caused catalog/WAL growth. `candidate-01` then had PostgreSQL setup errors, not a product verdict. Both failures remain retained; the owned container was replaced and fixture table scope narrowed. No memory/CPU budget increase.
- `candidate-02`:66 passed, no skips.
- `baseline-03`: final product-code replay on frozen base,58 cases,31 expected failures/27 passes/zero errors or skips. The failures are SQL count/selected-column assertions and the real PostgreSQL interstatement concurrent-commit inconsistency. Candidate source was restored byte-for-byte afterward; no branch switch or primary checkout mutation.
- `candidate-03`:74 passed, zero skips, including differential output, empty/missing/invalid uploads, page beyond end, search escaping/injection/Unicode controls, latest-year0, nullable date, distinct NULL, database failure, real PostgreSQL concurrent commit, worker cancellation/ownership/cache/error/remote-close cases. Subsequent final source/collection replay is recorded below.
- `affected-01`:295 passed,3 pre-existing PostgreSQL cleanup skips,4 warnings. Exact command/node inventory in receipt. Cohort includes public response cache/economic status/public query transfer/county query volume/audit payload and media service/API/object identity/management/cleanup/retained recovery/legacy recovery/reconciliation/owned writes/target safety/payload retirement. The three skipped controls require the separate assigned62124 fixture; they were not run against a mismatched target or represented as passed.
- Critical affected-file flake8 (`--select=E9,F63,F7,F82`) and `git diff --check`: clean.

Final collection correction: the PG-only concurrent-commit test is now parameterized solely to PostgreSQL, removing the SQLite early-return label. Product/worker bytes are unchanged. `final-baseline-01`:57 cases,31 expected failures/26 passes,zero errors/skips on actual frozen product source. `final-targeted-01`:73 passed,zero skips (57 new+16 worker). Both independent reviewers supplied final collection addenda for the exact source. Historical74-case receipts remain preserved under their original hashes.

## Independent executable reviews

Two independent reviewers executed current code and hostile controls, without hosted bots or candidate edits. Full commands, hashes and preserved invalid-reviewer-fixture failures are in `review-spec/` and `review-standards/`.

Spec: full targeted74-case cohort plus six independent PostgreSQL controls. Complete baseline/candidate snapshot and DTO equality; null/zero values, malformed stored data, escaped filters, pages, actual selected columns and no lazy loads. No validated defect. A synthetic eight-asset fixture, page_size2,65,536-character unused metadata per asset and one upload selected131,896→352 UTF-8 value-proxy bytes,2→2queries,50→14page columns. Synthetic pipeline fixture selected131,212→35 value-proxy bytes,10→1queries,ten candidate scalar columns. These are replayed selected-value representations, **not protocol bytes, billed egress, production latency or whole-table transfer**.

Standards/adversarial:54 existing worker/auth/API/object-identity/legacy-recovery cases;56 new compact cases with two then-parameterized concurrency nodes deliberately deselected to avoid shared advisory-key contention with Spec. Seven independent PostgreSQL probe families execute exact frozen function ASTs and current functions: empty/zero/NULL full equality, actual table-lock timeout/fail-closed/recovery, UUID-zero joined upload, zero/negative/NULL stored upload-version refusal, missing-upload version1, bounded SQL columns and no ORM/lazy loads. No hard standard breach, actionable smell or validated candidate defect.

## Remote reachability and cross-lane dependency

Remote separation is **diagnosed but unimplemented**. The legacy route still awaits five parallel HEADs,8s per HTTP operation, before returning. That timeout does not establish a total wall-clock route bound. The existing client uses a boolean reachable field and would label unknown as Down or cached success as current. No safe paired client is delivered here.

`DEPENDENCIES.md` supplies an explicitly unimplemented additive version2 proposal: preserve legacy route by default, opt in to local status scope, explicit per-source/aggregate observation states, original checked timestamps/current ages, unknown/null versus failure, stale labels, one bounded demand-triggered shared refresh, whole-refresh deadline/cancellation/client closure and no scheduler. Performance's independent dependency note agrees that the current client consumes no such fields. Coordinator must review/integrate/test any paired contract separately. This projection PR adds no fields/routes/flags/tasks or remote caching.

## Production, safety and acceptance limits

No production/provider database, representative active workload, browser measurements, wire/billed egress, latency gain or Free capacity acceptance was obtained. B65's empty production library cannot prove a filled-library latency/savings benefit: zero rows do not transfer the excluded values. There is no causal attribution from this local SQL work to FCP/LCP. Existing accepted financial/citation/qualification projections are untouched.

Publishing/uploads/native processing/supervision/automatic generation stay OFF by unchanged source/config; this author did not re-attest production flags. Repository Actions stay OFF; no workflow/dispatch/bot review/plan/budget/DNS/OAuth/access/storage-retention/secret/production write/merge/deploy change was made. Author publication controls use fresh GitHub API state plus explicitly retained coordinator Chrome personal-review/Preview-Tracking evidence; exact dates/bases are in control receipts. Existing Vercel$1PauseOn/export custody/Oct28 deadline unchanged.

This is one scoped draft PR on frozen main. It does not close #481/#774/#699 or certify complete admin/operational acceptance. Full release/hosted/deployed gates remain coordinator work; no author merge/deployment authorized.

Rollback: revert this scoped PR to restore legacy SQL selection. No schema/data/config migration or external side effect needs reversal. Retain the open author worktree/branch/evidence; owned fixture/process/port cleanup is recorded in RESOURCE_MANIFEST.json.
