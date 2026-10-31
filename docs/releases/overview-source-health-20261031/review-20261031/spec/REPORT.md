# PR863 — independent merge-gate and assertion-disposition review

**Scoped pass.** The exact merge coordinator passes50 normal controls and50 true Python `-O` controls:100 passes, zero failures/skips and zero external GitHub calls. The optimized-assertion finding is refuted for the retained default pytest command shapes. The separate live-verification request remains a valid deployment gate. The root REVIEW.md classifications and counts match the inspected and executed evidence; no material mismatch was found.

## Exact merge helper

Helper SHA256: `9da17d2dbd2ea18a232d2b9a3aca8020de044e6b124c93f64c1b90e24f1ca96f`. Compared with prior accepted helper `d27f1da42207237a68c066498016ccc900b0f2f1ed930b159c6ac21e7dc0401e`, its only two changes are the validation/argparse allowlist861/862→863. The frozen helper, census reader, retained census and three historical runners all match before/after hashes. The runners also match their committed bytes at review head `253ab29978fdb546b001381861eb767fe84b633f`.

`test_merge_guard.py` imports that exact helper and calls `coordinate` with controlled census/run ports. Any uninjected subprocess call is forbidden. The fake run port verifies exact normal/admin argv and the pinned `--match-head-commit`. No CLI merge, GitHub request, production access or deployment is performed.

Each mode executes12 workflow controls and19 bad-census states at both initial and late boundaries. Positive paths prove ordinary success, ordinary merge attempted before override, expected policy refusal without opt-in, explicit override only after a second census, and rejection of a merely truthy nonboolean opt-in. Unexpected normal errors, failed override and census exceptions refuse.

Bad states cover draft/head changes, new review body, pending bot requests in both views, unresolved threads, top/nested pagination gaps, incomplete review/comment/inline counts, reviewer/aggregate changes-requested, failed/pending/unknown checks, closing references, boolean counts and pending review state. Every late control changes the second census after the first policy rejection and proves no admin command occurs. Wrong-PR allowlist use refuses. Exact call traces and all100 unique mode/case identities are retained.

The retained initial census was actually draft. The first48-case-per-mode attempt inherited that state, so the helper correctly refused before commands and the harness's intended positive/late expectations failed. Those attempts are preserved under `attempt-1-draft-fixture/` and not credited as acceptance. The corrected synthetic ready baseline explicitly sets draftFalse and includes an explicitly classified resolved fixture thread. Actual draft refusal is separately tested at both boundaries. Synthetic accepted material is a test input, not approval of the live PR.

These controls certify the coordinator behavior under the injected census contract, not live merge permission, actual current review readiness or an atomic review-state lock. A real caller still needs the fresh complete classified census at the actual merged head.

## R1: optimized-assertion finding refuted

I executed all three exact historical argv-builder bodies, substituting only the project test selection/output with an owned calibration module while retaining their optimized pytest entrypoint. Every constructed command uses default `python -O -m pytest`; none selects `--assert=plain`.

For each builder, the real optimized child surfaces two deliberately false assertions: one directly in a collected test and one in a helper inside that collected module. The explicit runtime canary passes only when `sys.flags.optimize == 1`. Each original runner propagates child exit1. Across three shapes this is six **expected assertion failures** and three runtime-canary passes, not an ordinary all-green test suite. No full application selection is credited to these calibration runs.

As a negative calibration, deliberately selecting `--assert=plain` under-O makes the same two false assertions disappear; all three cases then pass. That false-green result is explicitly not acceptance. It demonstrates that the probe distinguishes rewriting from the unsafe plain mode.

I also read Standards' report/receipt and parsed its five actual XML files:70 outcomes,66 passes and4 intended assertion failures, zero errors/skips. Its original31-case module plus runtime check passes32; the one-literal26→27 mutant fails at the intended helper assertion with31 other passes. Those are inspected peer outcomes, not additional Spec execution credit.

The disposition is bounded: ordinary unrewritten imported-module assertions can still disappear under-O. Default pytest rewriting preserves these collected modules and same-module helpers, while application code remains optimized. Historical runner/application changes are not warranted for the blanket claim.

## R2, artifacts and cleanup

Live provider integration, actual authenticated Overview recovery, advice/CORS, installed hashes, source observations and all OFF controls/counts/processes remain deployment checks. Offline proof is not a live cold-cache observation. The reviewed disposition correctly avoids claiming such a transition from a successful reload and forbids manufacturing an outage or weakening TLS/authentication. This Spec review performs none of those production actions.

`FINAL-RECEIPT.json`, `CASE-LEDGER.json`, `SOURCE-AFTER.json`, `REVIEWED-DISPOSITION.md` and the command/output/exit/XML receipts bind the result. All execution used owned cached offline Docker, one CPU/512MiB/128PIDs; no installs, providers, paid services, credentials, shared containers or control changes. `CLEANUP.json` records zero remaining owned containers. Previous sealed release evidence remains untouched.
