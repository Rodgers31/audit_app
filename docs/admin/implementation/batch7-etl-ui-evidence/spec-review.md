# Independent Spec review — Batch 7 ETL UI

Reviewed source SHA: `f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3`.
Pinned base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`.
Diff: `git diff f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d...f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3`.
Commit: `f27a3fc feat(etl): add verified worker dispatch and command receipts`.
Worktree: `/Users/roger/.codex/worktrees/batch7-etl-ui/audit_app`.

Sources: current issue #568 and companion #554 (both OPEN), frozen
`BATCH_7_SESSIONS/SPEC.md` and `dispatch-contract-examples.json`,
`ADMIN_OPERATIONS_HANDOFF.md`, `ADMIN_USERS_HANDOFF.md`, shared authorization
provider/guard/query cleanup, and the complete scoped diff. Applied
`/Users/roger/.agents/skills/code-review/SKILL.md`, Spec axis. No applicable
AGENTS.md/CLAUDE.md was found in the owned checkout or its ancestors.
`docs/agents/issue-tracker.md` is absent; this review did not install or change
repository policy to recreate it. Issue bodies were fetched read-only with `gh`.

## Findings (under 400 words)

1. **P1 — same-actor renewal loses the submitted ambiguous intent key.** Frozen
   requirement: “UI retains one key for an ambiguous retry of the same intent”
   and “Protect deferred confirmations/mutation callbacks against … same-actor
   privilege revocation/session renewal.” `DispatchPanel.tsx:39–43` clears the
   journal whenever its actor differs from `access.actorId`.
   `useEtlAccess.ts:13` inherits `actorId` from the profile `user`, while actual
   `AuthProvider.changeSession` clears `user` during renewal and profile
   revalidation. A submitted request can therefore be aborted after acceptance,
   enter the transient null-profile state, and lose the only recovery key.
   After the same actor regains authorized access, the same Dry Run/Run Now
   starts a different key, permitting duplicate acceptance/execution. Two
   independently executed rendered regressions confirmed both absent recovery
   and a different UUID on the next same-action POST. The committed renewal
   test only fires a subscriber while keeping the profile populated, so it
   does not exercise the actual provider transition. The shared AdminGuard
   additionally unmounts children while the profile is loading; retaining the
   key solely inside DispatchPanel is insufficient across that transition.
   Preserve a bounded actor-scoped submitted intent across revalidation/remount,
   expose it only after that same actor reauthorizes, and retain a provider/
   guard lifecycle regression. Do not replay automatically.

No scope creep found. No additional confirmed receipt/parser/pagination/polling
defect was found in exercised paths. Actual backend-worker integration remains
coordinator acceptance, as explicitly required by the spec.

## Executed checks

All commands ran from the owned `frontend` directory with a clean process
environment and no dependency install. Node runtime was
`/Users/roger/.nvm/versions/node/v22.19.0/bin/node`; compatible read-only
`frontend/node_modules` symlink was reused. Cache:
`/tmp/batch7-etl-ui-spec-cache`.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --runInBand --cacheDirectory=/tmp/batch7-etl-ui-spec-cache \
  --runTestsByPath __tests__/batch7_etl_ui.test.tsx \
  __tests__/batch7_etl_ui_parsers.test.ts
```

Result: exit 0; **87 passed**, 2 suites, 1.041s.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --runInBand --cacheDirectory=/tmp/batch7-etl-ui-spec-cache \
  --runTestsByPath __tests__/admin/operations/operations-ui.test.tsx \
  __tests__/admin/operations/operations-adversarial.test.tsx \
  __tests__/admin-auth/session-lifecycle.test.tsx \
  __tests__/admin-users/users-pages.test.tsx
```

Result: exit 0; **72 passed**, 4 suites, 5.78s. Existing Operations/Users and
auth compatibility controls remain green in this executed scope.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --config=/tmp/batch7-etl-ui-spec-review/jest.config.cjs --runInBand \
  --cacheDirectory=/tmp/batch7-etl-ui-spec-cache -t 'spec review:'
```

Result: exit 1; **2 failed, 24 skipped**, 0.431s. Failures:

- `Same-actor renewal discarded the submitted ambiguous intent recovery.`
- `Same ambiguous action was resent with a different idempotency key after same-actor renewal.`

