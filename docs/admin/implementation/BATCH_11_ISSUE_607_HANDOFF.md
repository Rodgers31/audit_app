# Batch 11 navigation author handoff

The scoped repair removes the demonstrated asynchronous URL/table split in
County Explorer pagination and View All. It uses Next's integrated native
`history.replaceState` for client-only list state, preserving unrelated query
values (including duplicates), the fragment and history depth. No Flight
response is needed for pagination. No scroll implementation was changed.

**#601 remains open:** the historical saved~900 → returned100 failure has no
reproduced natural cause here. #607's historical naturally delivered-200 reason
also remains unmeasured. The causal red/green proves the pending-delivery
boundary this repair eliminates; it does not prove a lost internal render retry.
Coordinator owns final issue dispositions, hosted acceptance and merge.

## Source and ownership

Pinned predecessor: `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`, tree
`9d0061928c16d173859f98cb6daa5f2f591b257c`.
Implementation commit: `09fd3c150032e8595678ddf2046948651a260b96`, tree
`f3a254d87655cbba42365684f1c611cae5b1312e`.
Current source commit: `982a961a58ed3647ead6bc7900250efa7d882a94`, tree
`5ebb363b208efd159d4b4673a760f111cdd1d629`. This adds only the native-history unit
observer described below; the implementation bytes equal the implementation
commit. Earlier author browser receipts name their actual launch HEAD plus measured staged /
working source hashes. They ran before/during creation of this product commit;
the measured product bytes equal that commit. They are not relabeled as tests
of a future evidence commit. Later documentation adds no product changes.
The external append-only postcommit binder records actual final remote HEAD/tree,
complete tracked-source inventory and correspondence to the tested inputs.

Owned product hunks:

- `frontend/app/counties/CountiesPageClient.tsx`: `replaceListQuery`,
  `CountyRankingsTable.setPage/setShowAll`, and unused import removal.
- `frontend/e2e/county-pagination-boundaries.spec.ts`: three real-browser
  pending/failed/competing response controls.
- `frontend/e2e/county-pagination-contract.spec.ts`: three query/hash/history,
  deep-link/filter and saved-position back/forward controls.
- `frontend/__tests__/countiesUrlStateSsr.test.tsx`: observe real native history
  writes while retaining all row/SSR/hydration and URL behavior assertions.
  Harness-injected navigation uses the captured original method, so negative
  no-write controls observe only product writes; positive controls also assert
  actual URLs and absence of server-router calls.

The original smart-back source SHA256 remains
`0a39e8b46d52cbc8bb932048c847f77488cb4e60fc1c32fb21b07c58c58160ae`.
No package, lock, native/build/Tailwind configuration, template/style, financial
fixture, navigation trail or scroll source changed. Primary checkout remained
read-only. The #494 owner must integrate only after an explicitly accepted
navigation HEAD/tree transfer; pinned-lock lane acceptance and later combined
acceptance remain separate. The shared SPEC and skill files were read-only.

## Actual controls and limits

