# Batch15 platforms handoff

Worktree: `/Users/roger/.codex/worktrees/b15-platforms/audit_app`.
Branch: `codex/b15-platforms`. Frozen accepted base: `06896185005d822c4b29888138b984510dd1fdbd`.
Implementation revision and draft PR: final publication identifiers will be recorded in this file's delivery update; current exact branch HEAD is also recorded in shared `lane/platforms-status.md`. No merge or deployment is authorized by this handoff.

## Implemented and tested code

Default-off real Threads/X/TikTok Accounts API connections/adapters now use the existing immutable authorization and durable worker pipeline. There are actual HTTP/API/native composition paths, not just helper functions. New namespaces isolate platform connections, material admission, budgets, runtime policy and signed event intake. Account connection saves publishing disabled.

- Separate Threads OAuth, quota/container children/parent/processing/publish/retained ID retrieval; correct graph.threads.com host and conservative transmittedUTF8 budget.
- X OAuth2+PKCE, weighted Unicode/URL/emoji counting, media operations and metadata, create/exact-public-author readback and bounded original-intent timeline recovery. All reads/mutations require explicit paid admission; zero budgets refuse without HTTP. Charges remain reserved after ambiguity/crash.
- Genuine TikTok Accounts API v1.3 console OAuth/refresh, current creator settings, explicit privacy/disclosure/interactions/consent, exact verified origin/media/hash binding, direct/draft distinction and status. Separate future-workflow permission gates schedule/reschedule/resume/retry and worker mutation. Effective content/provider-choice edits reset consent.
- Exact signed Threads/TikTok callbacks, minimal semantic dedup inbox, bounded target-only status nudge, preserved Retry-After holds and audited idempotent admin retention. Inbox/manual completion is never Published.
- Default-off strict environment and application lifespan composition; `--native-platforms` and separately selected optional worker role contract. Meta-only role matrix preserved. No supervisor/global-owner redesign.
- UI connection cards/callback/health/renew/disconnect, platform preview counters and TikTok current-settings controls, using current design components.

Details, endpoint/config fields and requirement boundaries: [IMPLEMENTATION.md](docs/social-publishing/b15-platforms/IMPLEMENTATION.md). Replays and limitations: [VERIFICATION.md](docs/social-publishing/b15-platforms/VERIFICATION.md).

## Exact current verification

