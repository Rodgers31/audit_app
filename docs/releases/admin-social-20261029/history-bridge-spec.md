# Scoped Next history integration review

No remaining finding in the reviewed bridge delta. The old late capture listener is unsafe under the actual Window listener ordering recorded by root in Chrome. The permanent early bridge repairs that ordering dependency in the executable integration model.

## Executed evidence

- `old-next-order-red3`: **1 desired regression executed and failed**, expected one prompt, received zero. Old guard bytes SHA256 `3dc234942deb70059e647e151342a27c699806b1746e9bb56ac0ad151f6b6426`. Trace: first listener → actual Next restore → probe unmount → late guard listener. This matches root's browser observation; it does not independently reproduce native Chrome.
- `next-bridge-green1`: **5/5 passed, no skips**, using shipping bootstrap/manager plus the actual cached Next 15.5.28 history effect, traverse dispatcher, useActionQueue, queue dispatch/runAction, and restoreReducer. Dirty cancellation prompts and stops before Next; acceptance prompts once then permits Next restore; bootstrap is persistent/idempotent; missing and invalid bridge refuse tracking.
- `permanent-bridge-green1`: **5/5 passed, no skips**, executing the requested permanent `frontend/__tests__/admin/social/history-bridge.test.tsx`. This uses a small isolated framework-listener model with the shipping hook/bridge, avoiding parser/framework internals in repository tests.

Both green runs used read-only integration source and locked dependencies in owned Docker with `--pull=never --network none --cpus 1 --memory 2g --pids-limit 256`. Source hashes remained identical before/after each run. Exact commands, Jest JSON, logs and hash receipts are adjacent. The only project file written by this reviewer is the permanent test named above.

Reproduce the real-code model with `python3 run.py red <fresh-label>` and `python3 run.py green <fresh-label>` from this evidence directory. The red invocation mounts the preserved old source. Existing labels are deliberately protected from overwrite. Permanent execution is recorded in `permanent-bridge-green1-command.json`.

## What the model proves and its limits

The model dispatches Window callbacks in the **registration order observed by root's Chrome test**, allowing a React commit between callbacks. It does not use JSDOM's capture-before-bubble synthetic ordering as evidence of browser safety. Next's actual history listener is registered without capture and restores route state through React. When that listener runs first, it can retire the guard; when the shipping bridge runs first, cancellation synchronously prevents the framework callback. The bridge passes the original event, and the tests inspect the actual rendered probe before teardown. A final probe-unmount entry in the cancellation trace is test cleanup.

The history effect and dispatcher functions are extracted without rewriting their bodies from the cached Next files whose hashes are in `framework-hashes.json`; the real useActionQueue module is loaded normally. Route content is a local guarded React probe, the dev rendering indicator is stubbed, and the unused PPR branch explicitly throws. This is not a complete AppRouter/Flight/BFCache/browser test. The first attempted full restoreReducer import ran **zero cases** because Jest lacked Next's bundler alias for react-server-dom-webpack; that setup failure remains in `old-next-order-red.log`. The subsequent extraction executes the actual restore body without that unused import tree.

Source inspection separately confirms cached Next app-bootstrap sequences `__next_s` scripts before hydration, and the reviewed root layout declares this bootstrap with `beforeInteractive`. The ReactDOM navigate listener found during investigation is limited to its `react-transition` indicator; no evidence identifies it as this Back failure's cause. Duplicate tracking owner and BFCache theories were not needed to reproduce the observed ordering failure and remain unproven.

Prior 63 controls retain their previously stated JSDOM scope. Root owns the separate Chrome proof and full frontend/build run; this report does not claim to have executed those. No browser, provider, production, database, worker or publishing actions were performed.

## Author integration confirmation

Actual hydrated Chrome separately reproduced the earlier late-listener failure and verified the new bootstrap in both Back and Forward directions. Cancelling retains manual unsaved text and URL; accepting asks once and reaches the destination. Generated drafts auto-save, so the permanent composer fixture now uses a manual draft.

Final complete frontend run: 214 suites, 2,858 passing tests, one existing skip. The real workflow and authoritative frozen Git objects were supplied to the two producer suites; initial missing-harness-input failures remain retained. TypeScript (incremental writes disabled for the read-only mount), scoped lint and capped offline production build pass. This is local integration evidence; production deployment and #849 acceptance remain separate.