The temporary test uses the committed rendered suite's real DispatchPanel and
access hooks, separates mocked `authUser` from profile `user`, submits a deferred
Dry Run, emits renewal, sets profile null/admin false, then restores the same
actor/admin true. It neither searches implementation strings nor replaces the
changed dispatch/access seam with a fake. The author was sent the path and
finding; source files were not edited by this reviewer.

Because author repairs began concurrently, the same two failures were also
replayed against an immutable `git archive` of exact source SHA `f27a3fc` at
`/tmp/batch7-etl-ui-spec-pinned-f27a3fc/frontend`, using its unchanged manifest
and read-only runtime symlink. This isolates the retained red from working-tree
changes. Exact command (run from the owned worktree root):

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node \
  /tmp/batch7-etl-ui-spec-pinned-f27a3fc/frontend/node_modules/jest/bin/jest.js \
  --config=/tmp/batch7-etl-ui-spec-review/jest-pinned.config.cjs \
  --runInBand --cacheDirectory=/tmp/batch7-etl-ui-spec-cache -t 'spec review:'
```

Result: exit 1; **2 failed, 24 skipped**, 0.443s, same two explicit errors.
The six scoped/compatibility suites were then rerun from this immutable
snapshot with the same clean env/cache and their original config:
**159 passed**, 6 suites, exit 0, 6.454s. Arguments were the six
`--runTestsByPath` paths in the first two commands above, combined.
Temporary test SHA256:
`5353b0ef26635dfd5aa00bda4ebe9cc24d58f03849ac0d5e9a4ab302788044f2`.
Initial custom config SHA256:
`9d14a54b61e76d76c675893dc6078facd8cd6ada244d88e3738a62fc692b19b6`.

An earlier mismatch assertion encountered the shared runtime's pretty-format
`maxWidth` incompatibility; the final run above throws a plain explicit error
for the same observed mismatch and is the retained finding receipt.

## Limits and resources

No browser fixture reset/configuration or server/process/port changes were
performed: the author's 3162/8162 browser matrix was concurrently active, so
independent temporal tests used isolated Jest. No product backend integration,
PostgreSQL lease semantics, deployment, hosted CI/security/quality status or
financial readiness is certified here. No GitHub mutation or issue closure.
The dirty primary remained read-only; no primary application imports or dotenv
files were loaded. No source or shared runtime mutation.

Review temporaries are in `/tmp/batch7-etl-ui-spec-review`; the only owned
repository write is this receipt. The author owns retention/cleanup after
regressions are incorporated. A repaired-source replay remains necessary.

## Preliminary repair replay

The author added an actor-scoped browser-memory submitted-intent store, keeping
the same key through profile revalidation and AdminGuard-style page remount.
The reviewer independently executed the retained original two tests against the
working repair: **2 passed, 24 skipped**, exit 0, 0.44s (fixture acknowledgment
completion emitted act warnings; no product failure). A separate clean test
replayed null-profile renewal and page unmount/remount, including a different
actor between mounts: **2 passed, 24 skipped**, exit 0, 0.464s, no warnings.
Both retained the original UUID; the different actor had no recovery control.
Working repair SHA256 identities at replay:

| File | SHA256 |
| --- | --- |
| DispatchPanel.tsx | `91c9ecac3df7e240ca5587604d40abdbe8bcd320912a36cef2c88be143f46ab0` |
| useEtlAccess.ts | `edebdbb0b172325b59ff9f2a9dad3cf27f9325eb002aee703ac2e493e62e1481` |
| submittedIntent.ts | `3debdb7bf60d758ad8d1d0ecd0536f30fe1137f8c7d7f5a584a51fb48006f9c8` |
| batch7_etl_ui_spec_repaired.test.tsx (temporary) | `8d87717f3273b753a400ea7ea997ed6c0a1b1b984d27d32b3e420a519b970fce` |

The clean command was the original temporary-config command above with:

```sh
--runTestsByPath /tmp/batch7-etl-ui-spec-review/batch7_etl_ui_spec_repaired.test.tsx \
  -t 'spec repair:'
