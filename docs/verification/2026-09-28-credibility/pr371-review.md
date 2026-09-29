# PR #371 audits scheduler review — 28 September 2026

Base: `ca329fd06a4ac7522e8ed1cd2a54ae1352979e5e`, the PR head reviewed in an isolated worktree. This receipt covers the two Copilot comments on the audits domain only. All source URLs and database rows in the checks below are synthetic; no OAG download or production database access was used.

## Comment 4128223418 — new national document cap

**Valid.** The scheduler sliced three newly discovered URLs before applying the national report filter. A popular or summary report, or a duplicate URL, could consume a slot and hide an eligible Blue Book. It also omitted eligible excess from `deferred_documents`. The correction deduplicates and filters the full candidate list, then enforces three **never-fetched national attempts** in the queue. Each eligible excess URL receives `reason: new_document_cap`. A provisional source row with no verified PDF path and hash still uses one of the three slots on a later run; registration alone cannot bypass the limit. The existing start-budget reason remains distinct.

The synthetic regression supplied a popular report, a summary report, five eligible Blue Books and a duplicate. Against the unmodified PR head, the first run fetched only one eligible URL and the dry run listed only two eligible URLs; the new tests failed accordingly. With the correction, the first run attempts three eligible URLs, records the other two as cap deferrals, and the next run reaches those two. A separate control registers five never-fetched national rows before discovery and confirms the same three-attempt cap applies.

## Comment 4128223434 — interrupted first national fetch

**Valid.** For a new URL, the scheduler previously stamped `last_audit_schedule_attempt_at` only after `fetch_document` returned. The fetcher flushed a new row before downloading, but the CLI rolls that uncommitted row back when a hard `DomainTimeoutError` interrupts the download. The URL then re-enters the next run with no recorded attempt and can repeatedly take the first retry turn.

The correction commits a provisional `FAILED` source row and a scheduled-attempt timestamp before invoking the fetcher. It records the exact discovered URL and dataset, with no file path, hash, HTTP success, or verified timestamp. A file-backed SQLite regression raises `DomainTimeoutError` during the first national fetch, performs the same rollback as the CLI, and opens a new session. The row and timestamp survive; the next run offers the previously unattempted legacy county document before the national retry. Against the unmodified PR head, this test failed because the national row did not survive rollback. The hard timeout still propagates, and document extraction and publication gates are unchanged.

## Checks and limits

The red run on the unmodified PR head: three new focused tests failed (`filter_and_dedupe`, `dry_run_lists`, `first_national_fetch_timeout`). After the fix and the registered-backlog control were added, the focused suite passed: **35 passed**, 4 dependency/deprecation warnings, for `test_audits_domain_county_ingest.py`, `test_national_budget_fetcher.py`, and `test_audit_candidate_filter.py`. The tests ran from `backend` with `PYTHON_DOTENV_DISABLED=1`, a loopback-only `DATABASE_URL`, empty `REDIS_URL`, `TESTING=true`, and automatic seed/warmup disabled. The fixtures use SQLite and fake network/fetch/parser behavior; they do not assert PostgreSQL locking behavior or live OAG discovery completeness.

The source-content and reconciliation decisions remain with their existing guards. This change schedules and records candidate attempts; it does not accept any extracted figure, resolve the national document 2392 refusal, or demonstrate a production ingestion result.
