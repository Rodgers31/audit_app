# B15 generation: factual drafts and guarded shadow decisions

Delivery checkout: `/Users/roger/.codex/worktrees/b15-generation/audit_app`.
Branch: `codex/b15-generation`. Frozen base: `06896185005d822c4b29888138b984510dd1fdbd`.
The primary dirty checkout was not edited, installed into, reset or stashed.
Delivery head and draft PR will be recorded below after creation. No merge or deployment is authorized here.

## Implemented and locally tested

- Strict committed source/evidence contracts, exact decimal strings, factual-v1 templates, first-observation baselines, explicit backfill, semantic/versioned changes including A→B→A, and one event per generated post.
- Generated pending-review drafts use the existing immutable revision, human attestation and publication workflow. Edits retain evidence; placeholder checks include destination overrides and evidence. Corrections cancel superseded work through the existing global permit ordering and preserve worker-owned/attempted history.
- Separate default-off draft/shadow controls; immutable disabled/shadow rule versions; account/source/category allowlists, freshness/cadence/access/budget checks; immutable context-bound advisory decisions and paginated history. Shadow evaluation creates no approval, target or publication.
- Authenticated private/no-store admin routes and existing-style UI for evidence, controls, detection, rules, decisions and origin/category filters. The bounded detect endpoint accepts record/ingestion IDs, never HTTP facts. Receipt preflight releases its connection before fresh source readers, avoiding the observed two-connection pool deadlock.
- Optional default-off post-commit `maybe_generate_committed` hook: exact environment ceiling plus runtime controls; at most 1000 IDs in chunks of 25, fresh independent readers/transactions, pipeline audit actor, explicit partial confirmed counts, cooperative 30-second deadline, transaction-local SQL bounds preserving stricter inherited settings, precommit rollback and truthful late-commit counts. Borrowed active/dirty/cached sessions are refused without rolling back caller state.

The ETL producer/selector/native CLI caller is an explicit cross-lane dependency,
not duplicated in this branch. Without its reviewed adapter, detect returns unavailable.
Only qualified actual CoB expenditure currently has that adapter. Other typed source
names do not establish working parsers or evidence adapters.

## Integration and shared edits

Reserved additive migration `a704b15a0001` currently follows `a545b14a0001`.
Its complete chain was replayed from an empty owned PostgreSQL database. Actual
schema/metadata comparison returned no differences. The coordinator must serialize
the batch's migration predecessors and independently replay the final single chain;
the isolated candidate heads are not a production migration plan.

Shared backend edits: `social/__init__.py` model registration; `social/api.py`
router/filter wiring; `social/models.py` source-event FK and named unique;
`social/service.py` evidence retention, generated-source authorization checks,
audit actor and filters. Shared frontend edits: `SocialComposer`, `SocialWorkspace`,
`lib/api/social.ts`, `lib/hooks/useSocial.ts`. No worker repository, worker grants,
role-contract, main.py, dependency manifest or lockfile changes.

ETL dependency checkout: `/Users/roger/.codex/worktrees/b15-etl/audit_app`.
Relevant files: `backend/seeding/source_observations.py`, `generation_dispatch.py`,
`cli.py` and its safe outcome presentation helper. Actual adapter→HTTP→draft and
selector→dispatcher→hook proofs load the peer's exact source files against this
lane's database. The native caller supplies the hard main-thread timeout; the
generation hook alone cannot interrupt an opaque blocking factory.

## Verification and evidence

