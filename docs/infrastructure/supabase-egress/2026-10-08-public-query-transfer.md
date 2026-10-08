# Public-query egress investigation and reduction — 8 October 2026

Base: `e9da7c7e7149bddb54eb917cd391f4b67ccd827d`. Issue: #481, which remains open. This slice changes result selection, not financial accounting, stored evidence, publication eligibility, auth, cache TTLs, scheduling, or host configuration. The primary development checkout was left untouched. Actions was independently read as `enabled:false`.

## Existing plan and ownership

The [remediation plan](REMEDIATION_PLAN.md) already covers public summaries, cold reads, ingestion and operating-profile measurements. The separate social workstream merged #487's SQL ingestion statistics and distinct-source lookups. #505 subsequently merged economic writer batching and Audit comparison projections. Those improvements remain in place. Historical full-row query counters are not proof that those fixes failed.

This investigation found remaining overfetch on current main and implements five bounded reductions:

| Surface | Before | After and preserved behavior |
| --- | --- | --- |
| County/national/all-county money flow | Complete BudgetLine models and full/lazy source context | Required accounting columns, batched period/source context, national county IDs only; all accounting cohorts and full source metadata retained |
| County findings page | All rich findings hydrated before Python slicing | SQL count/offset/limit without a status facet; exact Python first-entry fallback/casefold on narrow metadata with a facet, then only page details |
| Basic county audit summary | Complete audits for ten 200-character descriptions | Six metadata fields, display-grade filtering before count/selection, then ten SQL substrings |
| Budget qualification | Complete source/entity/country/period/extraction models | Budget-only identity/context projections and the complete response_receipt member; full source metadata, every receipt observation and all refusal rules retained |
| Source vintage | Complete SourceDocument models | Publication-date JSON member and fetch date; parsing/fallback/timezone/max rules unchanged |

Money-flow reads are mounted in the transparency page/SSR prefetch and county money-flow tab. Budget qualification serves county list/comprehensive/budget and financial verification paths. The paginated/basic endpoints are registered, but the current frontend search did not establish a mounted consumer for their legacy component/hooks. Their production call rate is unknown; they must not be presented as the largest live source of traffic merely because their fixture reduction is large.

## What the production evidence establishes