| Run | Actual result | Meaning |
| --- | --- | --- |
| Untouched original scroll case | 100 passes | Local diagnostic positive; neither historical natural failure reproduced |
| Bounded history/layout/scroll probe, real200 released after page2 rows | 40 passes | Alive probe, maximum176 events under5000 cap; successful native-auto smooth restoration |
| Original unchanged prefix, real200 held pending | 3 failures at original line38 | `/counties` with ten rows showing11–20; before the original test's scrollTo/detail/back steps |
| Same original pending input after repair | 3 passes | No pagination Flight requests; URLp2, returnedY890–894 |
| Pending/failed/competing navigation controls before repair | 3 failures | Async URL split; failed response reload; competing final mode disagreement |
| Same boundary source after repair | 3 passes | Current entry and local rows no longer depend on server response |
| Corrected pre-change query contract | 1 lost-fragment failure /2passes | Identical committed query-test bytes; erroneous first textbox selector retained separately |
| All six committed focused cases after repair | 6 passes | Duplicate queries/hash, keyboard, history/document identity, clamping/filter, saved-position back/forward |
| First full public275 attempt | 263passes /11fixmes /1budget failure | Preserved unexpected failure, not clean acceptance |
| Unchanged-launch budget selector isolation | 20 passes | Does not establish intermittent cause or replace full acceptance |
| Earlier complete six-cohort run, before unit observer commit | 318 passes /11 unchanged fixmes /0 unexpected /0 flaky | Historical diagnostic positive on its actual measured source |
| Original-table initial-render control | 40 passes | Twenty repeats of each unchanged failed case; actual982a961 dirty table snapshot, no cause established |
| Current complete cohort accounting at982a961 | 316 passes /11 unchanged fixmes /2 unexpected /0 flaky | Failed public275 plus fresh54 remaining cases; full acceptance is false |
| First explicit full Jest | 2073 passes /1 existing pending /4 failures | Four assertions required the old router transport; raw failures preserved |
| Native-history unit observer | 21 passes | Existing rows, normalization, SSR, first-commit and hydration contracts retained |
| Refreshed explicit frontend gates at current source | All passed | Lint, TypeScript,147 Jest suites /2077 passes /1 existing pending, native verification |

Original viewport1280×720, configured workers2 for public /1 for other cohorts,
zero retries. A sequential single spec can use one actual worker despite a
two-worker configuration; failures can spawn replacement workers. Bounded probes
force geometry reads and may perturb timing. The v3 recorder did not inventory
all new external probe files; prelaunch generated-source manifests separately
bind those inputs. Later v4 receipts measure known source/helper bytes before
and after. Neither setup failures nor malformed helper attempts are product reds.

The eleven unchanged fixmes, not executed:

- `charts.spec.ts`: chart legend interactive, debt segments clickable,
  county tooltips category details, chart zoom controls.
- `home-map.spec.ts`: map integrates with county slider.
- `learn.spec.ts`: video cards displayed, video modal, video category filter,
  story expansion, interactive action steps.
- `static-pages.spec.ts`: status heading.

The full current suite is the original323 unique descriptors plus six additions
(public275, users4, operations6, overview-audit5, etl-ui28, coordinator11).
Earlier complete-run passing counts were264,4,6,5,28,11, respectively; the eleven public
fixmes were unchanged. Every original descriptor appears exactly once in the
partition. The source-bound outer receipt has child_exit0, no timeout and no
source/helper/generator drift. It retains its actual pinned launch identity,
with the measured working implementation bytes bound to the implementation
commit above. Its BROWSER_TARGET_SHA=bcb5ff declaration is inert fixture metadata
and is retained verbatim. The only subsequent tracked-source difference is the
unit observer update, so that prior complete run is historical rather than
acceptance for the later snapshot. The current public run at982a961 has262 passes,11 fixmes and two unexpected
failures, retained below. The five remaining cohorts passed4,6,5,28,11 cases
using the same3610 measured tracked-source hashes; total316 passes,2 failures,
11 unchanged fixmes,0 flaky. Both outer receipts report no source/helper drift.
The first remaining-cohort attempt failed fixture startup with DuplicateTable
before any browser case. Its raw report is retained as setup failure. Only the
exact label/ID-verified owned disposable databases were reset; source/config
bytes were unchanged. A subsequent recorder invocation had an incorrect local
script path and launched no browser; that setup failure is also retained.
The fresh successful54-case execution has its own third capture identity.
The final catalogue uses that failed public run together with fresh remaining
cohorts and controls; a later clean public attempt cannot replace it. The fresh
six focused cases passed on those exact3610 source hashes. The bounded
original-table initial-render control passed20 repeats per failed case,40total;
this diagnostic positive establishes neither an internal cause nor regression
status. Its actual982a961 dirty table snapshot and byte-exact restoration
receipt are retained separately.

