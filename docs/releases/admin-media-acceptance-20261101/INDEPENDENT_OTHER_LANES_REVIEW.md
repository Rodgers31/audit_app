# Independent UI and nightly review — 1 November 2026

Source authority: read [SOURCE_EVIDENCE_INDEX.md](SOURCE_EVIDENCE_INDEX.md) and its scoped reconciliation receipt first. Source JSON files from earlier review stages are preserved historical captures, not interchangeable current-checkout manifests.
This document records review of companion candidates from the same work batch. The UI and notification probes require those reviewed changes; they are not standalone acceptance commands for this PR alone. Each PR has a disjoint file set and its own directly relevant tests. The reviewed UI source is retained at commit `0bc78394a3bbb638ab1fd26aa103ece2f47c6a51`; no companion runtime dependency is introduced by the media/notification changes.

Verdict: **no remaining actionable product or workflow defect found in the reviewed source**. This review did not edit another lane's product, workflow or tests. Scope and exact file SHA256 values are retained in [review-start identity](independent-review-source-before.json) and [review-end comparison](independent-review-source-after.json); The browser fixture added its generated mobile scenario during review; the final source was re-read and passed `node --check`, with its refreshed SHA256 and disposition preserved in the review-end record. The other reviewed files stayed unchanged. The coordinator must refresh this comparison if later fixes change a reviewed file.

This is independent source/fixture review, not deployed acceptance, GitHub mutation or permission to enable any workload. No external API or real credential was used. The review does not resolve #767; the coordinator's latest read-only support observation still has no human provider resolution.

## UI and mounted API

Reviewed `useDeliveryWorkerReadiness.ts`, `SocialComposer.tsx`, `SocialMedia.tsx`, `manualPublicationBrowser.mjs`, the new UI tests and `test_manual_media_workflow.py` against the actual diff before execution.

- [38 deterministic worker-readiness challenges](independent-worker-readiness.txt) execute the **actual TypeScript hook**, transpiled with the installed TypeScript compiler. [The retained probe](independent-worker-readiness.cjs) supplies minimal state/effect/timer/visibility lifecycle and an independent controlled clock. It tests absent/null worker, stopped/stale/unknown states, absent/malformed/far-future heartbeat and scan, each active 45-second / idle 150-second boundary, 5-second tolerated versus 5.001-second rejected future skew, timer expiry while open, visibility refresh after clock advance, replacement fresh status and effect cleanup. It copies no hook logic. This is deterministic hook logic evidence; it is not a browser timing benchmark.
- [Two authored UI suites](independent-ui-authored-tests.txt): **11 passed**, no skips. Actual composer and media components render through QueryClient and mocked API boundaries; tests cover visible controls, status/account/worker holds, elapsed freshness, permitted future scheduling, queued-only publication receipt, media-unavailable copy and server-required human attestation.
- [Independent mounted API and strengthened cold restore run](independent-mounted-api-and-cold-restore.txt): **6 passed**, no skips, on the literal production package set plus isolated test overlay in a network-disabled, read-only Linux container. Three coordinator cases exercise actual API media→draft→validation→optional submit/approve→explicit inert control update→idempotent human queue acceptance. Paused publication rejects first; zero publish attempts and no fabricated remote success are asserted. Three cold-reconstruction cases independently rebuild DB/storage/inspector, preserve historical references and held unknown capacity, and refuse missing/corrupt restored originals.

Code review confirmed that immediate publishing checks `canPublishNow` both in the button and handler, while future scheduling retains the existing independent human authorization path. Publish readiness does not enable a control. The publish command continues to bind exact version/revision/warning acknowledgments and server checks. The new visibility and messages preserve the existing pending-media save/validate/publish hold.

`manualPublicationBrowser.mjs` was independently inspected, not rebuilt or rerun by this lane, to avoid duplicating the owner's browser build. Its production-build fixture replaces auth with inert local auth, binds loopback app/API origins, intercepts API operations and aborts other origins, checks unchanged retry key/body, refuses a malformed queued receipt, and closes the browser/server in `finally`. The supplemental generated mobile scenario checks initial Preview, visible library media, saved-revision validation and exact revision/version/attestation in the human publication command; it introduces no external request. Its test receipt at `../admin-publish-workflow-20261101/browser.json` records six checks, zero external requests and zero page errors; those are the UI author's execution, not a second independently executed browser acceptance. The independent executions here are the hook, rendered Jest components and mounted HTTP APIs.

## Nightly notification helper and wiring

Reviewed the actual `.github/workflows/seed.yml` diff and `.github/scripts/seed_notifications.cjs`. The notify job includes all seven direct prerequisites, including database admission. The reporting step runs with `always()`, receives JSON through environment values, awaits the required helper, and performs no writer admission. Existing accepted source-revision and activation guards were not changed by the inspected diff.

