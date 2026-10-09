# Admin social runtime implementation — Batch 6

2026-10-08. Lane [#549](https://github.com/Rodgers31/audit_app/issues/549), parent
[#545](https://github.com/Rodgers31/audit_app/issues/545).
Pinned base: `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`.
Worktree: `/Users/roger/.codex/worktrees/admin-social-runtime/audit_app`.
Branch: `codex/admin-social-runtime`.
Product implementation commit: `90b71d799564403dd4bd23ddbab1d58491d72cba`.
The final branch also commits this handoff and the expanded browser verification.

## Completed local changes

The actual `main.app` now installs the existing Sentry privacy policy before
request middleware captures, only with the exact server opt-in
`SENTRY_ENABLED=true` and a valid nonempty server `settings.SENTRY_DSN`.
Omitted opt-in or `false` ignores the DSN, including its secret-manager lookup.
Unsupported opt-in, missing/malformed DSN, malformed/nonfinite/out-of-range
trace sampling, or SDK installation failure stops construction with the fixed
message `Sentry startup configuration is invalid.` The shared helper's direct
sampling parse failure now also uses fixed text without exception context.
Default trace sampling remains 0.1 after explicit activation; accepted overrides
are finite values from 0 through 1. Profiles remain disabled even if a profile
rate is supplied. Standard SDK process lifecycle owns flush/shutdown; no
application worker or scheduler was introduced.

The frontend selection decoder now accepts strict boolean native-adapter
metadata from the existing backend contract while requiring account
`publishing_enabled:false`. The Accounts card reports a registered adapter and
states that delivery gates still apply. Previously it rejected that valid
selection and always reported the adapter unavailable. The contract correction
was recorded in this handoff before editing the consumer; API shape and account
control semantics are unchanged.

All-state GitHub searches found no dedicated duplicates for the two newly
confirmed defects. They are tracked as [#552](https://github.com/Rodgers31/audit_app/issues/552)
(direct sampling configuration text) and [#555](https://github.com/Rodgers31/audit_app/issues/555)
(native selection metadata/display). Both remain open for coordinator acceptance.
The missing automatic startup installation was already explicitly tracked by #549.

The caller audit confirms `main.app` is the sole automatic installation seam;
explicit `setup_sentry` callers retain the same sampling/privacy safeguards.
The backend's existing connection selection writes disabled publishing and
projects the injected registry's capability snapshot. `connectionApi.select`
uses the corrected strict decoder, and both Facebook/Instagram AccountCard
instances display that metadata. Registry availability alone does not alter
stored account admission, controls, approval, worker or delivery authorization.

## Baseline and registration boundary

Executed baseline on the pinned checkout: actual app construction, 35 unique
social method/path registrations, dormant Sentry and no injected social runtime;
136 selected backend tests passed, and 501 social frontend tests in 27 suites
passed. `social.api` already includes the connection and media routers, so the
single existing main mount was retained. No duplicate router mounting was added.

An initial TestClient lifespan attempt against an empty owned SQLite file failed
on unrelated reference/ingestion tables. It was not evidence of application
readiness. Subsequent actual-app checks deliberately avoid lifespan seeding,
warmup and background tasks. Full application lifespan, production schema and
shared JWT/session middleware are not certified by these fixtures.

Only the six-line social/monitoring registration seam in `backend/main.py` was
changed. Shared authorization, Axios/middleware, models, migrations, manifests
and lockfiles were read-only. The dirty primary checkout was untouched.
No native registration, public privacy/deauthorization endpoint, storage cleanup
runner, per-replica scheduler or production worker was automatically installed.
The existing explicit native registration/API/worker interfaces remain the
assembly contract; callers still own their supplied runtime resources.

## Executed acceptance matrix

| Surface/boundary | Executed evidence | Meaning and limit |
| --- | --- | --- |
| Actual app registration/access | All 35 unique social method/path routes returned 401 and 403 with `private, no-store`; administrator reads succeeded against the current migrated schema | Confirms route dependency wiring; denial dependency overrides do not certify deployed JWT validation |
| Default operational state | Actual app: publishing false, adapters empty, worker unavailable, upload false, generation/auto-approval/auto-schedule/auto-publish false; connection unavailable | No feature activation; no public privacy routes |
| Actual app telemetry | One SDK init; 4 transactions with status 200/500/401/500; 2 error events; 0 profiles; 0 private fixture markers | Real SDK 2.53.0 and FastAPI middleware, memory transport, blocked networking; exporter/host proof remains missing |
| Manual editorial flow | Hydrated production editor: draft/save/validate/submit/review/approve/schedule, schedule acknowledgment and scheduled queue | Contract responses with inert auth; no real publication |
| History/worker outcomes | Browser confirmed destination link and independent history panel; actual PostgreSQL/main.app five-destination cascade with four fake successes/one failure, target-only retry and frozen history guard | Fake providers/worker clock; retry never reposted the four successes |
| Accounts | Disabled connection gate, then explicit inert popup/callback/discovery/exact Page selection, ungranted Instagram disabled, native capability displayed with publishing false, health and local disconnect | One intercepted provider navigation fulfilled locally; actual standalone callback CSP/no-store/no-referrer; no provider request |
| Media | Library/search/empty result/select/default alt text; disabled upload; deliberate preview-unavailable response | Ready-asset contract fixture, no signing/upload/storage connection |
| Stale/repeated command | Two failed saves retained the same idempotency key/body and unsaved local edits | `VERSION_CONFLICT` fixture; existing mutation tests cover bounded retry/actor changes |
| Error/malformed states | API permission error rendered; malformed system status failed closed | Exact contracts reject unexpected method/path/prefix; no generic success fallback |
| Roles/mobile/keyboard | Production AdminGuard editor/signed-out redirects and no mutations; 320/390 viewport panel/preview, no document overflow, visible focus | Inert AuthProvider alias; excludes shared middleware/Supabase session exchange; not a WCAG conformance claim |
| Filters/paging/polling | Existing social unit suites executed actor-scoped caches, bounded polling, filters/history/media paging and loading/empty/error/malformed controls | Browser uses one-page fixtures; multi-page behavior is unit-level evidence |

Final browser receipt: **10 checks, 57 intercepted API requests, one locally
fulfilled provider navigation, zero external requests and zero page errors**.
This builds a temporary Next production project importing the real social
components/hooks/decoders, production AdminGuard and actual callback response.
Only auth/session and HTTP responses are explicit test aliases. It is not a
full frontend production build or a production host acceptance test.
The temporary project/server is removed after execution.

## Retained observed-red/green evidence

The committed regression tests were executed against the unfixed pinned main
files before being restored to the repaired implementation:

| Regression | Observed red | Repaired result |
| --- | --- | --- |
| Final actual-app startup/direct-helper cohort | 10 failed, 2 passed on pinned `main.py`/instrumentation | 12 passed |
| Direct sampling exception text alone | 1 failed, 11 deselected | 1 passed, 11 deselected |
| Native selected-account decoder | 1 failed, 6 passed | 7 passed before adding card controls |
| Native Accounts card | 1 failed, 1 passed, 7 skipped with pinned component | Final decoder/card cohort: 9 passed |

These cohorts overlap and must not be summed. The startup positive control
preserves real healthy/error captures and useful numeric status; an empty
capture does not pass. Inert private markers cover callback queries, request
body, thrown errors and the actual middleware capture boundary. Existing
monitoring suites retain malformed event/transaction/breadcrumb and profile
controls from the merged privacy repair.

Independent execution additionally found two defects in the newly authored
browser fixture, rather than production code: wrong API prefixes initially
received valid fixtures, and five malformed provider requests initially received
a local redirect. Both were corrected before the final browser run. The latest
extracted-handler replay executes 43 cases: 13 invalid API requests rejected,
21 hostile/disabled provider requests aborted, only the valid provider GET
redirected locally, and six exact responses passed production decoders.
No external networking occurred in the independent replay.

## Exact final verification commands and results

Commands run from the worktree above unless the frontend directory is specified.
The Python runtime is the existing read-only 3.13.9 environment. The assigned
PostgreSQL fixture is an owned loopback container on 55474 with inert credentials;
three cases apply the five unchanged social migrations in random schemas and
drop only those schemas. It never adopts a shared or remote database.
To reproduce after cleanup, create a fresh owned container from the already
installed `postgres:16-alpine` image with database `social_admin_runtime_test`,
user `socialbatch6`, inert password `inert-local-only`, and binding
`127.0.0.1:55474:5432`; wait for `pg_isready` before the command. No production
connection settings or external image pull are needed.

```sh
env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin \
 PYTHONPATH=/Users/roger/.codex/worktrees/admin-social-runtime/audit_app/backend \
 PYTHON_DOTENV_DISABLED=1 ENVIRONMENT=test \
 DATABASE_URL=postgresql+psycopg2://test:test@127.0.0.1:55474/unused \
 SOCIAL_ADMIN_RUNTIME_TEST_DATABASE_URL=postgresql+psycopg2://socialbatch6:inert-local-only@127.0.0.1:55474/social_admin_runtime_test \
 /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest -q -rs \
 backend/tests/social backend/tests/test_monitoring_redaction.py \
 backend/tests/test_monitoring_review_regressions.py backend/tests/test_social_monitoring_startup.py
```

Result: **1,814 passed, 154 skipped, two warnings**. The existing SQLAlchemy `declarative_base()`
warnings are in `backend/database.py:64` and `backend/models.py:25`.
The earlier minimal-PATH run passed 1,792 with 176 prerequisite skips; the final
command includes the installed read-only media tools and Docker discovery.
Final prerequisite skips are detailed below; no skip guard was weakened.
The separate startup/current-schema cohort passed **15 tests, zero skips**.

From `/Users/roger/.codex/worktrees/admin-social-runtime/audit_app/frontend`:

```sh
env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin CI=true \
 /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/jest/bin/jest.js --runInBand

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
 /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/typescript/bin/tsc --noEmit

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
 /Users/roger/.nvm/versions/node/v22.19.0/bin/node node_modules/eslint/bin/eslint.js \
 lib/api/socialConnections.ts components/admin/social/connections/MetaAccounts.tsx \
 __tests__/social-connections/admin-runtime-native.test.tsx tests/socialRuntimeAuth.ts \
 tests/socialRuntimeHarness.tsx tests/socialRuntimeBrowser.mjs

env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin \
 /Users/roger/.nvm/versions/node/v22.19.0/bin/node tests/socialRuntimeBrowser.mjs
```

Results: **1,674 tests passed in 131 Jest suites, one existing optional receipt
case skipped**; TypeScript exit 0; scoped ESLint exit 0; browser exit 0 with the
receipt above. The Jest skip is `BudgetTab.debtAbsence.test.tsx` without
`FINANCIAL_ABSENCE_HTTP_CAPTURE_DIR`, outside this lane. The earlier final social
subset passed 510 in 28 suites. Node 22.19.0, Next 15.5.27, React 19.2.4,
Jest 29.7.0 and Playwright 1.58.2 were read from installed dependencies.
The node_modules link reuses a read-only installed worktree dependency tree;
both lockfiles have SHA256 `dac3afaab71df334fc5e7d1c1a918c307f8a71fd750b91b1672546b044a0de5c`.
No packages were installed and no manifest/lockfile was edited.

The **154 backend prerequisite skips** are unchanged, separately assigned local
PostgreSQL cohorts: 53 social domain/schedule cases, 70 worker cases, eight
media-cleanup cases, two connection cases, 17 privacy cases, two integration
cases and two media-operator cases. Their fixed database guards include ports
62124/62238/62249; none was repointed to another lane or weakened. The final
PATH-aware run also executed all 13 cached PostgreSQL-17 readiness-role cases
in their own fixture-owned disposable container, plus nine actual installed
ffmpeg/ffprobe media controls. The three new PostgreSQL-16 current-schema cases
ran on assigned port 55474 without skips.

Local logs are `/tmp/admin-social-batch6-{backend-final,jest-final,browser,tsc,eslint}.log`,
`/tmp/admin-social-batch6-browser.json`, and the retained
`startup-final-red`, `direct-red`, `native-red`, `card-red`, `runtime-final` logs
with the same prefix. These are local verification records, not deployment
receipts. This committed handoff retains their commands, observed results and
boundaries independently of temporary log retention.

## Independent review dispositions

- **Standards: clear.** Zero hard-rule violations or actionable Fowler smells.
  Independently executed 12 startup tests, 26 monitoring redaction tests and
  9 native frontend tests; follow-up syntax/source review of the browser expansion
  passed. Existing SQLAlchemy warnings only. No independent browser/PG execution
  was claimed.
- **Spec: local pass.** No proven product/spec violation. Initial Accounts and
  nonadministrator browser-proof gaps were identified and repaired; reviewer
  independently inspected the final sources and parsed the final author browser
  receipt. Independently executed 12 startup and 9 native frontend tests.
- **Adversarial: clear after repairs.** Executed 63 startup/configuration probes,
  real memory-only captures, 89 production decoder cases (3 valid, 86 rejected),
  the 9-test native suite, and the final 43-case fixture interception replay.
  Direct sampling disclosure became #552 and was independently replayed after
  repair. These counts overlap authored checks and are not additive totals.

Targeted security review preserved default-deny activation, strict selected
account publishing false, no secret fields, safe exceptions, callback origin/
source/state validation and no-store. Design review is solid for this small
change: the native capability label now matches its metadata and keeps the
manual confirmation/delivery gate visible. Executed narrow mobile/focus checks
support that assessment; no broad redesign or compliance claim is made.

## Remaining production evidence and next acceptance work

[#525](https://github.com/Rodgers31/audit_app/issues/525) stays open. Obtain the
exact intended host/build/SDK, actual opt-in/options/initialization, DSN custody,
exporter access/retention and authorized inert success/failure captures with
healthy controls. The local installed SDK was 2.53.0. The previous minimum-SDK
privacy proof is merged, but actual-app startup on that separate runtime was not
re-executed here. Deployed SDK and upstream CDN/proxy/access-log redaction are
separate required receipts.

[#488](https://github.com/Rodgers31/audit_app/issues/488) stays open for exact
Meta app/product/mode/access/permissions/content tasks, registered redirect and
origin, key/digest custody and tested recovery/rotation, production schema and
effective roles, approved privacy/retention/deauthorization decisions, upstream
redaction and separately authorized owned-account discovery/selection/reconnect/
disconnect acceptance. Existing durable privacy/ownership primitives were not
recreated or publicly mounted. Valid fixtures do not grant provider authority.

[#490](https://github.com/Rodgers31/audit_app/issues/490) stays open for the
actual private social bucket, exact browser origin/host, authorized CORS and
signed-PUT/host receipts, inventory/quota/backup/retention, bounded maintenance
visibility and authoritative remote-write quiescence. Ready-original deletion
remains deferred. Source-evidence storage acceptance does not certify the social
media bucket or delivery fetch path.

[#481](https://github.com/Rodgers31/audit_app/issues/481) stays open for seven
representative closed deployed days, authoritative organization/provider charges,
measured social transfer, ordinary API/ingestion/restart/worker workload, accepted
always-on hosting and connection headroom. Offline or fixture transfer results
cannot authenticate a bill or justify a plan/hosting decision.

Follow-up coordinator acceptance should run the separately assigned existing
PostgreSQL lanes and the complete shared application/auth environment, then
review/merge the scoped draft PR. No merge, issue closure, Copilot request,
deployment, production migration, provider/storage mutation, publishing or paid
service activation occurred. No unfinished or interrupted implementation step
remains in this lane. Owned fixture server/project/database resources are cleaned
up after checks; the managed worktree remains available for review.
