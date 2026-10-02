# Round17 county money-flow read states

Issue #446 is implemented locally. `MoneyFlowTab` now distinguishes pending or
failed fiscal-year discovery, a successful discovery with no usable period,
a pending money-flow read, a failed read and a successful empty report. A failed
read displays a localized alert and explicit retry, with no fabricated financial
amounts or absence claim. Retry uses the existing bounded transport budget and
`cancelRefetch: false` to share an active request. Period selection remains usable
on a failed money-flow read. Loading and successful absence have status semantics.

The only production caller of `FollowTheMoney` and `useCountyMoneyFlow` is this
tab (`rg` across frontend); both initial/default and user-selected periods pass
through the gate. No API transformer, cache key, fiscal resolver or dynamic tab
import changed. The source-document and committed-to-procurement notes remain.
Seven `county.money.*` catalog entries cover these states in English, Swahili and
plain English. Runtime localization is verified; competent human Swahili review
is not certified and remains with the language-review owners (#307/#372).

## Executed local verification, 2 October 2026

Baseline is main `fc69f13c04c9cc27fa2e6514b47b6bd569a5b772`, tree
`5e63dfef84a992758ad24de88dcfa18e56f71b8f`, clean assigned worktree before edits.
The allowlisted runner and receipts use prefix `ROUND17_SESSION_1_` in the shared
Round16/17 evidence bank. They start production Next.js on3181 and actual
FastAPI readers on8181 with47 invented county fixtures in disposable SQLite.
Both dotenv/Pydantic environment files, background lifespan, seeder/warmup and
provider HTTP are disabled. A hostile inherited configuration control verified
local SQLite, inert lifespan,47 counties and blocked external HTTP. No provider
or production access was used. PostgreSQL5571 was not needed.

| Check | Actual result |
| --- | --- |
| Final8-case component regression on unchanged baseline product files |7 failed,1 healthy pending/empty control passed. Failure assertions require the missing state/recovery, not source strings. |
| Same regression plus existing amount-coverage suite after fix |13 passed,0 failed,0 skipped. |
| Independent adversarial rendered controls |10 passed,0 failed,0 skipped: cached failures, rapid retry, recovery, pending/absence, zero/null. Two controls document out-of-contract input limits. |
| Restored #291 county failure case on baseline production build |1 failed after the actual narrowly routed money endpoint returned500; no alert/retry. |
| First21-case post-fix browser selection |18 passed,3 failed: one test selector also matched Next's route announcer; two code-loading stalls with no money request. All retained. |
| Final focused Chromium selection |21 passed,0 skipped,0 unexpected,0 retry-classified flaky,0 retries;12.31s. |
| TypeScript, production Next.js build, diff whitespace |Exit0. |

The final browser selection restores the original named `/counties/001` failed
read case with a narrowly consumed endpoint and actual API retry recovery. It
also preserves all10 original follow-the-money cases, including unchanged
shell-click committed-note and source-link/year controls. Ten new controls cover
read states in all three languages at375/1280px, keyboard retry,44px button,
no horizontal overflow, discovery recovery and successful absent periods.
The new read-state matrix uses supported `?tab=money` deep links to isolate its
contract from #450; the existing shell-click regression remains unchanged.
No full legacy-suite or hosted CI result is claimed. Actions remains off.

Resolved dependencies: Node22.19.0, Python3.13.9, Next15.5.20, React19.2.4,
TanStack Query5.90.21, Playwright1.58.2, Jest29.7.0, existing read-only dependency
tree. Synthetic behavior on a production build does not establish corrected
public data. Two intermediate unit runs failed on animation/async-button test
assumptions; the final fixture waits for actual visibility and tests in-flight
request counts. A first isolation probe caught the wrong exception type after
HTTP was correctly blocked; the corrected probe records success.

## Issue #450 remains unresolved

A fresh baseline bounded run captured a10.08s no-request stall in
`ROUND17_SESSION_1_LAZY_10.zip` and `ROUND17_SESSION_1_LAZY.json`: money button
pressed, code fallback visible, money chunk9235 returned200, navigation RSC
request finished200, no money-flow request, no page exception. The browser URL
remained `/counties/001`; completed router transport is not a committed URL.
An earlier probe also timed out on the note after five controls, without its
full failure capture; it is not promoted to a diagnosed mechanism.

The retained capture run had9 passes/1 failure. A corrected probe gated the
actual money chunk rather than its shared dependency, gated the navigation RSC
response independently, rapidly switched tabs and recorded React fiber/lane
state. All25 controls passed. While the money chunk was held, the code fallback
and zero requests were expected; after release content arrived. While the router
response was held, money content/request completed. These controls falsify a
simple dependence on router completion; they do not identify why occasional
successful chunk responses leave the boundary stalled. Initial probes also
exercised a shared dependency gate, which is not the actual money-module gate.

The first post-fix browser selection retained two more code-fallback failures
(plain-English desktop and pending-discovery desktop), each with chunk9235/200
and zero money requests. They duplicate #450, not a new issue. No deterministic
bad interleaving or underlying dynamic-import/Suspense cause was established.
No timeout/retry/quarantine or speculative product change was applied to #450.
Keep it open. Next useful input is a reproducible promise/Suspense scheduler
state that explains the stall; a passing rerun is not a fix.

Evidence filenames, exact commands, UTC captures and SHA256 values are in
`ROUND17_SESSION_1_HANDOFF.json`; the external handoff includes cleanup and the
local commit identity. #446 is eligible for close-after-merge review; #291 still
needs its actual hosted final CI under the owner's policy, and #450 remains open.
