# Batch 7 ETL UI handoff

Lane [#568](https://github.com/Rodgers31/audit_app/issues/568), companion
[#554](https://github.com/Rodgers31/audit_app/issues/554), parent
[#545](https://github.com/Rodgers31/audit_app/issues/545). Local acceptance:
2026-10-09. Delivery stops at a scoped draft PR; coordinator acceptance and
merge remain separate work.

## Source and ownership

| Identity | Value |
| --- | --- |
| Managed worktree | `/Users/roger/.codex/worktrees/batch7-etl-ui/audit_app` |
| Branch | `codex/batch7-etl-ui` |
| Pinned main | `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d` |
| Pinned tree | `712b43650b1203ffd84583b67d07d30775669b1e` |
| Initial implementation | `f27a3fc6a7aea891bc6cf149a3946d28fb85f1f3` |
| Final product source | `6087347edf1412d232302f986166c889403d17da` |
| Accepted tests/browser capture | `dba511b9fec01ce63843fe576ef20f6e2539375a` |
| Delivery revision | Commit containing this handoff; later changes are documentation only |

Frozen inputs were read from
`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_7_SESSIONS/`:
`SPEC.md` and `dispatch-contract-examples.json`. The test examples are an exact
copy. No contract change was needed. No AGENTS.md/CLAUDE.md was found in the
checkout or ancestors. Repository Copilot instructions, CONTEXT.md,
TESTING_GATES.md and accepted Operations/Users handoffs were read.

Only the owned ETL UI tree, new dispatch parser, scoped tests/browser files,
`backend/tests/batch7_etl_ui_fixture.py` and this lane's documentation changed.
The existing ETL page adds the panel inside its approved shell. The calendar
parser, shared auth/Axios/middleware, product backend, manifests and lockfiles
remain unchanged. The dirty primary was read only; its changes and dotenv files
were not copied or loaded. No paid design/bot activation or redesign occurred.

## Result

- Separate dedicated-worker evidence enables each source only after strict
  current capability validation. Malformed, unavailable, stale and denied
  evidence disables controls. Calendar calculations retain their existing
  unverified meaning.
- Run Now uses an explicit native confirmation with Cancel initially focused,
  keyboard focus wrap, Escape and focus return. Dry Run says no publication.
  Every submitted intent has a canonical UUID and explicit source/mode/generation.
  No automatic POST retry occurs.
- Ambiguous acceptance keeps the same actor/source/mode/key/generation in one
  browser-memory slot across same-actor renewal, profile-null guard unmount and
  page remount. Manual recovery can retrieve the original receipt after worker
  evidence expires. Changing source/mode rotates the key. This memory does not
  persist through a full browser reload and stores no credentials or receipts.
- Reads and mutation callbacks use actor/session-lifetime cancellation and
  current-access checks. Actor changes, renewal/revocation, hidden pages and
  unmount suppress stale results. A 401/403 hides private capability/history
  evidence and cancels active work.
- Acceptance is displayed separately from queued/running/completed/failed/
  interrupted execution. Only an actual non-null positive observation ID is
  linked. Interrupted work offers receipt refresh without execution retry.
  Receipts never certify financial freshness or an immutable audit ledger.
- History has bounded canonical URL filters/pages, deterministic receipt
  validation, safe detail return links and usable Previous on an empty later
  page. Rapid filter edits merge while routing is pending. Detail identity,
  version progression, immutable recorded timestamps and microsecond chronology
  are verified before display. Visible authorized active receipts poll; terminal,
  error and hidden states stop polling.

## Executed acceptance

Counts overlap and must not be added together. Raw outputs and generated media
are retained outside git; [artifacts.json](batch7-etl-ui-evidence/artifacts.json)
pins the external manifest and its SHA256. The committed evidence contains
compact commands/results plus the three independent review reports.

| Check | Actual result and identity |
| --- | --- |
| Pinned Operations/Users/auth baseline | 10 suites, 206 passed on pinned main |
| Initial changed-behavior red | Rendered and actual-browser old ETL page could not supply Run Now; both failed at the missing control |
| Parser chronology red/green | Original UTC tie/order case failed; strict UTC and microsecond chronology cases pass after repair |
| Renewal regression | Author rendered red: 1 failed; independent immutable f27a3fc red: 2 failed. Final independent original and guard-remount/isolation replays: 2 + 2 passed |
| Adversarial receipt red/green | Original source: 6 failed / 25 passed across microsecond ordering and terminal finish rewrite cases. Final independent expanded suite: 44 passed |
| Filter regression | Author rapid-edit red: 1 failed. Independent original component: 2 failed (dropped filters and resurrected filter after Clear). Current component: both pass |
| Scoped final compatibility | 13 suites, 337 passed before the two extra independent filter cases; includes the original 206 compatibility controls |
| Final full frontend Jest | 147 suites, 2,063 passed, 1 existing skip; exit 0. Includes both added filter cases |
| TypeScript | `--noEmit --incremental false`, exit 0 after final test delta; no diagnostics |
| Scoped ESLint | Owned UI/parser/tests/browser files, zero errors/warnings; exit 0. Existing Next lint deprecation notice only |
| Production Next build | Exit 0; includes `/admin/etl/commands/[commandId]`; final product source 6087347 |
| Fixture syntax | Clean-env `py_compile`, exit 0; no product backend import |
| Final actual-browser fixture matrix | 24/24 Chromium journeys; exit 0, 54.9s; accepted test source dba511b |
| Local secret/diff check | Scoped credential-pattern scan: 17 source/test files, zero matches; staged whitespace check passed |

The browser matrix uses real production Next, the existing middleware,
AuthProvider/AdminGuard and shared Axios against an inert loopback contract
fixture. It covers ready/unavailable/malformed/stale capability, confirmed Run
Now and Dry Run, lost response after a committed acceptance, same-key recovery
after worker unavailability, filters/page/back/detail/identity matching,
failed/interrupted/error states, 401/403, deferred confirmation and committed
in-flight actor/renewal/role/hidden/unmount transitions, polling pause/stop,
initial hidden reads, and keyboard/mobile width at 375px. The backend fixture is
synthetic in-memory storage: its observation IDs are test values, not evidence
of actual runner persistence, publication, leases, fencing or audit atomicity.

The first full Jest invocation included fixture Supabase environment variables
and failed two unchanged retry-budget cases due to auth SDK timer activity.
Those 19 cases passed without those variables, and the final full clean-env
suite passed. Historical receipt is retained as `raw-logs/full-jest.txt`.
The penultimate browser run was 23/24 because the detail assertion ran before
navigation and matched ten history rows. Awaiting the detail URL/heading fixed
the harness; 24/24 passed. Early PNGs captured shared entrance opacity; accepted
captures wait for settled opacity and disable finite animations. Neither
historical harness result is presented as an unresolved product defect.

## Independent review

Standards and Spec review ran in parallel against the pinned diff; adversarial
verification independently executed hostile rendered/parser boundaries. Final
product review is pinned to 6087347. The later commit adds only independent
filter tests and browser assertion/capture timing.

- [Standards](batch7-etl-ui-evidence/standards-review.md): zero documented
  violations; one nonblocking duplication judgment in distinct actor/lifetime
  cleanup paths. Independent 131 scoped cases passed.
- [Spec](batch7-etl-ui-evidence/spec-review.md): the original P1 renewal-key loss
  was repaired. Zero unresolved final Spec findings; independent 203 scoped/
  compatibility cases and both retained renewal replays passed.
- [Adversarial](batch7-etl-ui-evidence/adversarial-review.md): repaired
  microsecond chronology and terminal timestamp mutation findings; expanded
  44/44 cases and TypeScript passed. Two new filter cases independently failed
  against the original component and passed against current source.

The reports distinguish original findings, repair evidence and final results.
Reviewer raw receipt manifests are linked in their reports. No reviewer
certifies an actual worker or hosted gate from these UI fixtures.

## Runtime, resources and cleanup

Node 22.19.0; Next 15.5.27; React 19.2.4; Jest 29.7.0; Playwright 1.58.2;
TanStack Query 5.90.21; TypeScript 5.9.3. Python 3.13.9; FastAPI 0.129.2;
Uvicorn 0.41.0. Read-only Python runtime:
`/Users/roger/Documents/projects/audit_app/venv/bin/python`.
Owned frontend symlink reuses the compatible existing runtime at
`/Users/roger/.codex/worktrees/social-batch3-integration/audit_app/frontend/node_modules`.
No install or shared runtime mutation occurred. Exact owned/runtime
manifest and lockfile content matched before use:

- package SHA256 `62c4d3857990d6426242641376be810037b3d8acf694017405bb99a4f08b914e`
- lock SHA256 `dac3afaab71df334fc5e7d1c1a918c307f8a71fd750b91b1672546b044a0de5c`

Commands used `env -i`, owned paths and `PYTHON_DOTENV_DISABLED=1` for Python.
JWTs/identities/provider transports were inert. HTTP bound only owned loopback
3162 (Next) and 8162 (UI fixture); external HTTPS was blocked in browser tests.
No PostgreSQL or worker process was required or started for this UI lane;
reserved 55482 remained unused. Companion ports 8161/55481 were untouched.

Both owned servers were stopped after acceptance; `lsof` confirmed no listener
on 3162/8162. Owned Jest/Python caches were removed. Managed worktree, ignored
production build and read-only dependency symlink remain for coordinator replay.
Raw logs, traces and screenshots remain in the hashed local artifact directory.
Reviewer resources were archived and cleaned by their owners.

## Issue accounting and remaining work

[#568](https://github.com/Rodgers31/audit_app/issues/568),
[#554](https://github.com/Rodgers31/audit_app/issues/554) and
[#545](https://github.com/Rodgers31/audit_app/issues/545) remain OPEN. All-state
searches and results are recorded in
[issue-accounting.json](batch7-etl-ui-evidence/issue-accounting.json). UI findings
were repaired inside #568; no new issue or issue closure was made. Existing
worker activation/exclusion follow-up #572 was observed in deduplication and
belongs to worker/coordinator acceptance.

Coordinator must replay this UI against the actual #554 backend/dedicated
worker, persisted matching ingestion observations, real acceptance audit and
generation/recovery semantics. Additional source mappings remain a worker
decision. No live financial execution/publication, provider/user/email/storage
mutation, migration or deployment occurred.

GitHub Actions permissions returned `enabled:false`. Hosted security/quality,
full backend coverage, financial ETL, broad legacy browser suites, staging and
production gates were not executed or certified. Full Jest here was run without
coverage instrumentation; ESLint was scoped to owned files. Local UI/build
acceptance is not full deployment CI. No workflows/rules/statuses were changed,
no extra bot review was requested, and no merge was performed.
