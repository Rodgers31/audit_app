# Batch 11 #602 handoff: bounded CRA recommendation ingestion and dispatch

Addresses #602 (CRA half). OpenData is still unavailable and is tracked in
[#621](https://github.com/Rodgers31/audit_app/issues/621). #554 and #583 remain
open. Dispatch and the CRA source flag stay default-off. Nothing here activates
anything in production.

This handoff names the predecessor and the tested bytes. A committed file can't
know the commit that contains it, so the exact pushed HEAD/tree and how they
correspond to the tested bytes are in the external append-only postcommit binder
(see "Evidence").

## Provenance

- Accepted predecessor: main `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`, tree
  `9d0061928c16d173859f98cb6daa5f2f591b257c`. Lane branch
  `codex/batch11-native-source-entrypoints`, checkout
  `/Users/roger/.codex/worktrees/batch11-native-source-entrypoints/audit_app`.
- This continues the interrupted Codex session `01a12626-69b6-7d82-9083-54e4bf07a86b`.
  Before any edit, the lane checkout matched the recovery bundle's
  `WORKING_TREE_MANIFEST.json` (23/23 source hashes). The bundle was not
  re-applied. Historical receipts are unchanged and stay in the bundle.
- Ownership: decision `ISSUE_602_DECISION_001`. A consequential-hunk request was
  appended to `ISSUE_602_REQUESTS.jsonl` for the Batch 9 legacy test's literal
  `13 → 14`, which is pending coordinator acceptance.

## What ships

| Area | Change |
|---|---|
| CRA source | `backend/seeding/domains/cra/{source,parser,writer,__init__}.py`. One reviewed official PDF (no discovery, no redirects, bounded bytes and time) → FY2026/27 Table 5.2, printed page 32 / PDF page 39 → four national recommendations in raw KES → one `SourceDocument` plus one `Extraction`. Nothing is relabelled as an enacted budget or as actual revenue, and no other financial table is written. |
| Parser contract | The exact reviewed header cells by column position, data-row labels, order and nonempty positions, and the table's own arithmetic (baseline + adjustment = recommended; the totals; the county "of which" lines). Amounts use a bounded grammar (≤ 6 integer digits, ≤ 2 decimals, canonical commas) and are carried as integer hundredths, so reconciliation and the KES conversion are exact. Any other layout is refused. |
| Writer contract | Type-strict canonical-JSON replay identity. Re-proves the exact native or dispatch observation shape, the claim/observation time window, a run-bound aware `fetched_at`, and a live domain execution lock on the writing transaction. A refusal happens before any effect, with rollback. |
| Gate | `SEED_CRA_INGESTION_ENABLED` defaults to false and accepts only `true`/`false`. The builtin loader imports CRA only when it is enabled. Worker readiness and the handler both refuse when it is disabled. |
| Dispatch | `cra → cra` mapping. Model checks plus migration `e602b11a0001` (parent `e554b10a0001`; requires a stopped worker; downgrade refuses CRA history; RLS/ACL preserved). The other four mappings are unchanged. |
| Registry | `cra_recommendations` source metadata (Commission on Revenue Allocation). |
| Every-writer | `cra` added to `etl/writer_ownership.py` `LEGACY_DOMAINS` (count description 13 → 14). |
| Fixture preparer | `.github/scripts/prepare_reconciliation_test_fixture.py` binds readiness to the repository's single ordered Alembic head instead of a hard-coded `e554b10a0001`, and refuses two heads. This is the #613 class, which would otherwise recur. |
| Review gate | `financial_literal_reviewed_inventory.json`: only the `backend/seeding/config.py` entry changed, after the dated review `FINANCIAL_CONTEXT_REVIEW_CONFIG_2026_10_10.md`. |
| Evidence tooling | `tools/record_v3.py` (complete measured inventories, source drift, deadline, exit semantics), `tools/run_suite_v2.py` (CI-equivalent owned prerequisites), `tools/publish_v2.py` / `tools/verify_packet_v2.py` (portable packet, integrity vs acceptance). |

## Supported mapping matrix

| Source | Native domain | Native CLI | Dispatch | State |
|---|---|---|---|---|
| oag | audits | yes | yes | accepted (unchanged) |
| treasury | fiscal_summary | yes | yes | accepted (unchanged) |
| cob | counties_budget | yes | yes | accepted (unchanged) |
| knbs | population | yes | yes | accepted (unchanged) |
| cra | cra | only with `SEED_CRA_INGESTION_ENABLED=true` | only with the flag and `ADMIN_ETL_DISPATCH_SOURCES` including `cra` | this PR, default off |
| opendata | — | `Unknown domain(s) requested` | 503, unavailable with a reason | blocked: #621 |

## Tested source

- Product bytes: identical from `5d62b1d11e48ff06d4bf00cb7f0eae3e2ac35cf9`
  (tree `53c782b1…`) onward. The relevant cohorts, preparer, parser controls,
  lint and heads ran there.
- `eb0989a5e89f6a7c3feacab416311e7ac4e4f795` (tree `72d6d9d0…`) adds only the
  legacy session test literal, the complete-cohort runner and evidence. The
  complete inventories ran there.
- `fa8f90139feddb1493a530b0815d832b78d94485` (tree `9a796ca0…`) adds only
  evidence and the recorder's CI-parity mode. The CI-parity inventory ran there.
- Author evidence after these pins is historical. The coordinator correction below changes the writer boundary and adds versioned current verification; the old v2 verdict must not be used to certify the corrected checkout.

## Executed red → green (same input, recorded with record_v3)

| Receipt | What it proves |
|---|---|
| `red-01` → `red-02` | Parser: all four retained header reproductions accepted (negation, historical, year-prefix, full column swap), plus a values-only swap, the retained 32/33-digit Decimal-rounding input, oversized/noncanonical amounts and the printed-page check. Writer: stored `true`/`39.0`/`1.0` certified unchanged, foreign native/legacy/unknown observation metadata, stale/future jobs, an unbounded `fetched_at`, writing after `execution.close()`. red-01 mutated JSON through the ORM, which silently does not persist a Python-equal dict (see LESSONS 1). red-02 mutates in SQL and is the genuine red against the original writer `55aa7263…`. |
| `red-03` → `green-03` / `final-preparer-*` | The accepted-base preparer still expects `e554b10a0001`; it now reads the repository's single head and refuses two heads. |
| `red-04` | The real legacy loader (child process) and the real CRA CLI interfere without `cra` in `LEGACY_DOMAINS`: CRA wrote while legacy held its claims; legacy wrote while CRA, or a retained uncertain CRA claim, owned the domain. |
| `red-05`, `red-06`, `red-07` | Review round 1: a foreign or tampered extraction is appended next to the correct one, a ×10 table passes, a lock-key contender satisfies the writer, and an invalid flag is logged as an import failure. |

## Final cohorts on commit 5d62b1d

| Receipt | Runtime | Passed | Failed | Errors | Skipped | Drift |
|---|---|---|---|---|---|---|
| `final-cohort-current` | Python 3.13.9 / SQLAlchemy 2.0.54 | 1879 | 0 | 0 | 42 | none |
| `final-cohort-minimum` | Python 3.12.14 / SQLAlchemy 2.0.23 | 1879 | 0 | 0 | 42 | none |
| `final-preparer-current` / `-minimum` | both | 15 / 15 | 0 | 0 | 0 | none |
| `final-parser-control-{current,minimum}-{normal,optimized}` | both, `python` and `python -O` | exit 0 | — | — | — | none |
| `final-lint-ci-critical` | flake8 E9,F63,F7,F82 (CI gate) | exit 0 | — | — | — | none |
| `final-alembic-heads` | — | `e602b11a0001 (head)` | — | — | — | none |

The cohort covers every `test_batch9_*`, `test_batch10_*` and `test_batch11_*`
file except the legacy-package `test_batch9_legacy_etl_sessions.py`, which runs in
the full launcher's legacy cohort. It also includes the single-head,
financial-literal, CLI-budget and source-registry gates. It ran with
CI-equivalent owned prerequisites (`tools/run_suite_v2.py`):

- an empty service PostgreSQL on `DATABASE_URL` and an owned Redis (CI's pinned images);
- the real preparer for `BATCH9_RECONCILIATION_DATABASE_URL`, which prepared at head `e602b11a0001` and was cleaned up afterwards.

Mapped reconciliation executed 138 cases, 31 of them for `cra`. **The 42 skips
are all `test_batch9_native_schema_readiness.py`**, which needs
`BATCH9_NATIVE_READINESS_DATABASE_URL`. Hosted CI doesn't set it either, so this is
an unchanged prerequisite and those cases did not run.

## Complete backend + legacy launcher inventories

The unchanged launcher, `.github/scripts/run_backend_tests.py`, hard-codes
`--maxfail=5`. On this macOS host it stops early in both runtimes
(`launcher-unchanged-truncated-{current,minimum}-5d62b1d`: 6,809 passed, 6
failed, 4 errors, 9,214 collected nodes without an outcome). It is **not**
reported as complete. Two causes:

- `test_bounded_pg_backup`, which also fails on the pristine base
  (`baseline-base-bounded-pg-backup-*`);
- a real #602 consequence, the legacy session test's `13 → 14` claim literal,
  fixed in `eb0989a…` and journaled.

`tools/run_launcher_cohorts_complete.py` imports the unchanged launcher and
reuses its inventory, package bindings and collection receipts, without
`--maxfail`. Results:

| Receipt | Runtime / env | Backend passed / failed / errors / skipped | Legacy |
|---|---|---|---|
| `complete-*-current-eb0989a` | 3.13.9 / 2.0.54, recorder env | 14,800 / 19 / 16 / 1,426 (16,261 unique cases) | 295 / 0 / 0 / 41 |
| `baseline-complete-*-current-base` | same, pristine base `bcb5ff9` | 14,538 / 19 / 16 / 1,426 | 295 / 0 / 0 / 41 |
| `complete-*-minimum-eb0989a` | 3.12.14 / 2.0.23, recorder env | 14,799 / 20 / 16 / 1,426 | 295 / 0 / 0 / 41 |
| `complete-*-ciparity-current-fa8f901` | 3.13.9 / 2.0.54, CI-parity env | 14,812 / 7 / 16 / 1,426 | 295 / 0 / 0 / 41 |

`probes/complete-inventory-failure-diff.json` compares the commit with the
pristine base on the same env:

- **0 commit-only failures** and 0 base-only failures (35 identical);
- identical skip sets;
- 270 new cases on the commit, all passing;
- 8 "removed" ids, which are random-UUID parametrizations.

Every remaining failure is named and pre-existing:

- `test_bounded_pg_backup`: 1 failure plus 16 setup errors, host-only (macOS
  ownership/mode checks); reproduced on the base.
- `test_healthcheck_is_bounded` (6): `node` is not installed on this host, and
  the test says it is present on `ubuntu-latest`.
- Recorder-env-only failures, which disappear in the CI-parity run: 7
  `test_stalled_projects_pipeline.TestFetch`, 3 `test_inflation_monthly_live`,
  1 `test_cpi_publication` and 1 `test_receipt_ingress_trust`. Each comes from
  inert `SEED_LIVE_PDF_FETCH_ENABLED` / `SEED_ENRICH_WITH_WORLDBANK` overrides
  that CI does not set.
- Minimum-runtime only: `test_budget_qualification_transfer` pins SQLAlchemy
  2.0.5x JSONB rendering. It reproduces on the base with 2.0.23 and is filed as
  [#625](https://github.com/Rodgers31/audit_app/issues/625).

The 1,426 skips are unchanged prerequisites. That is the same set on the base
(owned-PostgreSQL env vars that hosted CI also leaves unset, e.g.
`BATCH9_NATIVE_READINESS_DATABASE_URL`, `AUDIT_TEST_POSTGRES_URL`, social and
egress lanes). Those cases did not run. Hosted CI on Linux remains the
authoritative unchanged-launcher gate.

## Repairs 1–7 from the continuation task

1. **Parser column identity.** The parser checks cell-exact headers by position,
   row labels, order and positions, the table's own identities, and the table
   against the page text, all on the unchanged official PDF. The four retained
   cases and more refuse (`red-01/02`, `red-05`).
2. **Exact numeric semantics.** The grammar allows at most 6 integer digits
   (≤ KES 999,999.99 billion, about 335× the largest reviewed value) and at most
   2 decimals, with canonical commas. Values are integer hundredths, so the KES
   value is hundredths × 10⁷ with no Decimal context. The retained 32/33-digit
   input and an oversized value in the real layout both refuse.
3. **Stored extraction type identity.** Comparison is canonical type-strict JSON
   plus an `int` column check, reproduced on PostgreSQL through SQL `jsonb_set`.
   Valid idempotent replay and the tampered/duplicate SourceDocument controls are
   kept, and a refusal rolls back with zero effects.
4. **Ownership boundary.** The direct-call hypotheses were classified against the
   real orchestration: the CLI holds the execution lock for the whole handler.
   The writer now refuses foreign metadata, out-of-window observations, an
   unbounded `fetched_at`, and a lock not held by the entering runner. Claims are
   never released or expired. The residual limit is below.
5. **Every-writer enrollment.** `cra` is in `LEGACY_DOMAINS`, with the new
   `WRITER_INVENTORY_ADDENDUM_602.md` and real-loader/real-CLI controls
   (`test_batch11_cra_legacy_ownership.py`) on both ORMs.
6. **Full-cohort gates.**
   - The `config.py` financial-literal entry was updated after a dated review.
   - The mapped-reconciliation failures were diagnosed with an A/B probe
     (`probes/autovacuum-ab-2026-10-10.json`). Same image, template and 138 cases:
     with autovacuum on (1 s naptime), 13 failed on "Other database sessions…";
     with autovacuum off, as the CI preparer sets it, all 138 passed. The
     production refusal is correct; the draft runner built its template in an
     autovacuum-enabled container.
   - The citation test's inert `DATABASE_URL` is replaced by an owned service
     PostgreSQL.
   - The preparer head fix is shared with item 7's tooling.
7. **Evidence publication.**
   - `record_v3` records complete unique inventories, source drift, a deadline,
     exit semantics and receipt readback.
   - `run_suite_v2` provides the owned prerequisites.
   - `publish_v2` is append-only, makes paths portable and compacts oversized ids.
   - `verify_packet_v2` keeps integrity separate from current acceptance, with
     negative controls for tampered, unlisted/internal, symlinked, escaping,
     malformed and rebound receipts (`test_batch11_evidence_packet.py`).
   - The draft `run_cohort.py`, `record_v2.py`, `publish_v1.py` and
     `verify_packet_v1.py` stay in the recovery bundle with their original
     identities and are not committed.

## Independent reviews

See `batch11-issue-602-evidence/REVIEWS.md`: Standards and Spec ran in parallel,
in two rounds, each executing its own controls on both runtimes. Every round-1
finding is fixed or recorded as a decision. Both round-2 rechecks report the
fixes confirmed and only the residual lock limit below.

## Issues

- New: [#621](https://github.com/Rodgers31/audit_app/issues/621), the OpenData
  external prerequisite; [#625](https://github.com/Rodgers31/audit_app/issues/625),
  the minimum-SQLAlchemy test pin (independent, pre-existing). Census: 308 issues (15 open / 293 closed; 312 PR rows
  excluded), plus PR titles and bodies, searched for OpenData/ArcGIS/CRA/
  `SB_0006`. Only #602, #554 and #545 mention OpenData. No matching ticket existed for #625.
- Reused or recorded:
  - #613 (closed): the same stale-head class, now removed by deriving the head.
  - #602 / #554 / #583 remain open.
  - The autovacuum runner fault and the zsh/recorder slips were lane-internal
    author tooling mistakes, fixed here, so no product issue was filed.
  - The lock-identity residual is a coordination request to #603, not an issue.

## Resources

All owned containers, networks and volumes were labelled and nonce-named, and
were removed with readback (`suite.json`, the `resources*.json` files written by
the fixtures, and receipt `owned_containers_after`). The ports (55531, 55535–55537,
55539, 55543, 18031, 18043; reviewers 55541/55542, 18041/18042) avoided every
sibling reservation. The disposable full-run worktrees are listed in the
postcommit binder.

## Evidence

- Committed: `docs/admin/implementation/batch11-issue-602-evidence/`. Run
  `python -B docs/admin/implementation/batch11-issue-602-evidence/tools/verify_packet_v3.py`;
  it reports historical integrity only unless `--current-receipt` names a fresh external record_v4 receipt for the exact clean checkout.
- External outputs: `/Users/roger/.codex/visualizations/2026/10/10/01a12626-69b6-7d82-9083-54e4bf07a86b/issue602/claude-continuation/`
  holds the raw logs, JUnit, the reviewer logs and the append-only `POSTCOMMIT_BINDER.json`.
- Proposed skill lessons: `LESSONS.md`.


## Remaining constraints and next step

- OpenData: #621. Reconfirmed on 2026-10-10 that `api/search/v1` returns 401
  `SB_0006 Subscription is canceled`, the legacy `api/views.json` returns 404,
  and the bare host times out. #602 can't fully close until #621 is resolved or
  OpenData is retired from #554.
- Coordinator: accept or reassign the journaled consequential test hunks: the
  `13 → 14` literals in `test_batch9_legacy_etl_ownership.py` and
  `test_batch9_legacy_etl_sessions.py`, and the three batch10 test edits. The
  `etl/database_loader.py` comment "Thirteen continuity transactions" is now
  stale; it is outside this grant and left unchanged.
- #611: its dependent migration still waits for coordinator acceptance of this
  real `e602b11a0001` predecessor.
- Hosted: a fresh immutable hosted run of the seven-job verification. The
  preparer now reads its head from the repository, so no further edit is
  needed for it.
- Production (#583) and operator acceptance (#554) are separate. CRA
  activation needs the flag, the dispatch source selection, a production
  migration and every-writer quiescence, none of which is done here.
- The historical P1b lock-identity limit was repaired during coordinator review: see the exact physical PID, entry nonce and continuity contract below. Historical red receipts remain unchanged.
- Decisions recorded:
  - A malformed `SEED_CRA_INGESTION_ENABLED` (`1`, `TRUE`, …) stops every seeding
    run (fail closed rather than guess).
  - With the flag off, the CLI reports `Unknown domain(s) requested: cra`
    because the domain is unregistered; dispatch gives the specific reason.
  - Any later parser edit changes `parser_sha256`, so replay on an existing
    database refuses until an operator reconciles. It never appends.

## Coordinator review corrections (2026-10-10)

The five Copilot comments and all general review observations were checked against actual execution. The writer now requires the live handler-visible DomainExecution on the same engine, exact physical PID, canonical domain/run/command identity and the claim's entry nonce digest. It re-proves physical continuity, and its observation window begins at the later of acquisition and entry (with the existing clock margin). A preopened transaction that replaces a killed lock holder is refused before effects, as are absent or foreign execution identities. Existing document lookup uses country/publisher/URL before comparing the strict artifact and extraction identity, so changed provenance cannot append a second document under an existing URL. The same owned PostgreSQL controls confirm valid replay and zero effects on refusal.

Evidence versions are append-only: record_v4/run_suite_v3/verify_packet_v3 supersede the archived v3/v2 tools. The current reader checks every tracked and untracked source input (including workflow/dispatcher/config), forbids source links before reading, requires exact clean HEAD/tree and before/after digests, hashes raw output, recomputes actual JUnit or both launcher collection/outcome inventories, and rejects failed/error/xpass, timeout, missing-source or leftover-resource claims. Archived final-* receipts remain history and cannot certify this corrected source. The companion launcher derives its checkout from __file__ and admits only fresh external non-symlink output. The unchanged hosted launcher remains the whole-suite gate.

Current and supported-minimum scoped writer/API/worker/evidence controls passed after the initial correction; the latest expanded current cohort passed all99 cases with zero skips/failures/errors and owned-resource cleanup. Final committed-source runs, both independent review axes and the integrated seven-job hosted verification are coordinator-owned external records, not claims about a future self-containing commit. The bootstrap sibling now fences optional CRA claims even with its flag off. #602 remains open for #621; #554/#583 remain open for production/operator activation.
