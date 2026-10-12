# Batch 12 browser reliability — draft #624 remains HOLD

2026-10-12. This round merges accepted main and publishes a bounded diagnosis.
It makes no new product, selector, assertion, timeout, retry or dependency edit.
The original browser failures have not been reproduced and repaired in a fresh
real-app runtime. Do not accept or merge this lane on the results below.

## Ownership and source

- Worktree: `/Users/roger/.codex/worktrees/batch12-browser-reliability/audit_app`.
- Local branch: `codex/batch12-browser-reliability`; existing remote branch:
  `codex/batch11-county-navigation`, [draft PR #624](https://github.com/Rodgers31/audit_app/pull/624).
- Held source: `4a6580dfd79348da894a60ce7eb216f765d81edd`, tree
  `65371adf88828089cd8b87a209f5eae18160cd01`.
- Accepted main: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree
  `3a680eef19822ef0ac83aa6890c3b41deee97058`.
- Normal merge: `33612990bf8e084eea731b9cebee759b5a408cf2`, tree
  `f4ac2d03ed33f6f2bd2c6b5c682cbe3911d10396`. No conflicts.
- Failed hosted rapid-return source remains separately frozen at
  `75bc69c04a45b7eceffe47ddbdd9c1c2ea2c3282`.

External evidence root (abbreviated **R** below):
`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/BROWSER`.
`START.md`, `STATUS.md`, literal source inventories, raw logs, traces and versioned
producers are there. The final source-bound checks run after this handoff is
committed and stay external; their exact final HEAD is in the receipts/STATUS.
The primary checkout, peer lanes, Actions configuration, live providers and
shared dependencies/layout/model files were not changed by this author round.

## Separate failure families

| Issue | Observation and present conclusion | Next required experiment |
|---|---|---|
| [#601](https://github.com/Rodgers31/audit_app/issues/601), old Y=100 | Run 38009357220, source `b709…`: original `smart-back.spec.ts:72` failed `afterY > 100` after departing near Y=900–911. Later green runs do not explain this failure. | Replay the unchanged original on the held source with production-build runtime and recorded scroll owners. |
| #601, rapid second return Y=0 | Run 38087700192 at `75bc69c…`: first return passed; forward then Back about 71.582 ms apart returned the list and later moved to Y=0. No captured caller proves who won the scroll. | Record every scroll call, focus, popstate, route commit, saved target, height and active element around the unchanged rapid-return test. |
| [#607](https://github.com/Rodgers31/audit_app/issues/607) | The held native `replaceState` repair avoids Flight navigation for client-only page/view-all changes. Prior held/failed/competing-delivery controls establish that boundary, but not why the historical natural case delivered 200 or left the URL on `/counties`. | Run the original natural case and controlled delivery in the same exact runtime; retain transport/URL/commit ordering. |
| [#622](https://github.com/Rodgers31/audit_app/issues/622) | Original trace shows FY2025/26 heading, a FY2024/25 click, then failure to see the KES150B heading within the unchanged 10 s. No fiscal-selection cause established. | Capture hydration completion, click delivery, selectedFY updates, fiscal query/cache data and rendered heading; retain original payload and deadline. |
| [#623](https://github.com/Rodgers31/audit_app/issues/623), zero h1 | Original heading-count action's before snapshot contains `County Explorer` in hidden streamed fragment `S:0` with a zero rectangle. Its after snapshot contains a visible heading, 442.59×55.19 px. The query straddles a hidden-to-visible transition. | Real-app replay must demonstrate the same transition and an implementation repair with the original immediate query unchanged. |
| #623, duplicate row-count | Original error records two exact matching spans. Snapshots around the failed visibility action move a row-count span from hidden `S:0` into the visible page. They do not capture the two-span overlap itself. Streamed DOM overlap is a hypothesis, not a proven duplicate cause. | Record simultaneous matching nodes, their ancestor identity/visibility, stream insertion/removal and selector timing before any pagination click. |
| [#629](https://github.com/Rodgers31/audit_app/issues/629) | The held byte-artifact mapping is preserved. Its malformed historical producer is evidence, outside live Python discovery; the scanner is unchanged and still rejects malformed live source. | Keep open until reviewed frozen acceptance/merge; replay final archive, collection and guard checks. |

The original hosted rapid-return trace is retained at
`BATCH_11_REVIEW/CI_V2/BROWSER_ARTIFACT/legacy-results/public/county-pagination-contract-c7c89-itimate-saved-list-position-chromium/trace.zip`
under the sibling Batch 11 evidence root. SHA256:
`9fecbb8deb91a7b4b2a74d0f90aa70b61053c951fba053babed05c4b5f068bc4`.
R/`HOSTED_RAPID_TIMELINE.json` records the extracted call times. After the rapid
Back snapshot, recorded Y values move 905 → 895 → 879 → 851 → 722 → 152 → 0.
This records the symptom, without identifying its cause.

## Fresh bounded observations

The native-history probe (`native_history_probe_v1.cjs/.json/.log`) ran 10 smooth
and 10 instant same-document controls with a 72 ms forward/Back interval. All
20 retained the saved-position contract. This is synthetic HTML on macOS ARM64
Chromium 145.0.7632.6, through bundled Playwright 1.62.1. It neither reproduces
the app failure nor accepts the held source. Native history alone was
insufficient in this probe.

`trace-inspection-v1/` and `trace-inspection-v2/` retain original trace hashes,
CLI commands and frozen snapshot queries. The original traces identify Linux
Playwright 1.58.2. Their inspection renderer is explicitly the bundled 1.62.1
CLI and an owned revision alias to existing Mac Chromium 145. This is historical
DOM inspection, not a live execution of the original app or hosted runtime.
Missing JavaScript response bodies prevent a complete original-runtime replay
from the traces alone. The budget trace's two 404s are local Vercel telemetry
scripts; no captured application-chunk HTTP failure established the cause.

Ranked rapid-return hypotheses remain native smooth restoration continuing
toward a forward target, a late Next scroll/focus action, and temporary document
height clamping. Next 15.5.27 source shows scroll/focus handling and native
history restoration boundaries, but it is not evidence that those paths caused
this failure: [layout router](https://raw.githubusercontent.com/vercel/next.js/v15.5.27/packages/next/src/client/components/layout-router.tsx),
[smooth-scroll handling](https://raw.githubusercontent.com/vercel/next.js/v15.5.27/packages/next/src/shared/lib/router/utils/disable-smooth-scroll.ts),
[restore reducer](https://raw.githubusercontent.com/vercel/next.js/v15.5.27/packages/next/src/client/components/router-reducer/reducers/restore-reducer.ts).
No global CSS/layout change was made from these hypotheses.

## Local checks and limits

At merge `33612990…`, the unchanged canonical Chromium list collected **329**
cases with the same **11** fixmes. Exact descriptors and annotations are in
R/`runs/merged-browser-collection/stdout.log`. Declared disjoint browser cohorts:
public 275, users 4, operations 6, overview-audit 5, etl-ui 28, coordinator 11.
The separate publication cohort is 21; do not count it as additional cases in
the original 329 inventory.

The actual `.github/scripts/run_backend_tests.py --collect-only` completed both
package-owned cohorts: backend **17,273**, legacy **336**, total **17,609**.
R/`backend-collection-current/` preserves full nodeids, package identities and
canonical summary. Collection is not full backend execution.

The unchanged archive hostile controls, publication guard boundaries, mounted
API advertisement guard, invented-national-figure guard and zero-fallback guard
executed **2,528 passed**, no failures/errors/skips, on Python 3.13.9 and
SQLAlchemy 2.0.54. Raw output and JUnit are in
R/`runs/merged-archive-controls-current/` and `merged-archive-current.xml`.
Earlier held attempts with missing FastAPI/uvicorn are preserved as setup
failures, not causal reds. A pytest cache was also created by the earlier
recorder; its bytes were relocated to owned external evidence. Final commands
disable cacheprovider and keep all output external. Exact current/minimum
SQLAlchemy 2.0.23, normal/optimized, archive CLI and final committed-source
replays are recorded separately in R/STATUS and the final run receipts.

The initial v3 recorder is execution-only and has confirmed provenance/output
tampering gaps; it does not certify acceptance. R/`adversarial-recorder/`
contains executed isolated controls. v4 closes those cases but initially allowed
a child to move its output directory and replace it with a symlink. v5 retains
the old producer bytes and adds pre/post directory identity and ancestor checks.
All versions remain diagnostic tools. Their cleanup covers the exact owned
process group; a detached `setsid` descendant is outside that proof. Final raw
outcomes require independent JUnit/output/source reconciliation.

## Runtime and cleanup blocker

The Data volume fell to approximately 117 MB free, then refused writes during
setup. Docker subsequently reported that Docker Desktop could not start;
later readback hung and its exact owned CLI was stopped. Only redundant owned
source tar archives (after literal extracted-copy verification) and the unused
owned Linux Node download were removed. Historical failures, producer bytes,
original source inventories and trace ZIPs remain intact. No global engine
restart or peer cleanup was attempted. A storage/alternate-volume question was
sent to the user; it is still pending.

Owned container **`batch12-browser-linux`**, ID
`e11280d89083cfb8ea1b1e54f6c3794b557982fd0d918b75259a8348de617f6a`, label
`audit_app.owner=batch12-browser-01a130e3`, was created with the pinned
Linux-amd64 image digest
`6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d`.
No host ports were published and no API/UI test server started there. Its
terminal/removal/absence cleanup cannot be verified while Docker is unavailable.
Do not call that resource cleaned. Future cleanup must inspect the exact ID and
owner label first, then stop/remove only that owned container and read back its
absence. Optional PostgreSQL was never created.

## Required continuation and acceptance

1. Supply adequate owned runtime storage and restore Docker access without
   altering peer resources. Complete exact owned-container cleanup/readback.
2. Build the production app against the owned loopback fixture; verify health,
   47 county rows, actual versions, compiled API target and test detector failure.
3. Replay the unchanged original saved-position cases on held and failed source
   in the same runtime; introduce one controlled causal hypothesis at a time.
   Retain a natural red and a detector-capable red/green before repairing code.
4. Treat budget and both initial-render failures separately; no new skips,
   retries, weakened assertions/selectors or larger deadlines.
5. Coordinator reviews the actual final head and runs fresh immutable hosted
   acceptance: original full 329 browser inventory with exact old 11 fixmes,
   separate publication 21, and all seven mandatory jobs/post-test/cleanup
   checks. Earlier partially passing or cancelled runs do not accept this head.

Fresh GitHub `GITHUB_V1/` and `GITHUB_V2/` readbacks show unchanged held remote
head, accepted main, one body-only COMMENTED review and zero inline/unresolved
threads. The census finding has an existing classification/fix reply at
[comment 6102097033](https://github.com/Rodgers31/audit_app/pull/624#issuecomment-6102097033).
No fresh unaddressed review finding was found. Post-push readback and the draft
HOLD publication are recorded externally; issues remain open.

## Evidence-backed skill proposals

- Distinguish a missing prerequisite/setup failure from an original test red:
  this round's missing FastAPI/uvicorn attempts did not test the browser cause.
- Snapshot inspection can narrow a timing boundary without proving a fix:
  hidden `S:0` before and visible h1 after the original query is bounded evidence.
- Validate output directory identity again after the child, before publishing:
  the v4 child move/symlink control preserved inventory bytes and still returned
  zero until v5 added that boundary. Keep earlier tools/controls immutable.
- State process-group cleanup limits explicitly; executed `setsid` controls
  demonstrate why a zero parent exit does not prove complete resource absence.

These are proposals for coordinator consolidation. No shared skill was edited.
