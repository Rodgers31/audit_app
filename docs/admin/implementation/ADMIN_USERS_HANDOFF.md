# Admin users final implementation handoff

Users lane #546, parent #545; coordinated review of PR #559 with #560–#562.
Final local acceptance executed 2026-10-08–09 America/Chicago (2026-10-09 UTC).
Worktree `/Users/roger/.codex/worktrees/batch6-admin-users/audit_app`, branch
`codex/batch6-admin-users`; initial base `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`.
The final revision is the commit containing this handoff. Current main containing
Operations, social and overview/audit was merged before retaining current callers.
The dirty primary checkout was not edited, reset, switched or used for installs.

## Result and preserved contracts

- Complete bounded Auth enumeration powers global email search, totals and
  statistics. Fetch 100 identities/page and at most 100 pages; a terminal short
  page is required. Repeated/malformed identities and incomplete census fail
  closed. Auth identities without profiles count; orphan profiles do not.
- All six blocking provider handlers execute in FastAPI worker threads. A slow
  list/stat/detail transport no longer stalls the ASGI event loop. The census
  remains capped and non-atomic under concurrent provider changes.
- Canonical UUID self-protection prevents self-demotion/deletion. Existing
  unknown role strings may be retained; new unknown grants cannot be made.
  Empty roles for another actor remain permitted under the existing policy.
- Provider verdicts and returned identities are validated. Roles/reset/delete
  return explicit acceptance and `audit_recorded`; acceptance and persistence
  are separate transactions. Failed persistence warns without replaying the
  accepted provider mutation. Reset acknowledges a request, not delivery.
- Reset uses `/auth/v1/recover` with query `redirect_to` and JSON email. An actual
  installed official SDK capture plus the GoTrue handler contract confirms this;
  the suggested JSON redirect change was refuted. No live email was sent.
- The provider/audit helper supports top-level and package imports. The users
  boolean writer applies the same pure bounded audit policy as overview/audit
  before persistence. Unknown role/field material and reset redirects are
  redacted; shared public writer signature/transaction behavior remain intact.
- Signed backend authentication, browser profile/guards and middleware require
  a matching identity and real string-array roles. The former strict auth xfail
  is removed and passes. Valid admin/citizen/legacy strings preserve policy.
- Private auth/internal/validation diagnostics are withheld, with no-store and
  Vary Authorization on protected responses. Queries are scoped by actor with
  disabled unauthorized reads; departing caches are cancelled/removed. Late
  mutations after actor departure or privilege revocation cannot mutate caches
  or navigate. Impossible dates, including year zero, are rejected.
- Auth notifications return synchronously; profile work runs after the SDK lock
  releases. Generation, identity lifetime and mounted checks suppress stale
  restore/profile/login/refresh/registration completions. Old permissions clear
  during verification, failures settle loading, and same-identity registration
  refreshes can accept a newer valid retry while stale role evidence stays out.

## Current acceptance matrix

| Surface/boundary | Executed evidence |
| --- | --- |
| List/search/stats/page/URL/history | Complete enumeration, global match, duplicates, out-of-range controls; real browser pagination/search/history |
| Detail/self/role policy | Canonical UUID, malformed/current/legacy roles, repeat changes, returned identity validation; keyboard/mobile/self browser controls |
| Reset/delete | Accepted-only verdicts, repeat/malformed replies, typed confirmation/cancel, exact reset contract; synthetic browser mutation/audit rows |
| Audit persistence/privacy | Boolean success/failure independent of provider acceptance; canonical bounded policy before write; actual role/reset/delete callers and persisted PostgreSQL browser rows |
| Auth/privacy/concurrency | Real inert signed JWT/profile controls, package imports, private error transport, slow provider/concurrent health; rendered guards/middleware and all protected browser checks |
| Actor/lifetime | Retained cache and late-callback adversary cases, same-actor revocation, SDK-lock fixture, initial/profile/refresh/registration/StrictMode interleavings |
| Recovery/accessibility | Loading/empty/error/malformed distinction, retry/refresh/empty-page Prev, keyboard and 375px overflow controls |
| Cross-lane callers | Users acceptance/audit bool; repeated real/dry-run ETL 503 with zero jobs/success audit; rendered 3 Auth identities despite only 2 profiles |

## Verification

Current users backend scope: **164 passed**. Users/auth frontend scope:
**127 passed across seven suites**, including **23 lifecycle cases**. Independent
Spec lifecycle replay: **15 passed**; it overlaps the retained suite and is not
additive coverage. The initial lifecycle receipt was 10 failed/2 passed; the
registration refresh receipt was 1 failed/22 passed before its repair. Final
React output has no act warnings/console errors.

Final combined source: **357 selected admin backend cases**, **14 actual
PostgreSQL controls**, **1,932 frontend cases** (one unrelated optional financial
skip), clean scoped ESLint, successful production builds and browser journeys:
**4 Users / 6 Operations / 5 Overview-Audit**. Full social verification is
recorded in [batch acceptance](BATCH_6_REVIEW_ACCEPTANCE.md). Compatible runtime:
Python 3.13.9/FastAPI 0.129.2/pytest 9.0.2/SQLAlchemy 2.0.46; Node 22.19.0,
Next 15.5.27/React 19.2.4/Jest 29.7/Playwright 1.58.2. No manifest/lock changes.

Tests use `env -i`, `PYTHON_DOTENV_DISABLED=1`, worktree backend PYTHONPATH,
owned SQLite/PostgreSQL and inert transport/identities. Browser APIs bind only
loopback 8151/8152/8153. Users/Operations run real production Next;
Overview/Audit uses actual Next development server. Unrelated finance prefetch
404s in these minimal fixtures do not establish a finance/deployment failure.

AuthProvider SHA256:
`a3bc744e0f7535e66386df585aa38602ff56ef5addea3444484f198d78f308a5`.
Independent Standards and Spec reports and the final lifecycle recheck are
retained under [review-evidence](review-evidence/BATCH_6_FINAL_SPEC.md).
Both review axes and adversarial fixes completed; no acceptance work was
interrupted. Review round covers all four inline findings; the redirect
hypothesis is an executed refutation, and the other three are repaired.

## Boundaries and next work

Fixed issues: #550 authorization, #551 users workflows, #553 shared audit policy,
#563 private caches, #564 private failures, #566 auth lifecycle. #554 remains open
for actual dedicated-worker dispatch/acceptance/idempotency/leases. Parent #545
and deployed telemetry/provider/storage acceptance remain open. GitHub Actions
is disabled; required repository CI checks cannot run. Owner merge bypass is
separate from local verification and does not certify those CI/security gates.

No real provider/user/email/storage mutation, production migration/deployment,
publishing, paid activation or new bot review request was made. Provider acceptance
and audit writes cannot be atomic; ambiguous post-mutation transport outcomes
require refresh before retry. Cross-admin global lockout is not serialized.
Live delivery, production provider/concurrency and Safari/Firefox remain unverified.

See [GoTrue recover](https://github.com/supabase/auth/blob/master/internal/api/recover.go)
and [redirect lookup](https://github.com/supabase/auth/blob/master/internal/utilities/request.go).