```

This is preliminary working-tree evidence; HEAD still identifies `f27a3fc`.
The final committed repaired SHA and any later delta must be reviewed before
claiming final Spec acceptance. Finding 1 is repaired in the exercised working
tree; no new confirmed defect was found in that repair. Shared authorization
and guard sources remain untouched.

## Final committed Spec replay

Final reviewed source SHA: `6087347edf1412d232302f986166c889403d17da`.
Repair commit: `6087347 fix(etl): retain uncertain intents and enforce receipt chronology`.
Reviewed both:

```sh
git diff f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3...6087347edf1412d232302f986166c889403d17da
git diff f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d...6087347edf1412d232302f986166c889403d17da
git diff --quiet 6087347edf1412d232302f986166c889403d17da -- frontend backend/tests/batch7_etl_ui_fixture.py
```

The final command exited 0 before these checks; product and scoped tests were
the committed source, with only untracked author evidence in the worktree.

### Final findings (under 400 words)

**Zero unresolved Spec findings in the exercised UI scope.** Finding 1 is
repaired: the browser-memory store contains one actor-scoped unresolved intent,
keeps its source/mode/key/generation across profile-null revalidation and page
remount, and reveals recovery only to its originating actor after authorized
access resumes. It contains neither credentials nor command receipts, and
recovery still requires explicit action. Changed intent creates a new UUID.
The committed tests now exercise the actual AdminGuard unmount, rather than
only firing a renewal subscriber against a populated profile.

The repair delta also retains microsecond timestamp ordering for worker and
receipt evidence and history sort order, rejects rewriting recorded terminal
finish time, merges sequential filter intentions while navigation is pending,
provides exact accessible select labels, and wraps keyboard focus in the native
confirmation dialog. Those changes implement frozen requirements for “Enforce
coherent ordering,” “bounded history/filter/pagination,” and “mobile and
keyboard behavior.” The fixture single-clock/CORS changes remain inert test
infrastructure. No scope creep was found.

Actual product worker/backend replay remains required coordinator acceptance;
these UI tests do not close #568/#554, certify dispatch mappings, or establish
financial freshness/deployed readiness. Hosted gates remain unexecuted by this
reviewer.

### Final independently executed commands/results

From the owned `frontend` directory, same clean env/runtime/cache as above:

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --runInBand --cacheDirectory=/tmp/batch7-etl-ui-spec-cache --runTestsByPath \
  __tests__/batch7_etl_ui.test.tsx __tests__/batch7_etl_ui_parsers.test.ts \
  __tests__/batch7_etl_ui_adversarial.test.tsx \
  __tests__/admin/operations/operations-ui.test.tsx \
  __tests__/admin/operations/operations-adversarial.test.tsx \
  __tests__/admin-auth/session-lifecycle.test.tsx \
  __tests__/admin-users/users-pages.test.tsx
```

Exit 0; **203 passed**, 7 suites, 7.325s. This reviewer independently ran the
scoped adversarial controls, including in-flight/deferred actor, role, session,
visibility, unmount, stale denial, AdminGuard remount, receipt error and strict
parser boundaries. Broader author-reported 337/build/lint results were not
re-certified by this reviewer.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --config=/tmp/batch7-etl-ui-spec-review/jest.config.cjs --runInBand \
  --cacheDirectory=/tmp/batch7-etl-ui-spec-cache --runTestsByPath \
  /tmp/batch7-etl-ui-spec-review/batch7_etl_ui_spec_review.test.tsx -t 'spec review:'
```

Retained original reproduction against exact final source: exit 0;
**2 passed, 24 skipped**, 0.445s. The original lost-key failures are green.
The temporary acknowledgment stub still emitted act warnings when its
unmatched Dry Run response completed; the key assertions passed.

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --config=/tmp/batch7-etl-ui-spec-review/jest.config.cjs --runInBand \
  --cacheDirectory=/tmp/batch7-etl-ui-spec-cache --runTestsByPath \
  /tmp/batch7-etl-ui-spec-review/batch7_etl_ui_spec_repaired.test.tsx -t 'spec repair:'
```

Additional clean independent null-profile/remount/isolation replay: exit 0;
**2 passed, 24 skipped**, 0.512s, no warnings. Test file hash and the final
DispatchPanel/useEtlAccess/submittedIntent hashes match the preliminary table.
Final CommandHistory SHA256:
`2736196589839991a13d17bb1cc99cf406c66b5cd5071e26f07e4d5bd6a6d2f2`.
Final etlDispatch SHA256:
`60376cdce3fbb49c735389be51fba75f3ed4919f2f6c96f73672152d0b0e6487`.