Evidence root (local, retained outside Git):
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/generation-evidence-v1`.

- `final-v2/receipt.json`: source/runtime/command/log hashes, unchanged sources; **50 passed, zero skipped** normally and the same **50 with Python -O**; **3 actual cross-lane integration tests**; **463 frontend tests**. These inventories overlap independent review selections and must not be summed as unique tests.
- Core command: `.venv/bin/python [-O] -m pytest --confcutdir=backend/tests/social backend/tests/social/test_generation.py backend/tests/social/test_generation_api.py backend/tests/social/test_generation_integration.py backend/tests/social/test_generation_postgres.py -q -rs`. Use `PYTHONPATH=backend:backend/tests/social`, `PYTHON_DOTENV_DISABLED=1`, and `B15_GENERATION_TEST_DB_URL` targeting the guarded owned database on 55400.
- Frontend command: `node_modules/.bin/jest __tests__/social-generation.test.tsx __tests__/admin/social --runInBand` from `frontend`.
- `backend-broader-v1.log`: 145 passed; 3 existing delivery-history PostgreSQL fixtures skipped because they require their historical fixed port. Their guards were not repointed and this is not a full zero-skip backend claim.
- `browser-v3/browser-result.json`: actual Google Chrome 155.0.8059.80, desktop/mobile, production components with inert HTTP/auth fixtures; no external requests/errors and no horizontal overflow at 390px. Screenshots retained. Command: `B15_GENERATION_BROWSER_OUTPUT=<fresh evidence directory> node browser-fixtures/generation/verify.mjs`.
- Full TypeScript check **blocked**: `components/map/StyledGeography.tsx(36,9) TS2322`, unchanged byte-for-byte from frozen base, using locally cloned dependency runtime. No generation TypeScript diagnostic was emitted. This does not prove a clean install from the lockfile or a green full typecheck.
- `migration-full-chain-v2.log`: empty-database Alembic replay. `hook-pg-bounds.log`: real PostgreSQL preserved inherited 50ms/25ms limits, rejected pg_sleep, and did not leak settings to the next transaction.
- Independent executable Spec review: `spec-review/REPORT-v2.md`, `integration-v1/REPORT.md`, `deadline-v1/REPORT-v2.md` (final 30 passed normally and the same 30 with -O). Standards: `standards-review/STANDARDS_FINAL.md`, `STANDARDS_POOL_ADDENDUM.md`, `STANDARDS_HOOK_ADDENDUM.md`, `STANDARDS_DEADLINE_ADDENDUM.md` (final 89 passed normally and the same 89 with -O). No unresolved finding in those executed scopes. Reports bind exact source hashes and preserve discovered failures.
- Observed reds retained for baseline evidence loss, placeholders/overrides, backfill, stale shadow contexts, strict schemas, pool starvation and deadline/commit uncertainty. `final-v1` remains explicitly failed/superseded because of ambiguous duplicate lineage in the positive cross-lane fixture; it was not rewritten into a pass.

Python runtime is owned `.venv` with read-only reused cached packages and locally
installed missing dependencies. Frontend dependencies are an owned local clone;
no primary checkout installation or paid service was used.

## Remaining original requirements and acceptance gates

CODE INTEGRATION: combine the reviewed ETL adapter/selector/caller and serialize the
batch migration chain; independently review the merged shared-file diffs. Other
source/measure adapters remain unimplemented/unavailable. Real stored publication
dates and explicit source qualification require coverage before evidence is eligible.

DEPLOYED / LIVE ACCEPTED: neither is claimed. Shadow-versus-human operating outcomes,
narrow live automation rollout and production/provider/storage qualification remain
separate gates. No automatic approval, scheduling or publishing was enabled. Global
publishing/media uploads remain off; X remains zero-budget blocked and TikTok access
remains unavailable absent qualification. No live flags, grants, credentials, posts,
uploads, storage deletions, hosted builds, bot reviews or paid resources were changed.
Parent roadmap #476 remains open. Fixtures do not establish all-plan completion.

## Delivery and resources

Draft PR, final commit binding, remote review readback and cleanup are recorded in
the final delivery update and shared `lane/generation-status.md`. Local database
`b15-generation-postgres` on 127.0.0.1:55400 and its owned anonymous volume must be
removed after final cross-lane replay. Chrome fixture server on 33506 stops in its
finally block. The worktree and owned runtime caches remain for coordinator review.
