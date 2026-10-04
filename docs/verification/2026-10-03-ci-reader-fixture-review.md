# Reader and route CI fixture review — 2026-10-03

## Baselines and scope

Owned branch `codex/remaining-ci-reader-controls`, base `7f17daa`. The same nine assigned full test files were executed on actual main `3ddd3d36b08cddefc38736650ff947325bdb7a6b` (13 failed, 192 passed, 5 skipped) and integrated base `7f17daa` (19 failed, 186 passed, 5 skipped). All 19 assigned failures are fixture/contract drift. No production handler, publication gate, qualification evaluator, producer, parser, or detector was changed.

## Per-finding classification

| Group | Count | Baseline | Evidence and repair |
|---|---:|---|---|
| County pending-bill positive | 1 | Main | `select_county_pending_bills` requires declared KES; SimpleNamespace omitted currency. Supply KES and add missing/USD currency refusal cases. Keep list-shaped, national-on-county and bad date refusals. |
| County list health | 1 | Main | Current `county_audit_signals` selects latest executive FY and maximum severity in that FY, requires independently declared executive source identity, and reports FY end rather than ingestion date. Fixture had no volume kind and mixed all older warnings into latest FY. Declare executive source, give older findings their older annual FY, preserve 12 findings/order/200-character snippets/ten-item limit/clean latest INFO. Assert coverage FY2022/23 and 2023-06-30, never official opinion. New missing-institution case stays pending with 12 findings and genuine budget. |
| County query volume reached after health positive | 1 assertion | Main source already has selector | Existing selector adds one bounded citation/period metadata batch to finding metadata and short-description batches. Pin exact three audit SELECTs and exactly one citation metadata batch/one substring batch; retain absence of full finding text and management responses. No production query changed. |
| Budget overview freshness | 1 | Main | Exact official-county scope intentionally excludes `Test County`. Use Baringo County with explicitly synthetic quantities; preserve actual selected FY, money and trust-note assertions. |
| Persistent local UI fixture status | 1 | Main | Synthetic source document omitted executive volume. Add explicit synthetic executive declaration. Preserve synthetic publisher/title/URLs and refusal of changes, add assembly-volume mutation refusal. No official source facts invented. |
| Cache sweep pipeline health | 1 | Main | Worker owns its SessionLocal session, bypassing request get_db as intended. Fixture now supplies a distinct worker Session bound to isolated SQLite fixture connection, making populated/empty/restored reads observable. Preserve complete route sweep, serialization probes and table-read proof; no allowlist. |
| Dead-database sweep | 1 | Main | Worker factory escaped old request-only fixture patches. Patch factory to the same synthetic dead failure. Watch actual worker-factory invocation and trip on any real database engine connection. All route discovery, dependency-signature and no-zero controls retained. |
| Direct hostile debt calls | 7 | Main | Actual sustainability handler is no longer decorated. Call actual handler directly, retaining NaN/bool identity-map inputs and absence assertions. |
| Direct versus HTTP county qualification IDs | 5 | Integrated only | Native row-ID dict keys are integers; JSON object keys are strings. Compare full actual FastAPI encoding followed by JSON serialization, with allow_nan=False. Preserve entire payload equality plus explicit ID-key association; no fields removed or ignored. |
| NULL allocation reason | 1 | Integrated only | Shared typed qualification emits value_not_reported. Preserve null and no manufactured KES0 checks; assert typed reason and allocated_amount unavailable qualification. |

## Verification

- Eleven affected full files plus actual pipeline worker and financial-health disclosure controls: **231 passed, 5 skipped**, 14 warnings, 10.76 seconds. Logs retain all skip reasons.
- Separate actual PostgreSQL full legacy county-budget contract: **35 passed**, 3 warnings, 11.34 seconds; this executes the four Numeric special-value cases skipped by the SQLite run.
- Exact citation publication expression PostgreSQL probe: **1 passed**, 3 warnings, 0.46 seconds. The original full-preflight setup error was connection refusal at the stopped local 55439 fixture, not a publication-expression defect.
- PostgreSQL was a new owned tmpfs `postgres:16-alpine` container, `audit-ci-reader-controls-20261003`, loopback-only port 62217, trust user receipt_test, synthetic database audit_ci_citation; each PostgreSQL fixture created/dropped unique schema. Container removed after runs. No root database or existing cluster used.
- The remaining 53MB CBIRR fixture-dependent case was skipped, not executed. No broader optional PostgreSQL suite is claimed executed.

## Finite full-preflight inventory

The earlier untruncated run at `16c15ca2168de0eb102c05f26e557cd59f36bc04` found **43 failed, 8283 passed, 1101 skipped, one setup error**, 265.36 seconds. Exact nodes and every skip record are retained in `A/REMAINING_CI_COMPLETE_FAILURE_INVENTORY.json`. Of those skip records, 1085 mention an explicit PostgreSQL/database DSN prerequisite; this includes combined PDF+PostgreSQL prerequisites and must not be represented as executed database coverage. The other 16 comprise four required retained-PDF cases, one DI fixture exclusion, one empty parameter set, eight workflow-expression cases, and two isolated integration database prerequisites (the latter are still database prerequisites). Detailed reasons remain authoritative.

Other 24 original failed nodes were assigned to separate producer/PDF/WB/packaging/social workers. This scoped green run does not establish a green consolidated backend suite. Root's final combined local and hosted CI gates remain.