### Rendered evidence inspection and browser limits

Read-only inspected author fixture PNGs under the 9 October task artifact path
`batch7-etl-ui/browser-final`: mobile-ready, mobile-receipt and desktop-ready.
Their layout fits the mobile width and keeps receipt/dispatch meaning separate.
The screenshots caught the shared 420ms+80ms PageShell opacity entrance before
it settled, so they cannot establish final text contrast; the author was asked
to capture settled frames or disable finite animations in screenshot capture.
This is a receipt-timing limitation, not a confirmed product contrast defect.

At inspection, author browser-final.txt reported 23 passed/1 failure: the
history/detail assertion matched ten history rows before navigation settled.
The author was notified to await the detail URL/heading. No fixture reset,
configuration, transport mutation, additional browser run, or server ownership
change was performed by this reviewer. Final author browser repair/replay is
still required and must be reported under its actual source identity/results.

### Settled visual review and final cleanup

The author subsequently repaired only screenshot/navigation timing in the
browser harness: wait for the detail URL/heading and settled PageShell opacity,
then disable finite animations during capture. Read-only review of that delta
found no weakened acceptance assertion or product change. Product sources
remain exact `6087347` (verified with diff-quiet over ETL app/client and the
fixture). The later `dba511b9fec01ce63843fe576ef20f6e2539375a` commit adds browser
harness timing and two history-navigation tests; that narrow test-only delta
was reviewed and its two new controls independently executed below.

`browser-accepted.txt` now records **24 passed, exit 0, 54.9s**. This is the
author's actual browser execution, independently inspected here rather than
executed again. Refreshed PNGs under external `batch7-etl-ui/browser-accepted`
were viewed: mobile-receipt, desktop-ready and interrupted. The settled text is
clear; mobile command identity wraps within its card, controls fit the width,
and receipt/status/action hierarchy is readable. The interrupted screen states
execution unverified, offers a receipt refresh, and exposes no execution retry
or fabricated observation link. The existing calendar stays separate below
dispatch/history. No new visual Spec finding was confirmed.

Original review red and exact final-source greens were recaptured before
cleanup: **2 failed** at pinned `f27a3fc` (0.44s); **2 passed** retained-original
replay at `6087347` (0.422s); **2 passed** clean renewal/remount/actor-isolation
replay at `6087347` (0.444s). Source test/config/raw result files are archived
outside git with commands, source identities and hashes in:

[spec-review-reproductions/manifest.json](/Users/roger/.codex/visualizations/2026/10/09/01a11f2c-fa93-7441-9107-010ba2a08dd8/batch7-etl-ui/spec-review-reproductions/manifest.json)

Manifest SHA256:
`0a28d340622d8d9dec2c16a0d4f57a97cf5f503c5348ea7ca248a331801eac61`.
The manifest describes regenerating historical temporary paths for replay.
Reviewer-owned `/tmp/batch7-etl-ui-spec-review`,
`/tmp/batch7-etl-ui-spec-cache`, and
`/tmp/batch7-etl-ui-spec-pinned-f27a3fc` were removed after archival.
No reviewer server, port, database, browser fixture change, production identity,
GitHub mutation or shared runtime mutation was created. Only this review receipt
was written in the repository. Final result: **one initial Spec finding, fixed;
zero unresolved Spec findings in the exercised scope**. Coordinator product
backend/worker integration remains required.

At final HEAD `dba511b9fec01ce63843fe576ef20f6e2539375a`, independently executed:

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
  PYTHON_DOTENV_DISABLED=1 NODE_ENV=test \
  /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js \
  --runInBand --no-cache --runTestsByPath __tests__/batch7_etl_ui_adversarial.test.tsx \
  -t 'adversarial rapid history|adversarial clear and browser back'
```

Exit 0; **2 passed, 42 skipped**, 0.361s. Pending sequential changes preserve
page-size/source/status across intermediate navigation, while Clear and actual
popstate discard unfinished filter intentions. No additional source gap or
scope creep was found. The no-cache run created no new reviewer cache resource.
Final browser harness SHA256:
`73355b8e6d2e1e9f7d6cf76da40ab5b57117c247d6409bf6873409bce3a8f5fd`.
Author browser accepted receipt SHA256:
`d7200eaa1264e1069ebee19acf170c44cbe69049b5fd2b555f63ff0ec861bd62`.