- [Authored notification tests](independent-nightly-authored-tests.txt): **17 test methods passed**. They execute the workflow-selected script, enforce actual direct-needs visibility and job/step selection, and intercept every GitHub method. These methods include repeated subcases; this count is not added to the independent scenario count below.
- [95 independent scenarios](independent-nightly-probes.txt) execute the **actual workflow-selected async script and imported helper**. [The retained probe](independent-nightly-probes.cjs) parses the current YAML, validates the seven direct dependencies/environment/wiring/pinned checkout, and intercepts all GitHub API methods. Cases include every job with failure/cancelled/pending/empty/null/array/object/numeric result; absent dependencies; malformed JSON/top-level shapes; absent/malformed bootstrap plan; missing/partial/malformed health evidence; database cancellation with blocked descendants; seed failure with unexpectedly skipped validation; intentional exclusions; same-attempt deduplication versus later-attempt update; full 100-item lookup, multiple managed incidents, malformed lookup response and list/create/update failures. No issue/comment was created externally.

Observed behavior: failed or unknown prerequisites produce a visible non-success summary and managed incident; intentional disabled validation/bootstrap/preview exclusions do not independently page; validation skipped after admission succeeds and seed fails remains unexpected. Same retained run-attempt marker suppresses duplicate update/create, a later attempt updates the existing managed issue, and ambiguous/full lookups refuse instead of inventing a second incident. Success never auto-closes a managed pipeline incident or certifies source freshness/publication.

The helper's bounded deduplication concerns the managed incident returned in its one at-most-99-result lookup and current run-attempt marker. It is not an atomic multi-writer GitHub transaction or a historical ledger of every prior report; the unchanged workflow-wide seeder concurrency guard remains relevant.

## Commands and prerequisite transparency

Run the two retained independent probes from repository root using the installed audited Node runtime:

```sh
/Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/runtime/node-v24.22.1-darwin-arm64/bin/node docs/releases/admin-media-acceptance-20261101/independent-worker-readiness.cjs
/Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/runtime/node-v24.22.1-darwin-arm64/bin/node docs/releases/admin-media-acceptance-20261101/independent-nightly-probes.cjs
```

The rendered UI command ran from `frontend/` with a deliberately minimal environment and Node 24.22.1 on PATH:

```sh
node node_modules/jest/bin/jest.js --runInBand __tests__/admin/social/manual-publication.test.tsx __tests__/admin/social/composer-media-integration.test.tsx
```

The six backend cases use the complete network-disabled Docker command in [LOCAL_ACCEPTANCE.md](LOCAL_ACCEPTANCE.md), selecting only `tests/social/test_media_cold_restore_acceptance.py tests/social/test_manual_media_workflow.py`.

The authored nightly driver ran with `/opt/homebrew/opt/python@3.13/bin/python3.13 .github/scripts/tests/test_seed_notifications.py -v`, audited Node24 on PATH and `PYTHONPATH=/Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/python/envs/backend/lib/python3.12/site-packages` supplying the already installed pure Python YAML loader. This driver invokes the actual Node workflow script; it does not claim Python production parity or install packages.

Two original setup failures are preserved: [missing YAML in the initially selected host driver](independent-nightly-driver-setup-failure.txt) and [unavailable Node `yaml` module in the initial probe](independent-nightly-probe-setup-failure.txt). The former was corrected by using the existing pure YAML package; the latter by using installed `js-yaml`. Neither setup failure ran the intended negative boundary and neither is counted as a passing rejection control. Final reruns above pass unchanged product/workflow source. `git diff --check` passed.


## Final immediate-delivery gate refresh

The final owner change also applies the shared worker-readiness hook to `SocialScheduleControls`'s **Publish unsent now** path. The fresh diff was read before execution. No actionable defect was found: the button and `change(false)` handler both refuse unavailable worker evidence; future rescheduling uses the existing independent path, and cancellation remains available in the parent composer.

