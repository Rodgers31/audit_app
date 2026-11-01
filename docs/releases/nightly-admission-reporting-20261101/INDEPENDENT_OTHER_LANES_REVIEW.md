# Independent UI, manual publication and media acceptance review

This document records review of companion candidates from the same work batch. The UI and notification probes require those reviewed changes; they are not standalone acceptance commands for this PR alone. Each PR has a disjoint file set and its own directly relevant tests. The reviewed UI source is retained at commit `0bc78394a3bbb638ab1fd26aa103ece2f47c6a51`; no companion runtime dependency is introduced by the media/notification changes.

Reviewer: nightly reporting lane, 1 November 2026. No actionable product defect found in the reviewed candidate. This is local independent review; external launch gates remain open. No files owned by the UI or media lanes were edited. [Source identities and fixture hash](independent-review-source.json) bind this review to the candidate.

## Rendered UI and actual command invariants

I read the actual composer gates, new delivery-readiness hook, media availability branch, publication receipt checks and mutation idempotency path. I authored an independent external Jest fixture that renders the real composer and real hook through React Query. Its retained [source](independent-worker-readiness.test.tsx.txt) is documentary text so it does not alter another lane's test discovery. Every Axios call is intercepted.

[Executed result](independent-ui.txt): **11 passed, zero skips**, 1.085 seconds. This is separate reviewer-authored coverage, not an extra count to add to the author's broad cohort. It verifies:

- Missing worker; missing or invalid heartbeat/scan; timestamps 60 seconds in the future; and expired idle scan all keep Publish now disabled **after actual rendered validation has completed**. Clicking the disabled control sends no publication command. The reason remains visible in the readiness region.
- A fresh worker permits an explicit human publication request with the exact saved `expected_version`, `revision_id` and acknowledged warning list. No implicit approve or controls request occurs.
- A queued receipt displays queue acceptance without a remote success link.
- Worker unavailability still permits an explicit future schedule. The request binds the exact local time, Nairobi timezone, UTC offset and revision. A matching receipt is accepted; a mismatched scheduled time is rejected without claiming acceptance.

The first external-fixture attempt could not resolve `react/jsx-runtime` from `/tmp`; [the setup failure](independent-ui-setup-failure.txt) retains zero executed cases. Adding an explicit existing `frontend/node_modules` module path corrected that prerequisite. No package was installed or manifest changed. Final command from `frontend` with the existing Node 24.22.1 directory prepended to `PATH`:

```sh
node node_modules/jest/bin/jest.js --runInBand \
  --roots /tmp/nightly-other-lanes-review-20261101 \
  --modulePaths /Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend/node_modules \
  --runTestsByPath /tmp/nightly-other-lanes-review-20261101/worker-readiness.independent.test.tsx
```

The retained fixture can be copied back to that owned `/tmp` path before replay. No app build, browser server or provider call was needed for this review.

## Media cold reconstruction and mounted manual API

I reviewed both new Python modules and executed them independently in the immutable local exact-package image recorded in the source receipt, with networking disabled, read-only mounts and bounded CPU/memory. [Executed result](independent-media-manual.txt): **6 passed, zero skips**, three existing dependency deprecation warnings, 2.39 seconds. No test-local switch survives the disposable fixture.

The cold reconstruction covers a healthy restore and missing/corrupt original controls. It captures original bytes and SHA256 before service output, logically exports real rows, destroys the primary in-memory engine, clears primary storage, builds a new database and new object store from retained files, constructs a new inspector and re-inspects the reconstructed bytes. Independent bytes/hash/dimensions agree. Historical references block archive, quota remains reserved and the unknown browser-write grant remains held. Missing/corrupt restored originals refuse preview; no delete/finalize operation is inferred from restore.

The mounted API cases independently exercise upload idempotency, inspected ready media, preview, a manually created draft and exact destination validation, optional submit/approve review, publishing-paused refusal without attempts, and a fixture-only explicit controls action followed by human queue acceptance. Idempotent replay returns one authorization and zero provider attempts. Default automation remains off; disabled media runtime grants no upload or publication activation.

The final command used the source and environment mounts documented in the media lane's local acceptance report, plus these selections:

```sh
docker run --rm --network none --cpus 1 --memory 1g --pids-limit 128 \
  --read-only --tmpfs /tmp:rw,nosuid,size=256m \
  --mount type=bind,src=/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/backend,dst=/app,readonly \
  --mount type=bind,src=/Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/security-final-866-867-20261101/python-author,dst=/evidence,readonly \
  --workdir /app --env PYTHON_DOTENV_DISABLED=1 --env PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /evidence/docker-prod-test-env/bin/python \
  pr863-python-patch-parity:local -m pytest \
  tests/social/test_media_cold_restore_acceptance.py \
  tests/social/test_manual_media_workflow.py -q -ra -p no:cacheprovider
```

