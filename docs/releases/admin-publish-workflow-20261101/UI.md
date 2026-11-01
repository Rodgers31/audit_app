# Human-operated admin publication — UI acceptance, 1 November 2026

The composer now exposes media selection and a primary **Publish now** action, with explicit readiness reasons beside that action. This is a local candidate UI correction at base `db713b72ccd4c1938e7dac0401f66770379bdb62`. It does not authorize production uploads, publication, worker startup, financial generation, automatic approval or automatic scheduling. No production configuration or remote provider/storage operation was executed in this lane.

## Bounded behavior changes

- Manual **Images & video** is visible without opening a secondary disclosure. Existing generated drafts retain their media controls outside the mobile editor/preview switch, so media selection remains available when Preview is the default view. Existing styles, destination overrides, inspected-media selection and immutable-revision saving remain in use. See [SocialComposer](../../../frontend/components/admin/social/SocialComposer.tsx).
- **Review & publish** is visible outside **Delivery & scheduling**. Its readiness list names system pause/unavailable status, missing/disconnected/paused accounts, missing or stale saved validation, media inspection, warning acknowledgements, authorization conflicts and an explicit server request for review attestation. The button references these explanations through `aria-describedby`.
- Both immediate actions — primary **Publish now** and schedule management’s **Publish unsent now** — require a fresh active/idle worker report: heartbeat and last scan within 45 seconds for active or 150 seconds for idle, with at most five seconds of future clock skew. Readiness expires while the page remains open and is checked again after visibility changes. Absent, stopped, stale or incomplete status refuses the immediate command. Future human scheduling/rescheduling and cancellation retain their separate behavior. Resume and safe-retry commands retain existing server-authoritative queue semantics; their accepted-command copy does not promise immediate delivery. See [worker readiness](../../../frontend/components/admin/social/useDeliveryWorkerReadiness.ts).
- A human may review and publish the exact saved revision directly. A separate **Approve revision** click is not newly required. Existing server validation, optional sensitive-content attestation, command idempotency and exact receipt checks remain authoritative; accepted queue receipts never become claims of remote publication.
- Media help text no longer invites an upload when the server only offers the inspected library. Runtime unavailability reasons remain visible. See [SocialMedia](../../../frontend/components/admin/social/SocialMedia.tsx).

A clean, idle editor now reconciles delivery/approval post-version changes only when post identity, immutable revision identity and the saved/live/input content fingerprints all agree. This updates the local post metadata without replacing input or resetting attestation or warnings. Dirty edits, changed revisions, conflicting content and in-flight command/media work retain explicit review. The badge distinguishes post **version** from content revision. Generated queued posts retain the accepted-publication receipt and truthful delivery-status copy; ready approved posts still validate before publication.

No new API or backend dependency, package change, global layout change, enablement control or automatic publication path was introduced.

## Executed evidence

The [source manifest](source.json) binds the candidate frontend source and reusable fixtures by SHA256. These are local contract fixtures using actual components/hooks/decoders with inert administrator auth. They do not establish real account permissions, provider behavior, storage custody, host capacity or deployed UI behavior.

[Red receipts](regression-red.txt) retain the failing assertion inventory. The initial seven-case regression run produced **6 failures / 1 pass** against the pre-fix composer: hidden media/publication controls, absent readiness reasons, stale/stopped/unavailable workers permitting immediate publication, and worker freshness not expiring. Two additional targeted pre-fix controls separately failed for misleading upload availability text and for a server review-attestation refusal leaving the publication action immediately available. The schedule-management counterpart also had **3 pre-fix failures** for unavailable/stale/stopped workers permitting its immediate action. Its green cases preserve future rescheduling and cancellation, with no immediate request. The final regression cases are normal Jest tests, not source-string checks.

From `frontend`, select an installed Node **24.22.1–24.x** runtime that satisfies `frontend/package.json`:

```sh
# Select an installed Node 24.22.1–24.x runtime before running these commands.
node --version
node scripts/verify-node-runtime.cjs
node node_modules/jest/bin/jest.js --runInBand \
  __tests__/admin/social __tests__/social-generation.test.tsx
node tests/manualPublicationBrowser.mjs
```

The final Jest run passed **47 suites / 750 tests**, zero skips, in **31.464 seconds**; its output is retained in [frontend-tests.txt](frontend-tests.txt). The new manual-publication suite has nine cases. The clean-status synchronization suite has seven cases, and the actual media-upload integration adds an in-flight status-refresh preservation case. The [independent stale-prompt red receipt](status-sync-red.txt) and [false checking-status red receipt](queued-checking-red.txt) retain the two post-publication failures before their fixes. The generated-draft suite also exercises library media → saved new revision → resolved preview → validation → explicit human Publish, including exact revision/version/attestation and absence of a published link. Existing positive publication fixtures now explicitly supply a fresh worker; the shared default status remains unavailable.

The owned Chromium browser run built the production fixture with two build CPUs and used local port **33551**, with every fixture API request intercepted at **33552**. It passed **six scenario groups**, recorded **49 fixture API requests**, **zero external requests** and **zero page errors**. The [full browser receipt](browser.json) retains request bodies and idempotency keys:

1. System/account pause plus unavailable media explains the holds, with no mutations.
2. A valid saved revision plus stale worker blocks immediate publication.
3. A new manual post selects inspected media, edits alt text, saves, validates and previews the saved content before human publication.
4. Failed/ambiguous and malformed publication receipts retain the exact request/key and never report remote success; an accepted queued receipt yields no published link.
5. A generated draft at 390px starts in Preview, exposes library selection, saves/validates the new immutable revision and sends only the explicit human publication command with attestation. Both publication paths reconcile the clean post-version readback without a false newer-content prompt, and generated publication preserves attestation without a false ongoing-check label.
6. At 390px and 320px, publication remains visible, Preview works and horizontal overflow is absent.

Screenshots were visually inspected: [off desktop](manual-off-desktop.png), [queued manual desktop](manual-queued-desktop.png), [off mobile](manual-off-mobile.png), [queued generated mobile](generated-queued-mobile.png). The fixture uses the real social UI styling with a minimal inert shell, not the deployed admin navigation or root typography.

Earlier browser setup attempts exposed the older minimal harness's missing production history bootstrap and non-exact test locators. They were fixture setup failures and are not counted as accepted scenarios. The final owned harness installs the actual `HISTORY_BRIDGE_BOOTSTRAP` before hydration and uses exact/scoped locators. Its temporary runtime directory is removed after completion. The reusable runner is `frontend/tests/manualPublicationBrowser.mjs`; it writes its report to `/tmp/admin-manual-publication-browser.json` and setup diagnostics to `/tmp/admin-manual-publication-*`. Accepted receipts are committed alongside this document; additional original diagnostics remain in the author's external evidence archive and are not required to run the checks.

Production publishing, uploads, all workers and financial generation remain required OFF until separately accepted external launch gates and an explicit owner decision. This local UI evidence does not close the [launch gates](LAUNCH_GATES.md).