- [Affected rendered suites and schedule contracts](independent-final-schedule-tests.txt): **34 passed**, four suites, no skips, 2.38 seconds. This selection overlaps the earlier 11-test UI run and is not an additional disjoint count. It includes schedule receipt/identity guards, successful independent destinations, stale/stopped/unavailable immediate holds, accessible explanation, future rescheduling and cancellation.
- [16 independent direct-handler scenarios](independent-schedule-handler.txt) execute the actual component **and actual readiness hook**, transpiled with installed TypeScript and minimal deterministic state/JSX adapters. The [probe](independent-schedule-handler.cjs) invokes even the disabled immediate button callback. Fresh active/idle reports reach the inert publish-now command; absent/null/stale/stopped/unknown worker, malformed/missing timestamps, >5-second future skew and expired timestamps do not. In each held case, the future reschedule handler still reaches the intercepted command with unchanged post/publication version guards. No mutation adapter sends a request. The separate 38-case hook probe supplies timer/visibility/threshold coverage.
- [Final-refresh before](final-refresh-source-before.json) and [after](final-refresh-source-after.json) hashes show no source drift during this refresh. [Final reviewed source](final-reviewed-source.json) consolidates the reviewed helper/wiring, UI, workflow test and restore fixture identities. All findings are cleared for this source snapshot; later source edits require another refresh.

The updated `LAUNCH_GATES.md` production-readback wording was independently re-read. It correctly limits the current rendered observation to publishing/media/account holds and unavailable worker evidence, and identifies financial-OFF/process inventory as prior separately retained receipts. No fresh financial-generation environment or host process census is inferred. The latest owner browser receipt has six groups/49 intercepted requests and zero external requests/page errors; it remains the owner's browser execution, not an independent reviewer rebuild.

The refresh used the same minimal Node24 environment as the earlier UI command, with this selection:

```sh
node node_modules/jest/bin/jest.js --runInBand __tests__/admin/social/schedules.test.tsx __tests__/admin/social/schedule-contract.test.ts __tests__/admin/social/manual-publication.test.tsx __tests__/admin/social/composer-media-integration.test.tsx
node docs/releases/admin-media-acceptance-20261101/independent-schedule-handler.cjs
```

The first command runs from `frontend/`; the second from repository root. `git diff --check` passed. No product source changed in this review lane.


## Late clean-status reconciliation review

Classification: the coordinator's screenshot finding was **valid**. A publish request can advance the saved post version while keeping the immutable content revision unchanged. The old local version comparison then displayed a content-conflict warning to a clean composer. The owner repaired that distinction; this reviewer changed no product code.

The final effect was independently read: it adopts only a strictly newer same-post/same-revision snapshot with identical `draftFingerprint` for both the local input and incoming snapshot, while the composer is clean and idle. It checks command/busy state and synchronous command/archive/media ownership refs. It updates only `post`, preserving the person's input, attestation and other review state. Different identity, content or revision retains explicit conflict review. Warning copy now distinguishes a saved post version from its content revision.

The generated flow also avoids redundant automatic validation after a clean publication has a requested due time and displays that delivery was requested; an approved ready authorization without a requested due time still validates the refreshed version before human publication. Neither path enables generation or queues a publication automatically.

- [Independent rendered challenges](independent-composer-metadata.txt): **7 passed**, zero skips, 1.36 seconds. [Retained independent cases](independent-composer-metadata.spec.tsx) execute the real composer/query hooks with inert API responses: clean metadata adoption, dirty text, changed revision, changed content with unchanged revision, different post identity, pending media callback ownership and in-flight validation. No publish/send request is issued by these probes.
- [Five affected authored suites](independent-status-sync-affected-tests.txt): **62 passed**, zero skips, 5.077 seconds, including real pending-upload/component guards and generated human-publication review preservation. The owner then appended an additional unscheduled-ready-authorization test; the [final clean-status suite rerun](independent-status-sync-final-suite.txt) passed **7 tests**, zero skips, 1.412 seconds and binds that final file separately. These overlapping selections are not summed into one run.
- The original [source-start](status-sync-review-before.json) and [source comparison](status-sync-review-after.json) retain the test-only change during this review; runtime source remained stable. Final identities are consolidated in [final-reviewed-source.json](final-reviewed-source.json).

The independent probe initially needed an explicit frontend `node_modules` search path because its file is retained under documentation. That [zero-test setup failure](independent-composer-metadata-setup-failure.txt) is preserved. The first executing probe also asserted cancellation readiness before React Query had rendered the incoming version; the [original assertion failure](independent-composer-metadata-preready-assertion.txt) is retained. The probe now waits for the independently visible `approved · version 2` badge before its readiness assertion; all seven cases pass against unchanged product source. Neither failure is relabelled as a product defect or a passing rejection control.

Reproduction from `frontend/` uses the same minimal audited Node24 environment as above:

```sh
node node_modules/jest/bin/jest.js --runInBand --roots "$PWD" "$PWD/../docs/releases/admin-media-acceptance-20261101" --modulePaths "$PWD/node_modules" --runTestsByPath "$PWD/../docs/releases/admin-media-acceptance-20261101/independent-composer-metadata.spec.tsx"
node node_modules/jest/bin/jest.js --runInBand __tests__/admin/social/clean-status-sync.test.tsx __tests__/admin/social/composer-media-integration.test.tsx __tests__/admin/social/gates.adversarial.test.tsx __tests__/admin/social/schedules.test.tsx __tests__/admin/social/manual-publication.test.tsx
```