Evidence packet root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/`.

Current append-only cohort `final-20261016T201824Z-2e59c5e5`:

- Normal Python3.13: **801 passed,14 skipped,0 failed**, exit0.
- Optimized Python3.13: **801 passed,14 skipped,0 failed**, exit0.
- Both cohorts include **42 actual assigned PostgreSQL cases,0 skipped**:40 adapter/integration/migration and2 actual dedicated-role cases. Full Alembic chain from an empty owned database reachesa703b15a0001. X acceptance-crash recovery retains original dispatch/fingerprint, waits without early HTTP, then confirms with one timeline GET and no second POST. Actual event consumer commits a nudge without changing publication/lease/checkpoint identity.
- **617 frontend tests/33 suites passed**,0 skipped/failed, exit0.
- TypeScript noEmit exit2 for pre-existing `StyledGeography.tsx:36`; accepted0689618 export with identical borrowed dependencies produces byte-identical output. This was not relabeled passed or fixed in the performance lane's file.
- Existing `test_native_lifecycle.py::test_cli_real_worker_bounded_scan_closes_native_then_engine` fails on candidate and accepted0689618; outdated fake repository lacks current ownership/preflight seams. Its separate failed output is retained, not counted as passed. New optional CLI/native lifecycle suites passed.

Fourteen historical role-review PostgreSQL tests require their separately guarded `SOCIAL_ROLE_TEST_DATABASE_URL`; no fixture was repointed. They remain skipped. Runtimes were borrowed read-only from the primary checkout: Python3.13.9, Node22.19, installedNext15.5.20 versus accepted manifest15.5.27. No install or hosted build/check was attempted. Local fixture tests do not prove deployed dependency parity.

The current copied recorder, JSON/JUnit/Jest outputs and raw logs bind exact argv/cwd, inert environment-key allowlist,331 source hashes before/after, generator hash, exit codes and filesystem readback. All current runs record source unchanged. Historical `final-20261016T201649Z-fd35b55f` preserves a real regression caught by broader testing:100MBvideo expansion widened the image-port ceiling. Restored8MBimages/100MBMP4; existing regression and79 material tests now pass. Other observed-red receipts preserve OAuth callback mismatch, retry timing, budget stored-row mismatches, gate/expiry handling and consent reset.

Historical author77/28/41-test receipts and fixed-path producer scripts are explicitly superseded, with original bytes retained: [EVIDENCE_STATUS.md](docs/social-publishing/b15-platforms/EVIDENCE_STATUS.md). Do not execute those scripts as current acceptance tools or overwrite their outputs.

## Independent executable reviews

- [Final Spec review and material addendum](docs/social-publishing/b15-platforms/reviews/FINAL_SPEC_v2.md):440normal+440optimized,42PG,100frontend, then79normal+79optimized material checks and direct ceiling probes. No remaining actionable finding in reviewed code.
- [Current Standards material addendum](docs/social-publishing/b15-platforms/reviews/STANDARDS_FINAL_v2_MATERIALS_ADDENDUM.md):707normal,231optimized,5nativePG,83frontend; unchanged optional-role sources also have independent2normal+2optimized actual-role proofs. Prior inventories explicitly superseded for the one material-source change.

Initial reports/failures and intermediate source-bound runs remain in external `reviews/`, `x-evidence/`, and `platform-events-evidence/`. Reviews do not grant external acceptance. Final GitHub inline comments AND review bodies will be read after draft creation; no billable review request or hosted check will be initiated.

## Integration dependencies and shared edits

Candidate migration `backend/alembic/versions/a703b15a0001_platform_connections.py` follows accepteda545b14a0001 and adds five RLS tables: OAuth flows, credentials, account budgets, app connection budgets and event inbox. Downgrade refuses retained data. No live migration/grant change. Coordinator must serialize its predecessor after peer migrations and independently replay the combined single head.

Shared edits are limited to:

- `social/__init__.py`, `adapters/__init__.py`, `api.py`: model/router/adapter registration.
- `contracts.py`, `native_admission.py`, `validation.py`, `service.py`: optional hash-compatible TikTok/FPS fields, exact capability context, paid admission, bounded reconciliation wait and future-workflow gates.
- `worker/{__main__,materials,native_runtime,policy,repository,role_admin,role_contract,runner,startup}.py`: real native composition, fenced material, reservations, event consumer and explicit optional role selection. No worker supervision/global ownership algorithm changes.
- `media/storage.py`: separate provider URL signer bounded1860seconds; browser preview remains300seconds. Media/rendering lanes must reconcile this port and qualify real video intake/rendering; sanitized adapter video fixtures alone are not that proof.
- Existing import-prefix assertion gains only exact public provider callback exceptions.
- Frontend accounts page, composer/preview/Meta explanatory copy, API types/decoder and exact callback middleware; new platform UI/API helpers. Dependency manifests and lockfiles unchanged.

**Issue700 remains an integration dependency:** current startup requires enabled media runtime. Inert enabled-media fixtures verify composition/closure only. Worker-only reads with live HTTP uploads OFF require the worker/media lane correction. Uploads were never enabled as a workaround.

## Remaining original requirements and external gates

This is a coherent tested implementation increment, **not full phases6–8 acceptance**. No deployment/live acceptance is claimed. Genuine product/application access, app review/scopes/terms, exact callbacks, stable credential/key custody and recovery inventory, budgets, TikTok property/accepted unattended workflow, subscriptions, production grants/integrated migration and actual provider/public-post acceptance remain external or coordinator gates.

Threads authenticated own-post readback/permalink does not prove anonymous/public visibility. The adapter retains Processing/unknown; lost publish identity remains unknown without resend. A source-supported proof or audited manual reconciliation is a recovery integration dependency. Native replies/topic features, remote edit/delete and analytics are not advertised here; analytics/rendering and common recovery/privacy/media work belong to separate increments/lanes. There is no automatic background token-refresh/retention scheduler; renewal and event retention are explicit admin commands.

## Resource cleanup

Owned fixture only: Dockerb15-platforms-db and namedvolumeb15-platforms-db-data removed after an empty schema/role/fullchain-database census. Inert Next fixture execsession44841 stopped withCtrl-C/exit0. Ports33505/55398 both have no listener. Temporary UI and accepted-base exports removed after evidence capture; fixture source retained in external delivery directory. Cleanup receipt with generator/readback: `platforms-evidence/delivery/resource-cleanup.json`.

No peer process/container/volume, primary dirty checkout, provider account, production database, paid resource or credentials were changed. Managed worktree is retained for coordinator integration and draft review.