The one unchanged Jest pending test is `mounted reader consumes captured
PostgreSQL HTTP absence and sourced-zero states`. Native checks execute the
fixed public q8 model revision and native image/ZIP paths in the owned Node
runtime; they do not rewrite shipped embeddings or prove browser WASM inference.

## Evidence and independent review

The scoped packet is [batch11-issue-607-evidence](batch11-issue-607-evidence/README.md).
Raw failed/setup attempts, real traces/screenshots/videos, reports/logs, original
producer scripts and source inventories retain their measured identities.
The prior [Batch10 scroll handoff](BATCH_10_SCROLL_HANDOFF.md) and packet remain
unchanged; historical receipts are not attributed to this repair source.

Independent author-separate Spec, Standards and adversarial reviewers execute
controls with their own receipts. Preliminary source/control reviews are under
`batch11-issue-607-evidence/reviews/`. Fresh replays and final commit/corpus
rechecks are recorded separately when complete. The packet checker distinguishes historical integrity
from recorded local acceptance and fresh execution. The supported portable
entrypoint is `tools/replay.py`; old archive generators are identity records.
See [LESSONS](batch11-issue-607-evidence/LESSONS.md) for evidenced proposals rather
than shared skill edits.

## Unresolved browser failures and next work

The first full public attempt failed `charts.spec.ts:116` after clicking
FY2024/25 on `/budget`: the expected synthetic150B heading never appeared.
Budget/chart/test/fixture bytes retain the launch hashes; isolated launch-code
repetitions20/20 pass. Cause is unestablished. No budget edit or quarantine was
made. Complete all-state REST census excluded PRs (308issues/7pages), with
30 relevant issue and134PR body/comment matches, exact test-name search0 and
candidate full-body/comment reads. No matching leaf was found. The deduplicated
leaf will be tracked after immutable evidence publication; its actual identity
is in the draft PR and external postcommit binder. This preserves a reviewable
failure rather than attributing it to hydration without proof.

The current public failure signatures are `accessibility.spec.ts:24`,
`/counties — has exactly one h1` (immediate heading collection returned zero at
line29), and `county-response-validation.spec.ts:66`, `normal 47-county list and
legacy 001/047 detail routes remain usable` (line76 row-count locator resolved
two spans, one outside the visible main content). Both are unchanged original
cases. Neither journey clicked pagination. Their shared cause, relationship to
hydration/streaming and regression status are unestablished. No SSR/template or
original-test change was made. Complete all-state deduplication and candidate
reads found no matching dedicated leaf; the two observations will be tracked
with this causal limitation after immutable publication.

The packet verifier's default mode rejects current full acceptance. Explicit
`--integrity-only` validates the complete recorded files and counts and returns
`local_recorded_acceptance:false`; this is no browser rerun or acceptance waiver.

The next #601 experiment must observe the actual saved target, restoration clamp
limit, layout, scroll calls and focus in the historical hosted environment.
The next integration step is coordinator review/acceptance of this lane and an
explicit #494 dependency HEAD/tree integration, followed by separate combined
verification. Production activation remains #583. No hosted workflow was
enabled/dispatched and no production/provider write or paid bot request occurred.

## Owned runtime and cleanup

Local LinuxAMD64 Docker Desktop emulation on macOSARM64. Playwright1.58.2,
Chromium145.0.7632.6, official Node22.23.3 x64; actual executable hashes are in
`archives/runtime.json.gz`. Browser image digest:
`mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d`.
Owned container `batch11-navigation-linux`; PostgreSQL `batch11-navigation-postgres`
uses the same network namespace, internal55494, disposable fixture databases.
Image digest:
`public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.
No host ports were published. Assigned host13032/18032/55532 were verified free;
namespace-isolated internal cohort3141/8141 and55494 cannot occupy other lanes'
reservations. Child environments were allowlisted with inert endpoints/keys,
dotenv disabled and external backend HTTP blocked before imports.
Cleanup stops/removes only these exact label-verified owned containers after
all replays, with real readback in the external binder. Worktree is retained for
review; owned external raw outputs/caches preserve history.
