# PR #492 parent integration receipt

2026-10-03 (America/Chicago). Read with [the finding dispositions](REVIEW_492.md)
and [the batch ledger](BATCH_2_STATUS.md). This supersedes the agent receipt's
local/unpushed status; the PR timeline records the reachable final head and
eventual merge identity.

## Accepted base and preserved work

Only the six media commits after original Meta head
`01c39a8ff82395aa2afa7df119529ac6f0271658` were replayed onto accepted main
`9bc2133088572fb0eceab613f7dc8c3c4def2801` (#489). This preserves #487's accepted
egress change and unrelated #493's bounded verification/auth-test changes.
The sole rebase conflict was the composer's empty-account message. Accepted
#489 copy was kept; media operation/context controls were preserved and the
combined mounted-component tests passed. No unrelated branch was checked out,
reset or rewritten.

The reviewed media behavior fix is reachable as `a3c7854` after rebase. It
rejects C0/DEL filenames before any upload reservation or storage request and
uses actual advertised formats/availability for upload instructions and controls.
The existing MP4 conditional and strict capabilities decoder were already
correct and were retained. The agent's red/green receipt explains these
dispositions rather than accepting every review suggestion literally.

## Parent fixture hardening: red then green

The inherited `media_pg` fixture checked the URL authority but then forwarded
the original libpq query options. This was the same real safety defect found
on #487 and fixed across the core fixtures in #489. It was reproduced without
opening an engine or connecting to any rejected target.

`test_media_target_safety.py` intercepts `create_engine` and checks remote
`host`, `hostaddr`, `service`, port/database overrides, search-path options,
duplicate hosts, bare `?`, and blank options. An additional test sets hostile
`PGHOSTADDR`/`PGSERVICE` and inspects effective psycopg2 arguments. The initial
fixture produced **12 failed**; reusing `local_postgres_url` produced
**12 passed**. Accepted URLs pin literal host and hostaddr, assigned port and
database; percent-encoded password characters remain supported by the shared
helper's own tests. Production connection settings were not restricted.

## Final combined verification

All commands ran in the owned media integration worktree, using existing
read-only Python/node dependencies and the explicitly assigned local
PostgreSQL databases on `127.0.0.1:62124`. Dotenv, automatic seeding and warmup
were disabled. No production/default DSN was used.

Backend command, with the three assigned database opt-ins set:

```sh
PYTHONPATH=backend /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest \
  backend/tests/social \
  backend/tests/test_database_import_modes.py \
  backend/tests/test_response_models.py \
  backend/tests/test_etl_admin_endpoints.py \
  backend/tests/test_health_endpoints.py \
  backend/tests/test_write_routes_require_auth.py \
  -q --tb=short
```

**737 passed in 37.16 seconds**, no skips/failures; two pre-existing SQLAlchemy
declarative-base deprecation warnings. The total comprises **693 social tests
and 44 existing backend regression tests**. This includes actual isolated
PostgreSQL DDL/RLS/FK/downgrade, claim/cleanup races and process recovery; actual
available native media inspection; fake-provider HTTP; API/telemetry/import
boundaries. It does not establish production permissions, hosting or CORS.

Frontend commands from `frontend`:

```sh
./node_modules/.bin/jest --runInBand --no-cache __tests__/admin/social __tests__/social-connections
./node_modules/.bin/tsc --noEmit --incremental false
./node_modules/.bin/next lint \
  --file components/admin/social/SocialComposer.tsx \
  --file components/admin/social/media/MediaUpload.tsx \
  --file __tests__/admin/social/media-review-492.test.tsx
```

**441 tests passed across 23 suites in 7.708 seconds**. TypeScript exited 0;
scoped ESLint reported no warnings/errors. The lint command also printed its
existing Next.js deprecation notice. Historical responsive screenshots were
preserved, not reported as rerun.

## Merge and operational boundaries

Genuine inline and review-body comments were refetched after the prerequisite
merges. A pushed fix precedes replies and thread resolution. The only remaining
inline #492 thread concerns the now-rejected DEL filename; the body-only
capability message finding is separately addressed in the PR timeline.

Actions remains disabled. No new hosted CI result was claimed, manual workflow
dispatched, required check fabricated or rule changed. Exact-head administrator
merge uses the owner's standing authorization and is recorded separately from
these local test receipts. Vercel preview status is checked on the pushed head.

No live OAuth, accounts, storage, publishing, production migration, dependency
installation, deployment/environment changes or existing-process restarts were
performed. The primary dirty checkout and unrelated sessions remain untouched.
Real publishing/automatic approval remain off. #481, #488 and #490 retain live
egress/hosting, Meta operational and private-media maintenance/retention gates;
local fixes cannot close those operational acceptance items.