## Independent coordinator receipt reconciliation

[COORDINATOR_ACCEPTANCE.md](COORDINATOR_ACCEPTANCE.md) was read against the retained raw XML and structured command receipts. [Verification output](independent-coordinator-receipt-verification.json) confirms the four copied artifact hashes, all eight actual PostgreSQL XML hashes/counts, six combined restore/API cases and 21 host inspection cases. The extra ownership/retirement/operator selections contain 36 + 7 + 2 = 45 cases per mode, all with zero failures/errors/skips. The 299 normal / 302 optimized selections and other overlapping cohorts stay separate.

[Exact skipped-case reconciliation](independent-skip-inventory-reconciliation.json) matches the original broad-run skip function/parameter identities to passed testcase records: eight PostgreSQL cases in each mode and nine native-video cases in the 21-case host selection. The first inventory mapper needed decorator-line handling for one parametrized test; it made no test/runtime change. Host metadata was independently re-read as Python 3.14.0, Pillow 12.1.1, SQLAlchemy 2.0.46 and ffmpeg/ffprobe 9.0.1. This remains different-package host compatibility, not exact production-package or deployed-host video acceptance. The broad-run 17 skips are preserved as originally reported.

The addendum correctly limits synthetic reconstruction, conditional-history recovery and local SQL/role/race proof. It does not certify production PostgreSQL/R2 restore, independent custody, provider send, active hosting capacity, financial generation, costs or OAuth ingress privacy. No previously accepted diagnostic-accounting/ffprobe prerequisite is reopened.


The refreshed owner browser artifact was then reviewed separately: [final-browser-review.json](final-browser-review.json) binds the final six-group/49-request receipt, source manifest and generated mobile screenshot, with zero external requests/page errors. The owner source manifest matches the current files. This reviewer visually inspected the updated screenshot: approved version 3 and queued delivery are shown without a false newer-revision/local-edits warning; the human attestation remains checked, and the requested-publication status replaces the misleading checking message. The screenshot is still a synthetic contract fixture, not a production send. Final browser/source hashes are retained without relabelling the owner's run as a second reviewer browser execution.


## Final acceptance bookkeeping — no new execution

The coordinator's final receipts were independently read without running more tests or changing code. [Final bookkeeping verification](final-acceptance-bookkeeping.json) binds their file hashes and checks:

- `VALIDATION.json` and `source.json` agree on the same **17 frozen UI source/test hashes**, all matching current files. The backend manual-API test identity also remains unchanged.
- The copied complete production-mode build log matches its declared SHA256 and records successful compilation, lint/type validation, page generation and route output. Its execution receipt declares exit **0**, inert loopback API/Supabase configuration, and `artifact_deployed:false`. Expected loopback connection refusals during build are retained; this is a local complete-application build, not a deployed/API-health acceptance.
- The retained UI summary agrees with **750 passed tests across 47 suites**, zero skips. Browser JSON still contains **six groups, 49 intercepted API requests, zero external requests and zero page errors**. These are coordinator/owner receipts; they are not a new independent full-suite or browser run.
- Both copied combined API/cold-restore XML files report **6 tests, zero failures/errors/skips** in normal and optimized mode. All five entries in the updated coordinator artifact manifest match their copied files. The acceptance table now correctly records six passing optimized cases as well as six normal cases.

The earlier normal-only cold-restore wording and earlier four-artifact hash readback remain historical receipts; this final note records the additional optimized receipt and five-artifact manifest. All overlapping cohorts remain separate. No source, merge, deployment, provider send, production control or external acceptance changed during this bookkeeping step. The three draft PRs are independently reviewable candidates; their preparation supplies no production launch authority.


## Git build-log representation normalization

Verified directly with `git show 0bc7839:docs/releases/admin-publish-workflow-20261101/VALIDATION.json` and the matching committed build-log blob. [Committed representation receipt](committed-build-log-normalization.json) confirms the normalized log SHA256 is `3344b7aab36864f5c31d05e2948f5f1afefb0c89fe2f3f3caee8a3d930d9495e`. The original private raw log retains the previously reviewed SHA256 `23da90aebad45c71f90feba87f5f8e4257a7f7697c2de9363b24aa58b2700964`; converting CRLF to LF alone reproduces the committed bytes exactly. The committed validation explicitly records both representations and their normalization. All 17 committed UI source/test hashes match the frozen validation manifest. This resolves an evidence representation difference; it changes no execution result, test count, runtime source, deployment or launch authority. No tests were rerun.