The dated [dashboard evidence](EVIDENCE.md) identifies Shared Pooler as approximately all recorded daily traffic in the observed Free-cycle interval. This locates the database-to-client leg; storage cleanup or browser-response compression cannot remove those already transferred query results. [Supabase's egress guide](https://supabase.com/docs/guides/platform/manage-your-usage/egress).

Two new bounded, read-only PostgreSQL metadata snapshots at **13:17:31** and **13:31:12 UTC** retained the same statistics reset: **22 April 2026, 20:29:28.245625 UTC**. Among the 25 historically highest-returned-row SELECT shapes, only the internal `pgbouncer.get_auth` counter increased (60 calls/60 rows). No application SELECT in that selected group increased during this interval. This is neither a complete traffic inventory nor proof of zero traffic; it prevents mislabelling six-month cumulative totals as today's load or this billing cycle's usage.

The older full budget shape remained at 1,918 calls/1,052,350 returned rows, identical to the 3 October record. A newer full budget shape stood at 2,469 calls/1,639,154 rows. Identical normalized shapes can have multiple callers. Neither counter assigns historical bytes to a particular Render request, deployment, developer client or ingestion run.

At **13:36:19 UTC**, a separate read-only aggregation of the first 200 ID-ordered production rows returned only counts/mean widths:

| Nonrandom sample | Rows | Mean full-row serialized bytes | Mean proposed summary serialized bytes |
| --- | ---: | ---: | ---: |
| BudgetLine summary inputs | 200 | 1,797 | 1,424 |
| Audit summary metadata | 200 | 2,304 | 765 |
| Extraction IDs referenced directly by budget lines | 0 | — | — |

These are JSON serialization estimates with keys, not PostgreSQL protocol bytes or provider billing. They are not random population estimates. In particular, the empty budget-extraction sample gives no evidence that budget receipt sibling payloads currently dominate production egress. Its qualification projection is a correctness-tested reduction for contexts when those associations exist, not a measured share of today's bill. Production provenance/source metadata remains intentionally selected where it controls eligibility.

Both diagnostic connections checked the project/SSL target, used read-only repeatable-read transactions and bounded timeouts, rolled back and closed. They performed no resets, data exports, application lifespan, production load tests, seeding or writes. Existing logs/runtime metadata could not be freshly read through the provider browser (`Debugger unattached`); actual restart cadence and current cache behavior therefore remain unverified.

## Executed local before/after evidence

The actual handlers ran against owned SQLite fixtures with deliberately large unused fields. Complete JSON responses match before/after for all six operations below. Captured SELECTs were replayed on the same owned connection to count rows, columns and UTF-8 selected values.

| Controlled operation | Before SELECTs / rows / selected-value bytes | After SELECTs / rows / selected-value bytes |
| --- | ---: | ---: |
| County money flow | 6 / 7 / 328,253 | 6 / 7 / 131,470 |
| National money flow | 6 / 7 / 328,253 | 6 / 7 / 65,848 |
| All-counties money flow | 6 / 7 / 262,650 | 6 / 7 / 65,865 |
| Findings page, page 2 / limit 2 | 3 / 14 / 3,265,027 | 6 / 7 / 139,561 |
| Same page with status=open | 3 / 14 / 3,265,027 | 6 / 18 / 139,646 |
| Basic county detail | 19 / 37 / 3,002,122 | 20 / 47 / 1,250,459 |

The page's rich Audit result drops from twelve rows to two. Its status facet still scans twelve small metadata rows to preserve exact Unicode/whitespace/fallback semantics. Basic detail adds ten short description rows while eliminating full unused Audit payloads. Statement count alone is not a transfer measurement. Source/entity metadata and unrelated basic-detail financial reads remain in these fixture totals.

The budget qualification context fixture selects **574,785 → 82,864 UTF-8 bytes**, with five context SELECTs in both states. Thirty-two complete output cases cover valid evidence, malformed roots/members, missing/mismatched sources, country/period/association conflicts, origin/classification refusals and 121 retained observations. Six generic-table controls retain the original full-model context path. Against the original module, 38 controls pass and the transfer guard fails; the revised module passes all 39.

The source-vintage fixture covers partial/offset/invalid/null publication dates and non-object metadata, real max/fallback values, missing IDs and two selected columns below 512 selected-value bytes, despite retained 64 KiB unused fields.

These synthetic sizes exclude protocol, TLS, pooler/control traffic and provider accounting. Do not quote their percentages as expected bill reductions or use them to decide Free-plan viability.

## Verification and rollback boundary

Root's final affected-suite run: **574 passed, 5 existing disposable-PostgreSQL prerequisite skips, 3 existing deprecation warnings, 8.99 seconds**. Independent review executed the four new/affected projection suites: **93 passed**. The review checked consumed-field coverage, no deferred reads, retained committed components, all accounting cohorts, display-grade-before-selection, count/page/status/withheld semantics, complete receipt observations and vintage fallback. No actionable correctness defect was found.

Separate cross-agent adversarial executions matched complete baseline outputs for **55 probes**: 20 hostile budget qualifications, 17 money-flow accounting cases in fresh sessions and 18 actual county page calls. Missing sources/periods/evidence, invalid numbers, explicit model origins, competing sources, sector-only periods, malformed provenance, Unicode/whitespace statuses, tied dates and over-end pages retained their original refusals/absence/ordering. The modified read paths did not turn any tested invalid input into a verified amount.

The final root run used the existing complete backend Python runtime with an allowlisted environment: dotenv disabled, inert file SQLite DATABASE_URL, seeder/warmup false, TESTING=true, ENVIRONMENT=testing, Redis empty. TestClient was not entered as a lifespan context. It executed the new transfer/qualification/vintage cases plus money-flow, county citation/scope/accounting/query-volume/evidence, financial absence/adversarial, generic qualification, fiscal publication, revenue qualification and receipt suites. PostgreSQL SQL compilation is covered; the five existing receipt persistence cases were not executed against an assigned disposable PostgreSQL server. Production aggregate observations do not replace those tests.

No schema/data/configuration change needs unwinding. If the deployed read contract regresses, revert this query-only commit and redeploy the prior application. Abort conditions are changed amounts/basis/source/absence labels, missing citations, new 5xx errors, or deferred per-row context reads. First production observation should confirm the deployed version and representative existing API responses, then compare the daily meter and query deltas under ordinary demand.

External raw receipts are retained in the coordinator's `EGRESS_2026-10-08` artifact directory: public-query-audit, review, adversarial-public-review, adversarial-qualification-review, query snapshots/deltas, production widths and final-tests.log. They contain owned fixture outputs or aggregate metadata, not credentials or exported production records.

## Remaining work under #481

1. Correlate existing Render startup/request/ingestion logs with daily Supabase service breakdowns and deployment/version/cache evidence. Do not call a small database or quiet 14-minute interval proof of measured headroom.
2. Review broad startup warmups and the fixed 2024/25 keys against the actual current default/year and restart rate. Do not raise recycle limits or remove bootstrap/freshness work without these measurements.
3. Consider a compact federal homepage fill, unused columns in financial-series/unpaginated findings paths, and safely completed ingestion checkpoints as separate small slices. Full extraction JSON needed by canonical ingestion hashes remains required; source/provenance checks cannot be removed to save bytes.
4. Observe at least seven representative deployed days, including the intended ingestion/worker profile and a deployment. Actions-off/quiet days alone do not represent future nightly traffic. The provisional 120 MB/day total and 200 MB/month social targets remain planning margins.
5. Record measured Free-tier headroom before any downgrade. Supabase Pro remains active. No automatic monitoring, regular job enablement, billing change or issue closure follows from this PR.
