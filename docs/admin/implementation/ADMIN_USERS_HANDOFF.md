# Admin users implementation handoff

Users lane [#546](https://github.com/Rodgers31/audit_app/issues/546), parent [#545](https://github.com/Rodgers31/audit_app/issues/545). Verification executed on 2026-10-08.

- Worktree: `/Users/roger/.codex/worktrees/batch6-admin-users/audit_app`
- Branch: `codex/batch6-admin-users`
- Pinned base: `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`
- Audited implementation commit: `92b7426d07c447b752628d1969e7c7d65847b784`. The following handoff commit changes only this document; final branch head is reported on the draft PR.
- Owned changes: users router, new users provider/audit and frontend contract helpers, two users screens, lane-specific backend/UI/browser tests and fixture. Shared auth, AdminGuard, Axios, middleware, models, migrations, manifests and lockfiles remained read-only. The dirty primary checkout was not modified.

## Contract decisions recorded before implementation

- Preserve every users endpoint, `citizen`/`admin` vocabulary and stats field names. Search filters the full enumerated Auth population before pagination; `total` counts that matching enumeration. Fetch 100 users per provider page, at most 100 pages. A terminal short page is required; populations of 10,000 or more fail with 503 instead of an inferred total. Detectable repeated identities, malformed data and provider errors fail. Enumeration is not an atomic snapshot under concurrent changes.
- Canonical UUIDs determine self-protection. Existing unknown roles may be retained; new unknown roles cannot be granted. Empty roles remain supported except removal of the actor's own admin role. Another admin may demote/delete a different admin under existing policy; no new global lockout rule or cross-admin transaction.
- Roles retain the detail shape and add flat `ok` and `audit_recorded`; reset/delete retain `ok` and add `audit_recorded`. Provider acceptance and audit persistence are separate. Failed audit persistence after acceptance produces a warning without replaying the provider mutation.
- Reset uses `/auth/v1/recover`, acknowledges an accepted reset request and does not claim delivery. Recovery links/tokens are never returned or logged. Arbitrary redirect URLs are omitted from audit payloads; redirect allowlists remain provider controlled.
- Users-only helpers merge provider headers once and commit to the existing audit model with a boolean persistence result. Shared provider and audit helpers remain unchanged for coordinator integration. Existing action names and payload signatures are preserved.
- Users responses and expected rejection paths have `Cache-Control: no-store`; provider error bodies are sanitized. Frontend runtime parsers reject malformed identity/list/detail/acknowledgment payloads. URL queries, history and empty later pages remain recoverable.

## Acceptance matrix

| Requirement | Retained evidence | Disposition |
| --- | --- | --- |
| Totals, page boundaries and global search | Backend exact population, match beyond first provider page, out-of-range and duplicate/repeated pages; browser 42-user pagination/search | PASS for completed enumeration; concurrency/scale limits below |
| Statistics | Actual Auth population, rolling 7/30-day counts, orphan-profile exclusion | PASS |
| Auth failures and forbidden callers | Actual shared dependency with inert signed JWT; missing, expired, malformed and citizen controls stop provider calls | PASS for valid role arrays; shared malformed-role defect #550 |
| UUID and self-protection | Invalid IDs stop transport; equivalent UUID spellings cannot bypass self-demotion/delete; browser self controls | PASS |
| Roles/current policy | Invalid/new unknown grants rejected; legacy retained; empty roles for another user; repeated update; returned identity/state verified | PASS; concurrent global lockout limit below |
| Reset | Memory transport verifies `/recover`; no-email rejection; semantic failure acknowledgments rejected; browser accepted-request copy and audit row | PASS; delivery unverified |
| Delete | Repeated deletion, wrong identity, malformed verdict, matching raw/wrapped Auth User and empty acknowledgment controls; typed browser confirmation/cancel | PASS, synthetic users only |
| Provider/audit outcomes | No audit on rejected provider result; commit failure/truthy false verdict controls; browser verifies three actual disposable PostgreSQL rows | PASS |
| Sensitive data | Nested credential key variants stripped; unsafe/nonfinite/huge metadata rejected; sanitized errors; no-store success and 401/403/422/503 | PASS for exercised boundaries |
| Frontend contracts | 47 parser cases, including impossible dates, 24:00 clocks, duplicate IDs, role mismatch and malformed verdicts | PASS |
| Rendered recovery/state | 9 React cases: malformed list refresh, detail retry, URL page, history search, empty-page Prev, failed mutation acknowledgments, audit warning, expired-ban badge | PASS |
| Production browser | Four Chromium cases: list/search/detail/history; roles/reset/delete and persisted audit; self/keyboard/375px layout; malformed response recovery | PASS |
| Independent review | Standards, Spec and adversarial dispositions below | PASS, lane-owned surfaces |
| Shared authorization shape | Strict expected-failure test exercises real shared `require_admin` and inert signed JWT | Coordinator dependency #550; not a passing auth control |

## Observed red/green receipts

Failures were executed before repair. Retained tests assert the failed invariant. Setup and selector failures were corrected separately and are not counted as application regressions.

| Replay | Observed red | Observed green |
| --- | --- | --- |
| Original backend boundary suite against pinned router/provider | 69 failed, 21 passed, 1 strict xfailed | Final combined backend: 131 passed, 1 strict xfailed |
| Original rendered React cases | 8 failed | Final React + parser suites: 56 passed |
| Independent memory transport attacks | 20 failed, 8 passed | All 29 current cases pass, including later oversized-integer case |
| Independent frontend hostile contracts | 24 failed, 22 passed | All 47 current parser cases pass, including later 24:00 case |
| Rejected-response no-store | 4 failed, 3 passed | 7 passed |
| Late delete compatibility/oversized metadata controls | 3 failed, 6 passed in targeted 9-case replay | 9 passed |
| Malformed clock control | 1 failed, 3 passed | 4 passed |
| Expired-ban badge | 1 failed against pinned list source | 1 passed after repair |
| Browser baseline list count | First interaction failed: exact count copy absent | Four final production-build interactions pass |
| Browser mobile heading | Document 447px wide at 375px viewport | Final 375px overflow assertion passes |

First browser repair run also had an ambiguous search selector; a specific selector fixed that test issue. Final source remained unchanged for the last expired-ban test addition.

## Final commands and results

Commands ran in the managed worktree. Backend used the existing read-only Python 3.13.9 environment: FastAPI 0.129.2, httpx 0.28.1, pytest 9.0.2, SQLAlchemy 2.0.46. Frontend dependencies were installed into this worktree with its unchanged lockfile using Node 22.19.0/npm 11.6.0: Next 15.5.27, React 19.2.4, Supabase JS 2.98.0, Playwright 1.58.2. The pinned lockfile also records Supabase JS 2.98.0; no SDK downgrade or manifest edit. Test processes did not load environment files or production credentials.

```sh
# Worktree root: inert provider controls; no database connection required.
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch6-admin-users/audit_app/backend \
  DATABASE_URL=postgresql+psycopg2://fixture:fixture@127.0.0.1:55471/fixture \
  /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest \
  backend/tests/test_admin_users_boundaries.py \
  backend/tests/test_admin_users_adversarial_replay.py -q --tb=short
# 131 passed, 1 strict xfailed, 2 existing SQLAlchemy deprecation warnings; 0.77s.

# Frontend; shell-local runtime alias.
node_bin=/Users/roger/.nvm/versions/node/v22.19.0/bin
env -i PATH="$node_bin:/usr/bin:/bin" NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  node node_modules/jest/bin/jest.js --runInBand __tests__/admin-users
# 2 suites, 56 passed; 0.497s. Independent final replay also 56 passed.

env -i PATH="$node_bin:/usr/bin:/bin" NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  node node_modules/typescript/bin/tsc --noEmit
# Exit 0, no diagnostics.
env -i PATH="$node_bin:/usr/bin:/bin" NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  node node_modules/eslint/bin/eslint.js app/admin/users lib/admin/users.ts \
  __tests__/admin-users e2e/admin-users playwright.admin-users.config.ts
# Exit 0, no diagnostics.

env -i PATH="$node_bin:/usr/bin:/bin" HOME=/Users/roger NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8151 \
  NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic-users-anon \
  node node_modules/next/dist/bin/next build
# Exit 0: compile, lint/type validation, static pages and build traces completed.
```

### Browser reproduction

Use only an owned disposable database and unused loopback ports. The fixture creates/drops its audit table and resets synthetic users/audit rows between cases. Do not point it at existing storage. Browser and fixture block external provider traffic. Frontend auth uses a synthetic cookie and mocked local Supabase endpoints. Shared token decoding/role lookup are overridden for browser setup; backend tests separately exercise actual shared auth with inert JWTs.

```sh
docker run --detach --name batch6-users-postgres \
  --publish 127.0.0.1:55471:5432 --env POSTGRES_USER=fixture \
  --env POSTGRES_PASSWORD=fixture --env POSTGRES_DB=fixture postgres:16-alpine
# Wait for PostgreSQL readiness before the fixture.

# Backend: separate terminal/process.
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/batch6-admin-users/audit_app/backend \
  /Users/roger/Documents/projects/audit_app/venv/bin/python tests/admin_users_browser_fixture.py

# Frontend: production build server in a separate process.
node_bin=/Users/roger/.nvm/versions/node/v22.19.0/bin
env -i PATH="$node_bin:/usr/bin:/bin" HOME=/Users/roger NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8151 \
  NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic-users-anon \
  node node_modules/next/dist/bin/next start -H 127.0.0.1 -p 3151

env -i PATH="$node_bin:/usr/bin:/bin" HOME=/Users/roger \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:8151 \
  node node_modules/@playwright/test/cli.js test --config playwright.admin-users.config.ts
# Chromium: 4 passed, 7.1s against production build.
# Stop the two owned servers, then remove exactly the owned container:
docker rm --force batch6-users-postgres
```

The first local PostgreSQL setup lacked server binaries. A SQLite attempt could not compile the unchanged audit model's JSONB field. Both were abandoned; final browser acceptance uses disposable PostgreSQL 16. No model/migration changes or SQLite substitution. Raw logs are local `/tmp/batch6-users-*.log`; committed tests and results above retain portable evidence.

## Independent review dispositions

- **Standards: PASS, zero unresolved findings.** Read-only review against pinned base. JSDoc gaps in complex validators were repaired; timestamp/metadata predicates have descriptive names. Final delete compatibility and dedicated regressions reviewed. No material documented-standard or smell-baseline violations found.
- **Spec: PASS, zero lane-owned acceptance gaps.** Independent final backend replay: 131 passed, 1 strict xfailed, four warnings (two existing SQLAlchemy warnings plus two pytest configuration warnings in that review environment). Late acknowledgment, cache, metadata and delete compatibility repairs reviewed. Reviewer did not rerun browser/UI/build checks. Shared #550 remains a dependency.
- **Adversarial: PASS for owned users surfaces.** Independent backend: 131 passed, 1 strict xfailed, two existing warnings. Final frontend: 56 passed across two suites. Memory transport/JSDOM attacks cover false verdicts, nested credential spellings, unsafe numbers/dates, duplicate IDs and expired bans. No independent browser/live-provider claim; root performed production Chromium/PostgreSQL verification.

## Tracked defects and remaining dependencies

- [#551](https://github.com/Rodgers31/audit_app/issues/551) tracks owned count/search/stats/validation/reset/provider/UI defects and review edge cases; retained regressions cover repaired gaps. Shared `_raw_request` still supplies duplicate `headers` for the original role helper. The users helper avoids this without shared edits; coordinator decides shared reuse/repair.
- [#550](https://github.com/Rodgers31/audit_app/issues/550) remains unresolved: shared `_fetch_roles` converts `roles={"admin": false}` into `['admin']`, authorizing the inert caller. Current strict-xfail selector: `backend/tests/test_admin_users_boundaries.py::test_shared_auth_rejects_malformed_role_mapping`. The earlier issue body used an obsolete name. Coordinator owns shared role-array/profile-identity validation and rendered AdminGuard/middleware controls. This xfail does not establish repaired authorization.
- Dedup searched all GitHub issue states with `admin`, `roles admin auth`, `users count reset`, `reset roles Supabase`, and `audit persistence`; matching batch trackers/unrelated closed issues were inspected before creating specific tickets. Issues remain open for coordinator acceptance.
- Full scans cost up to 100 synchronous provider calls; stats also batch profile reads. Existing async handlers perform synchronous transport. Large populations require coordinator/provider query work; the cap fails closed. Concurrent inserts/deletes can yield non-atomic enumeration even without detected duplicates. No atomic global-count claim.
- Self guards preserve policy, but simultaneous actions by different admins are not serialized and can create global lockout. No new global lockout rule or cross-provider/database transaction was authorized.
- Provider acceptance and local audit persistence cannot be atomic. Ambiguous transport/malformed-response outcomes after mutation may require refreshing before retry. Accepted reset requests are disabled on the current screen; no durable idempotency/outbox was added.
- Live delivery, deployed provider versions, production storage/concurrency and Safari/Firefox were not verified. All identities/writes were synthetic. No deployment, migration, real deletion/email, issue closure, merge or Copilot review request.
- No interrupted acceptance work remains. Owned servers/container and generated browser results are cleaned up at closeout; managed worktree remains for coordinator review.

## Provider references

- [Supabase generateLink](https://supabase.com/docs/reference/javascript/auth-admin-generatelink): generated links/OTPs support a custom mail provider.
- [Supabase resetPasswordForEmail](https://supabase.com/docs/reference/javascript/auth-resetpasswordforemail): reset request sending semantics.
- [GoTrue recover handler](https://github.com/supabase/auth/blob/master/internal/api/recover.go) and [admin handler](https://github.com/supabase/auth/blob/master/internal/api/admin.go): empty success responses, pagination and deletion. Mutable upstream references informed compatibility; deployed-provider verification is not claimed.
- Installed `frontend/node_modules/@supabase/auth-js/src/GoTrueAdminApi.ts` and `fetch.ts`: raw/wrapped delete response compatibility.

## Coordinator review repairs (2026-10-08)

The shared-core exception is coordinated in this PR: backend signed-token role
lookup validates an actual string array and matching canonical profile UUID;
frontend profile fetch, guard and middleware validate shapes and matching
identities. The prior strict xfail is removed and now passes. Empty/citizen
arrays deny admin; legitimate admin and unknown legacy strings remain supported.
Provider helpers support both package and top-level imports. All six synchronous
provider handlers run in FastAPI's worker pool, so slow scans no longer stall the
ASGI event loop. The existing scan cap and non-atomic census limitation remain.

Users responses sanitize authentication/internal/validation errors, retain
no-store and add Vary Authorization (#564). Queries use actor-specific keys,
no inactive retention, disabled unauthorized reads and guarded mutation controls;
detail remounts on actor transition and ignores late success callbacks after
unmount (#563). ISO year zero is rejected to match Python's datetime contract.

Observed pre-fix regressions: backend14 failures/7 controls (signed roles/identity,
package import, concurrent health); frontend16 failures/6 controls (guard and
middleware); private errors5 failures/2 transport controls; actual AuthProvider3
failures/1 control; actor cache2 failures; year zero1 failure. The cache replay
corrected a test precondition that initially matched two equivalent email labels;
only the corrected pinned-head failure counts as product evidence. Current
coordinator scoped replay: backend160 passed, frontend90 passed, full TypeScript
and scoped lint exit0. Compatible runtimes, inert identities/HTTP and no dotenv.

The redirect-to-body suggestion is refuted: actual installed official auth-js
resetPasswordForEmail with injected fetch sends redirect_to in query and email in
JSON; the owned httpx transport retains matching query round trips. Official
Supabase auth RecoverParams excludes that JSON field, and utilities.getRedirectTo
reads header/form query. See the official sources:
https://github.com/supabase/auth/blob/master/internal/api/recover.go and
https://github.com/supabase/auth/blob/master/internal/utilities/request.go.
No live reset email was sent. Deployed allowlists remain provider configuration.

Cross-lane write policy (#553) and combined acceptance remain coordinator checks:
the boolean audit writer must reuse the overview lane's safe_audit_payload before
all four current callers can be certified; the overview user count must describe
Auth identities, including those without profiles. Final merged-head receipts
will supersede the initial lane-only/xfail counts above.
