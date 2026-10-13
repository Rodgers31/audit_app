# Batch 12 browser reliability — draft #624 remains HOLD

This continuation repairs three demonstrated readiness boundaries and records
the remaining historical failures separately. Local Docker Desktop execution
does not provide native hosted Linux acceptance. The coordinator must review
the frozen pushed source and complete the combined gate before any merge.

## Source and ownership

Owned worktree: `/Users/roger/.codex/worktrees/batch12-browser-reliability/audit_app`.
Local branch: `codex/batch12-browser-reliability`; published branch:
`codex/batch11-county-navigation`, existing [draft #624](https://github.com/Rodgers31/audit_app/pull/624).
Accepted main `dfd18032b6f38d57bfaa6f66d0feac218189f54c` was merged normally
at `33612990bf8e084eea731b9cebee759b5a408cf2`; this continuation starts at
`8f4953017b9deb84c62b557e2e87c6d76b47b5e4`.

External evidence root, abbreviated R:
`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/BROWSER`.
Fresh producers and attempts have unique paths. Historical failures, source
inventories, raw logs and required trace bytes remain immutable. The dirty
primary checkout and peer checkouts were not edited. Shared layouts, CI,
dependencies, backend models and migrations remain outside this lane's changes.

## Demonstrated boundaries and resulting behavior

1. The `/counties` route loading boundary streamed its prefetched heading/table
   into hidden `S:0`. Holding the real stream promotion plus bootstrap yielded
   zero immediate accessible headings; promoting hydration before stream cleanup
   produced two strict row-count matches. Removing this narrow route loading
   boundary keeps the prefetched explorer in the initial document. The existing
   five-second prefetch budget and hourly ISR remain unchanged. Cold navigation
   waits for the existing server work; the removed skeleton also covered nested
   detail loading. No global Suspense/layout or CSS change was made.
2. Server-rendered fiscal year buttons accepted clicks before React attached
   their handlers. A real controlled click was lost; the same click after
   hydration selected FY2024/25 and rendered KES150B. FiscalYearPicker now keeps
   those buttons disabled until its mount effect attaches usable handlers. This
   proves the early-click boundary, not every historical fiscal failure.
3. A native county-detail query mutation after Next's initial history commit but
   before its passive History API patch left the URL on FY2024/25 while React's
   query stayed stale. The original ten-second FY request detector failed at
   zero requests. A mount microtask reconciles a still-different current query
   through Next's supported native replaceState integration, preserving the
   current href/hash, ordinary custom state fields and existing history entry.
   The final actual regression also proves a hostile response reaches the
   controlled error state and clearing FY recovers without a document reload.

The query helper is intentionally one-shot and version-bound to the observed
Next15.5.27 ordering. It cannot recover an FY already erased by the initial
canonical history commit, nor guarantee arbitrary delayed parent patching.
Ordinary object custom state is preserved; arbitrary primitive/array state
identity was not established. No timer, polling product retry or global history
monkey patch was added.

## Original-test preparation and case inventory

An actual pre-initial-commit control demonstrated FY URL → plain county URL
during Next's first canonical replaceState, then zero FY requests at the
unchanged ten-second detector. Post-commit and fully-ready controls passed the
same numeric42 hostile payload. The natural public-v2 malformed-number trace
was consistent with this boundary but did not independently capture the caller
ordering; that distinction remains explicit in `DETAIL_COMMIT_READBACK_V1.json`.

The original response-validation helper now proves working Budget & Debt /
Overview tab navigation before injecting FY. Its request detector, hostile
payloads, error/empty-row/page-error assertions and deadlines are unchanged.
All 55 other original test files and the changed file's assertion tail match
base8f exactly. This is an authorized observable completion preparation after
demonstrating an unfinished transition, not an assertion/retry relaxation.
Independent literal controls reject a no-op tab and a zero FY request even
when the tabs work.

`CURRENT_ORIGINAL329_INVENTORY_V3.json` binds the fresh canonical collection:
329 original cases, the same file/title/column/project identities and eleven
fixme annotations. Forty-five descriptor lines move by four in the modified
preparation file. The four new causal regressions stay outside original329 in
`browser-regressions/` with a separate configuration and isolated reporters.
The publication21 suite is separate from both inventories.

## Local execution

| Original cohort | Cases | Passed | Original fixmes | Failures/errors/flaky |
|---|---:|---:|---:|---:|
| Public v4 |275|264|11|0|
| Users v1 |4|4|0|0|
| Operations v1 |6|6|0|0|
| Overview-audit v1 |5|5|0|0|
| ETL UI v1 |28|28|0|0|
| Coordinator v1 |11|11|0|0|
| Original partition |329|318|11|0|

Separate publication21 v2: all 21 passed, no skips/failures/errors/flaky results or retries.
`PUBLICATION21_OUTCOME_READBACK_V4.json` reconciles the exact21-case collection, actual JSON/JUnit outcomes and source-bound terminal receipt. Build `jMPZ4DhM843CNMwCgFF5i` targets canonical API8125. The first attempt passed20 and failed the signed refresh fixture because `jq` was absent; no product or test bytes changed. Installing the owned container prerequisite `jq1.7.1-3ubuntu0.24.04.2` and its two new libraries enabled the unchanged full21-case rerun. The original failure and exact package/binary delta remain preserved; the earlier329 runtime did not use jq.
All six original groups are disjoint and exactly match the fresh329-case
inventory. Each has one result per case at retry0, matching JSON/JUnit outcomes,
no report errors and no source drift. The original fixme annotations are exact.
`FULL329_PUBLIC_USERS_OPERATIONS_OVERVIEW-AUDIT_ETL-UI_COORDINATOR_READBACK_V4.json`
and `JUNIT_PUBLIC_USERS_OPERATIONS_OVERVIEW_AUDIT_ETL_UI_COORDINATOR_READBACK_V5.json`
bind the actual raw reports. `ORIGINAL329_BUILD_IDENTITIES_V1.json` records
six observed buildIDs with canonical loopback API targets8141/8151/8152/8153/8162/8163.


The final four causal regressions passed on actual production build
`1EMN_5x3pHIxH-nVx3PHZ`: immediate heading, unique row-count/ten rows,
hydrated fiscal selection, and detail history reconciliation. The first three
failed on frozen old source with the exact same test bodies (0/3); the final
detail regression failed at zero requests on that old source (0/1). These are
intended behavior reds with functioning fixtures, not loader/setup failures.
The default additive reporter paths changed only to avoid collisions; actual
external red/green executions already used unique explicit reporter outputs.

Four existing targeted unit files executed 41 passes with no pending cases.
Earlier public-v1:254 passes/10 failures/11 original fixmes. Public-v2:
263 passes/1 failure/11 fixmes. Public-v4:264 passes/11 fixmes, exact275-case
inventory and JSON/JUnit agreement, no retries/flaky results/errors/drift.
Public-v3 refused an existing live-output destination before launching any app
or case. Wrong module-instance adapters and other earlier setup attempts remain
preserved and explicitly excluded from causal/acceptance evidence.

The six configured cohorts use an owned private PostgreSQL fixture adapter and
sequential real production builds. The complete canonical orchestration script
was not executed: its Docker CLI/Git worktree assumptions are unavailable inside
the local container. Canonical cohort selectors, workers, deadlines and retries
are retained; canonical case/partition helpers reconcile actual reports. This
is local synthetic acceptance evidence, not a seven-job hosted gate verdict.

## Historical issue dispositions

| Issue | Current bounded conclusion and remaining work |
|---|---|
| [#601](https://github.com/Rodgers31/audit_app/issues/601) | Historical saved Y≈900→100 and later rapid second return→0 remain distinct. A fresh unchanged original rapid case failed on frozen failed source with an85.1ms forward/Back gap and constant document height; later Y908→892→797→383→0 had no recorded JS scroll/focus call, but that observer did not cover root.scrollTop. A corrected observer later passed at34.3ms and captured actual Next root.scrollTop calls. Those later passes do not identify the earlier scroll owner. Required next experiment: native hosted failed-source replay recording all scroll owners plus browser-native restoration. |
| [#607](https://github.com/Rodgers31/audit_app/issues/607) | Preserve the held native client-only pagination repair and its earlier causal controls. Fresh held original20 yielded19 passes/one mobile-menu opening visibility failure before Escape in the Escape/focus case; failed-source original20 yielded20 passes. Neither explains historical natural transport/pagination ordering. Require the exact final native hosted original gate. |
| [#622](https://github.com/Rodgers31/audit_app/issues/622) | The SSR early-click loss is reproduced/repaired. In another observed original failure, React props/fiber were already attached at click; afterward the newest FY became selected. Callback/default-FY/query-cache ordering remains unresolved. Capture selected/defaultFY and query-cache updates together in native hosted replay. |
| [#623](https://github.com/Rodgers31/audit_app/issues/623) | Actual stream controls reproduce zero headings and duplicate summary overlap; the narrow loading-boundary removal passes both unchanged detectors. Require final hosted original rendering, pagination and accessibility acceptance. |
| [#629](https://github.com/Rodgers31/audit_app/issues/629) | Literal malformed `.py.txt` artifact,65 original archives, original-to-physical mapping and scanner policy remain unchanged. Keep open until reviewed frozen acceptance/merge. |

## Archive and backend proof retained

At base8f, the unchanged archive/financial/API guard cohort executed2,528 passes
per mode, no failures/errors/skips, across normal/optimized Python and actual
SQLAlchemy2.0.54/current and2.0.23/minimum isolated runtimes. Current Python is
3.13.9; minimum is3.12.14. Literal Git archive correspondence passed in normal
and optimized modes. Canonical backend collection was17,273 backend +336 legacy
=17,609, which is collection rather than full backend execution.
`FINAL_OUTCOME_READBACK_V2.json` binds those exact receipts and XML identities.
`UNCHANGED_BACKEND_ARCHIVE_BINDING_V1.json` compares all4,727 old tracked files: only the five declared county/budget/preparation files differ before this handoff rewrite; the1,940 selected backend/workflow/archive/scanner files do not. Guard results remain base8f facts with unchanged relevant bytes, not fresh full-backend certification.

## Runtime, cleanup and acceptance

Pinned Linux-amd64 Playwright image digest
`6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d`
ran under Docker Desktop29.8.2 on an ARM host with emulation. Node22.23.3,
npm10.9.9, Next15.5.27, React19.2.4, Playwright1.58.2 and Chromium145.0.7632.6
were actually observed. Owned fixture Python3.12.3/SQLAlchemy2.0.54 and private
PostgreSQL17.11 were used; PostgreSQL ran native ARM64. This differs from native
hosted Linux. Unrelated provider credentials were scrubbed; all local keys were
inert and no provider/live financial state was written.

Direct native cleanup completed at2026-10-12T22:56:08Z in `native-owned-resource-cleanup-v3/`: exact verified private PostgreSQL `d41c459febf7…` was removed first with its sole anonymous volume, then exact browser container `44ded05a0e56…`. Native inspect confirms both containers and the volume absent; full-ID volume references and both owner-label queries are empty. Private PG55494 refused a connection before the browser namespace was removed. Eight final host launcher groups were terminal and absent; Docker container absence separately closes their processes/network namespaces. No host ports were published. Shared bridge, bind directories, runtimes, frozen source, traces and review worktree remain.

The prior v2 native precheck stopped before any removal because its expected empty volume labels omitted Docker's actual `com.docker.volume.anonymous` marker; v3 requires that exact observed marker. The unused generic `cleanup_owned_runtime_v1.py` was retired after independent and parent fake-Docker controls demonstrated unsafe plan/receipt/probe acceptance. It was never used for native cleanup. `CLEANUP_V1_RETIREMENT.json` preserves that distinction; its existence is not a cleanup certificate.

Shared visualization storage uses the unchanged188380164096-byte baseline and
10GiB combined growth limit. Before/after phases and during long executions,
fresh measured guards were retained. After publication v2 the fresh guard measured192754503680 bytes, growth4374339584 bytes, within the unchanged10737418240-byte shared limit (`storage-checks/post-publication-v2-pre-cleanup-v1.json`). The post-cleanup publication guard measured192758431744 bytes, growth4378267648 bytes, within the same limit (`storage-checks/post-native-cleanup-pre-publication-v1.json`).
No broad prune, peer cleanup or historical-packet deletion was performed.

The existing PR remains draft/HOLD. Use the external `FINAL_COMMITTED_SOURCE_BINDING_V1.json`, final GitHub readback and STATUS.md for the actual committed/published SHA, tree, clean worktree and PR/issue state. The coordinator must freeze that published identity for native acceptance. The author is authorized one finished normal push to the existing branch and ordinary scoped progress comments; no merge, force-push, Actions dispatch or paid review.

Test receipts record base8f plus dirty source hashes. After committing, verify the final product/test hashes against those actual executions and record the binding externally before the sole push. This does not retimestamp the runs as executions on a later Git commit. The handoff is the only tracked change after the completed source-bound runs.

The coordinator alone owns review, combined integration, Actions and merge.
Required frozen native hosted gate: original329 with exactly the old eleven
fixmes, four separate new regressions, publication21, all seven mandatory jobs,
source/post-test/cleanup reconciliation and remaining historical diagnosis. The current seven mandatory CI jobs are `test-backend`, `test-frontend`, `test-etl`, `security-scan`, `test-browser`, `test-browser-legacy`, and `quality-gate`; this author did not enable or dispatch them. The four new regressions require an additional scoped coordinator execution without changing original329 accounting.
Production deployment/authenticated acceptance remains separate. No new issue
was created for already tracked or scoped repaired defects; broad issues stay
open. No paid review was requested.

## Evidence-backed skill proposals

- Preserve the initial visible heading/hydration/history-commit distinction:
  actual Next can erase a native FY before its first canonical commit. Require
  an observable working client transition and retain the real request detector.
- Treat intermediate custom state as part of the native-history contract:
  the first null-state helper lost an ordinary owner field; independent and
  parent controls reproduced the loss before the final fix retained it.
- Reject contradictory/duplicate JUnit terminal children before classification:
  earlier precedence hid skipped+failure and failure+error; literal controls
  now reject those cases. Successful reconciliation of a known red is not a
  successful execution verdict, and zero-case setup cannot accept a cohort.
- Bound observer coverage explicitly: a later root.scrollTop-capable green
  cannot explain an earlier rapid-return red whose observer missed that setter.

- Keep removal authority independent of a mutable cleanup plan: fake-Docker
  controls redirected generic plan-driven cleanup to foreign resources and
  exposed incomplete receipt/probe acceptance. Retire that producer; use fresh
  native full-ID ownership, volume-reference and resolved namespace checks.
- Reject bool-as-number, nonfinite/duplicate JSON, falsey malformed error fields
  and optimized-away asserts in acceptance readers. Independent and parent
  literal normal/optimized controls reproduced the false greens before the
  explicit v3 checks; the final publication reader changes paths only.

The previous base8f handoff remains in Git with the earlier trace references
and recorder/output-identity/process-group proposals. Independent final review
`adversarial-handoff-resume-v2/REPORT_HANDOFF_TRUTH_SCOPE_V2.md` accepted the
three causality/publication-wording corrections and found no other material
overclaim; it did not independently certify publication-v2 or native cleanup.

These are proposals for coordinator consolidation; no shared skill was edited.

## Coordinator review: hosted test boundary (#645)

The first combined hosted candidate (`7c803a1`, run38341871807) passed all
2,098 unit cases with the existing one skip, but Jest also selected the two
Playwright-only readiness files and failed to load them. The scoped repair
excludes only `browser-regressions/` from Jest and adds the unchanged four
controls to the existing Chromium publication job in both CI definitions.
Their reports are retained beside publication receipts; the original329
inventory and all seven mandatory jobs remain required.

On this PR source, all148 actual Jest suites passed (2,095 cases, one existing
skip). After correcting the manual workflow's multiline artifact path, all112
workflow controls passed. These are local scoped receipts under the
coordinator's `BATCH_12_REVIEW`; fresh complete hosted acceptance is pending.
The failed combined run is preserved and does not certify merge readiness.
The separate coordinator PostgreSQL bootstrap failure belongs to #641 and
requires actual canonical-role verification before that candidate can pass.