This verifies synthetic SQLite/object-store compatibility and mounted HTTP contracts. It does not verify production R2/PostgreSQL restoration, independent custody, host video binaries, delivery worker activity, sustained costs or provider publication. Publishing, uploads, all workers and financial generation remain outside this review's authority; no deployed setting was read or changed.

## Final source and launch-gate refresh

All nine previously reviewed product/fixture source hashes remain identical to the independent review snapshot, including the simplified media copy. Those prior controls require no broad rerun. The subsequent schedule-control addition is reviewed and narrowly executed below. The generated-draft browser scenario was inspected: it selects inspected media from the default mobile Preview, saves a new revision, validates that revision and sends the explicit human command with exact version/revision and facts/source attestation. The final mock queued post now binds its authorization revision to the new saved revision; its due/UTC/requested-local-time and next-action metadata are also explicit. The final author browser receipt records six groups, 49 requests, zero external requests and zero page errors; its relevant source-manifest entries match the current runner and runtime. This is inspected author evidence, not another reviewer browser execution.

The parent `LAUNCH_GATES.md` was reviewed against the actual mounted-API fixture, browser receipt, PostgreSQL JUnit files and read-only production observation receipt. One documentation precision finding was corrected: “must remain OFF” is now an explicit operating requirement, and the read-only section distinguishes observed worker unavailability from a fresh process inventory, and the prior financial OFF receipt from an environment readback not performed here. I did not independently inspect production in this review.

The eight parent PostgreSQL JUnit file hashes match their summary: 299 normal and 302 optimized for the overlapping principal selections, 36 owned-media cases per mode, seven retirement cases per mode and two operator cases per mode; all report zero failures, errors or skips. These are inspected coordinator execution receipts, not reviewer reruns, and are not additive counts. The extra three optimized principal cases are the mounted manual API module, whose separate independent six-case manual/cold execution remains above.

Runtime source and the corrected launch-gate document are approved for separate draft review at the recorded base. This approval authorizes no merge, deployment or activation. [Refresh identities](independent-review-refresh.json) record the current document hash and unchanged runtime source identities; the original independent execution receipts remain unchanged.


## Schedule-control completion refresh

The coordinator subsequently required the same immediate-delivery rule for the existing **Publish unsent now** action. I independently read the new `SocialScheduleControls.tsx` change: it reuses the readiness hook, guards the command handler as well as the disabled button, and attaches the worker explanation through `aria-describedby`. The future reschedule branch does not inherit this immediate-delivery gate. Queue retry/resume code and backend application code are unchanged.

[Reviewer-authored rendered cases](independent-schedule-refresh.txt): **8 passed, zero skips**, 1.793 seconds. The documentary [fixture source](independent-schedule-readiness.test.tsx.txt) renders the actual schedule component. Absent, invalid, far-future, stale, stopped and missing-scan evidence prevents an immediate send; active readiness expires while the component stays open. Missing worker evidence still permits an actual future reschedule request with exact publication/version/civil-time guards and an unchanged authorization revision.

[Existing affected module](affected-schedules-refresh.txt): **11 passed, zero skips**, 1.064 seconds. This separately re-executes preservation of an already successful account, explicit cancellation availability and the existing schedule-response checks. These selections overlap conceptually and are not additive to author broad counts. The [refresh receipt](independent-review-refresh.json) now includes the additional component/test source hashes. No actionable product issue was found; approval remains limited to draft review.


The final author freeze was read back after both precision findings were resolved. The selected source-manifest entries match the current composer, media control, readiness hook, schedule control, reusable fixture, affected schedules tests and browser runner. The browser fixture directory was removed after execution. Final identities and browser receipt digest are recorded in `independent-review-refresh.json`. No unresolved review finding remains. Later positive-test fixture or receipt-only updates do not change this runtime approval; a runtime source change requires a new refresh.

## Coordinator media addendum review

`COORDINATOR_ACCEPTANCE.md` and its four retained receipt digests were independently checked. [The reconciliation](independent-media-coordinator-review.json) maps every original skipped function to passing later JUnit cases: eight PostgreSQL cases pass in both assigned principal modes; nine real-video cases pass among 21 host compatibility cases; the combined cold/manual receipt contains six passing cases. All four recorded receipt hashes match. The additional media groups remain 36 ownership/integration, seven retirement and two operator cases per mode, with no skips. These group counts are not added to overlapping cohorts.

The addendum correctly retains the distinction between the production-package Python 3.12.16/SQLAlchemy 2.0.55/Pillow 13 container and the host Python 3.14.0/SQLAlchemy 2.0.46/Pillow 12.1.1 video compatibility selection. An independent [read-only local runtime check](independent-media-host-runtime.txt) confirms the latter versions and installed ffmpeg/ffprobe 9.0.1; it does not re-execute the parent video selection. The 17 original skips remain disclosed in the original broad receipt. A zero-selected preliminary `-k native` command is correctly excluded from passing evidence.

The media addendum's counts and limits are approved for draft review. It claims neither native production parity nor deployed video/custody/restore/provider acceptance. No external operation or product edit was performed for this addendum review.


## Accepted-command status synchronization correction

The coordinator's later actual-browser review identified another runtime issue: an accepted command advanced the post version while keeping the immutable revision, and the clean composer falsely displayed a newer-revision/local-edit conflict. The earlier composer source approval is superseded by this section and its latest hash in `independent-review-refresh.json`.

I reproduced the defect independently through a real rendered composer: [red receipt](independent-sync-red.txt), **one executed assertion failure**, with five deliberately unselected cases. The new effect was then read directly. It only advances `post` metadata for the same post/revision and matching saved/local/remote fingerprints, with no dirty input, command, archive or media operation in flight. It does not call the input/review-resetting adoption helper. The generated auto-validation effect excludes an already queued clean publication so it cannot erase accepted-command messaging or restart publication work.

[Independent final boundary execution](independent-sync-green.txt): **6 passed, zero skips**, 1.592 seconds. The retained [reviewer fixture](independent-status-sync.test.tsx.txt) verifies clean accepted version 2→3 synchronization and preserves explicit conflicts for dirty input, a changed revision, conflicting same-revision content and a different post ID. An in-flight validation defers reconciliation until settlement and does not reuse the old version's validation. The first replay used the old alert wording, then one query-observer assertion ran before React Query notified the render; both [copy-expectation](independent-sync-copy-expectation-failure.txt) and [notification-timing](independent-sync-notification-timing-failure.txt) harness failures are retained separately. Matching both truthful old/new copy and awaiting the actual observer corrected the harness without changing runtime source.

[The affected author modules](affected-sync-media-refresh.txt) independently rerun here report **9 passed, zero skips**, 1.346 seconds on the final copy refresh. This includes the actual initiate → intercepted browser PUT → pending completion flow: a same-revision metadata refresh cannot rebase during inspection, and completion retains the selected asset/alt text and dirty local state without a save. The generated accepted-command case preserves human attestation and sends only validation followed by explicit publication. These results overlap author coverage and are not additive totals.

No further product issue was found. The corrected runtime and coordinator media addendum are approved for draft review. A final author browser/manifest refresh and the coordinator's own production build remain separately owned acceptance steps; no external operation is authorized.


The final generated helper copy was also reviewed and the same two affected modules rerun: nine pass with zero skips in 1.346 seconds. The queued wording requires both a requested due time and the matching immutable revision; busy and dirty editor states take precedence. It introduces no extra state transition, effect or request. The earlier nine-case pass is retained separately in `affected-sync-media-before-queued-copy.txt`. The latest composer/test hashes in `latest_status_sync_refresh` supersede the earlier source identity. No unresolved product finding remains.


## Final acceptance bookkeeping — frozen candidate

Approved the final frozen local candidate for separate draft review, with no unresolved findings. [Final identity and count receipt](independent-final-acceptance.json) verifies all **17 source hashes**, agreement between `VALIDATION.json` and `source.json`, the production-mode build-log digest and completed compile/static-generation output, and the author Jest result of **47 suites / 750 passed / zero skips**. The build retains inert-localhost API failures and is not deployed or live-data acceptance. No test or build was rerun for this bookkeeping step.

The final browser receipt has **six scenario groups / 49 intercepted API requests / zero external requests / zero page errors**. I visually inspected the actual queued desktop and generated mobile PNGs: approved post versions 2 and 3 respectively, queued acceptance/results with no false newer-version/load-current prompt, and retained generated attestation with truthful publication-requested text. Their byte digests are recorded. The additional seventh clean-status fixture was read: a generated ready authorization without a due timestamp still validates the refreshed version; its execution belongs to the author 750-case receipt.

Both retained combined manual/cold JUnit files independently parse as **six tests, zero failures/errors/skips** in normal and optimized modes. All **five** current coordinator receipt digests match, including the added optimized XML. The prior 17-skip mapping and compatibility/production limits remain unchanged. This final bookkeeping resolves the earlier pending author browser/manifest/build references and supersedes earlier composer/test identities.

Approval is for disjoint draft review only. It authorizes no merge, deployment, activation, external send/upload, worker or financial generation.
