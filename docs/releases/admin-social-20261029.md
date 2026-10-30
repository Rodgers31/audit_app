# Admin and social release review packet

Prepared for owner PR review. The complete generated-post workflow is implemented in the existing draft PRs. Nothing is merged, deployed, approved, scheduled or published by this preparation; no production worker, upload service or provider connection is started. Owner review and a separate production rollout gate remain outstanding.

Latest follow-up: **all 708 previously skipped cases now execute and pass** in their required isolated fixtures. The [skip audit](admin-social-20261029/skipped-test-audit.md) and [case ledger](admin-social-20261029/skipped-test-audit.json) close the earlier unverified coverage. The broad current-environment run passes 4,484 cases plus 84 subtests; its 705 guarded skips are covered by the matrix. Combined coverage is 5,189 unique social-suite cases, with zero uncovered/failing cases. Local account rows now explicitly say **preview only**; X/TikTok preview samples are not live connections.

30 October review follow-up: [all review dispositions and validation limits](admin-social-20261029/review-comments-20261030.md) cover all 14 inline findings plus body-only localization. Navigation now protects exact dirty draft/history state, TikTok packages retain an on-site caption destination within the provider UTF-16 limit, current documentation/examples match the renderer, and the source-page negative-total claim is refuted by execution. Final frontend validation is 213 suites / 2,853 passes / one existing skip; final focused backend checks pass 327 in each Python mode. The broad social run before the narrow final Unicode delta passes 4,489 cases, 705 separately covered guarded skips and 84 subtests. No activation or source adoption is inferred from these results.

## Scope and merge order

| PR | Scope |
|---|---|
| [#850](https://github.com/Rodgers31/audit_app/pull/850) | Private admin shell, readable queue and full review pages |
| [#851](https://github.com/Rodgers31/audit_app/pull/851) | Bounded complete-cohort generation |
| [#852](https://github.com/Rodgers31/audit_app/pull/852) | Evidence-bound captions, relevant per-account hashtags, exact AuditGava source views, historical replay and publication-link guards |
| [#853](https://github.com/Rodgers31/audit_app/pull/853) | Prepared previews, automatic media format/save/validation, admin session boundaries, public report UI and illustrative local examples |

The integration checkout merges both stacks onto accepted main `7797ecb4266169c438ecd2c82e6d817d6577ff19`. Suggested topological merge order after review: #851 → #852 and #850 → #853. Deploy the resulting complete tree with both backend and frontend present. Intermediate PR heads are not independently deployable product packages. Preserve the tested bytes when updating PR bases and revalidate any conflict resolution or additional code change.

Reviewed product candidate: `review-ready-candidate-4`, 5,754 files. File-entry manifest SHA256 `2735528d6b36a6c35bc060868abf9b2cb6982e1f077356d6f1426f666a030258`; complete manifest-file SHA256 `6068da4c65d9309191bdffb4ef30f9f6f67bdd01e0c24eee59a04b3b73dbcbe1`. The first failure audit repairs nine test files. The skip follow-up repairs 22 test files and clarifies two local preview fixture files. Backend application and frontend production-component bytes remain unchanged. The [latest input receipt](admin-social-20261029/skipped-test-validation.json) pins the repairs and distinguishes executed contexts; the final fixture manifest is `d0082001e74f6018c846b6921b173ae2f8b36bc3a33433ee4fa8399af8525981`. Earlier [validation evidence](admin-social-20261029/failure-audit-validation.json) remains retained. Reports and handoff documentation are finalized after execution.

The [workflow and policy notes](../social-publishing/review-ready-workflow-20261029.md) describe the implemented behavior, dated platform rules, review exceptions and model-free approach. New generated posts include caption, topic/location tags, configured account variants, an AuditGava destination and source references. Optional media preserves those fields and automatically saves/validates a new revision. Explicit review and publication controls remain required.

## Validation

Execution uses capped, owned offline Docker: Python 3.12, Node 24, locked frontend dependencies and guarded PostgreSQL 17 at unchanged migration `a756b20a0001`. No hosted workflow allowance, model call, paid service, provider request, production ingestion or live publication is part of the evidence.

| Check | Result |
|---|---|
| Entire merged frontend | 207 suites, 2,792 passed, one existing skip; TypeScript, lint and production build pass |
| Public county pending-bills API | 32 passed |
| Actual source/public HTTP and preparation regression selection | 51 passed: current county/national writers, exact public views, same-date corrections, actual prepare HTTP200/same-key replay/stale409, hashtags and legacy replay |
| Backend PR branch selection | 88 passed; its own base stack remains intact |
| Full merged social suite, latest native setup | **4,484 passed, zero failures/errors; 705 guarded skips covered separately; 84 passing subtests** |
| Formerly skipped fixture matrix | All **708** original IDs execute and pass; zero skipped/missing/failing |
| Combined social-suite coverage | **5,189 unique cases** covered; no broad skipped identity left unexecuted |
| Original 60 failures + 33 errors | All 93 execute exactly once and pass in the full suite; zero skipped or missing |
| Independent audit of the test repairs | 137 affected unit cases, four identity controls, 18 real-PG cases; cross-review 89 + ten cases; three additional boundary attacks; all pass |
| Independent Spec | 159 distinct normal cases (109 independent, 50 repository) plus seven optimized repeats; all original and newly discovered REDs close |
| Independent Standards | 45 backend and 29 UI cases, no skips; actual qualified county correction and both actor-cache cases pass |
| Browser review | Chrome desktop and 390px mobile, light/dark, contextual account tags, optional image save/new revision, exact landing figures and source citations; mobile document width equals viewport width |

The latest broad native run took 487.34 seconds (494.809 seconds including orchestration); its detailed fixture matrix is documented in the skip audit. The preceding [failure audit](admin-social-20261029/failure-audit.md) and [93-case ledger](admin-social-20261029/failure-audit.json) supersede baseline parity as acceptance for the original failures/errors, all of which pass again. The historical [parity receipt](admin-social-20261029/review-ready-baseline-parity.json) is retained: matching main established no introduced failure identities, but did not establish cause or safety. The original launcher itself was defective under multiprocessing spawn. Corrected runs use native `python -m pytest`, unchanged Python distributions, verified read-only tools and private Git inventory. No production code or source guard was changed to obtain a pass.

Separately named historical database/role fixtures are now provisioned and executed, preserving their guards and pinned DDL contracts. Current-runtime tests explicitly request real required descendants or genuine qualified current-source fixtures. No original failure/error or skipped case is excluded, and no new skip/xfail or source bypass closes a result. The synthetic SQLite port remains confined to named unit setups; actual current-PG source workflows use genuine saved witnesses and reject absence/mutation. The readiness fixture's uncertain-commit/ownership cleanup repair is also independently exercised before final acceptance.

The full 46-county changed cohort with installed current authority previously passed in 99.234 seconds, creating 46 pending-review drafts and zero publications; the corresponding cohort cases also pass in the latest full run. Existing frontend/API results above remain applicable because product bytes are unchanged by the failure audit.

The independent reports are [Spec](admin-social-20261029/review-ready-spec-review.md) and [Standards](admin-social-20261029/review-ready-standards-review.md). They include execution scope and limits. A retained comparison replays 41 accepted prior text/metadata/link/fingerprint/policy-scope records exactly. New template/policy/profile hashes bind the package to its saved revision; a legacy external destination remains readable but cannot regain dispatch permission.

All generated supported source families open AuditGava first. Public source pages preserve exact entity, period, figures, reporting qualifications and original citations. Unchanged qualified reacquisition preserves the URL; a genuine same-date correction makes the old view unavailable and the new view valid. No private social post/event/account data enters public responses.

## Holds and operational observations

This change adds no migration and changes no workflow, deployment descriptor or activation flag. All four PRs remain drafts. CI/CD Pipeline and Build and Deploy (Docker Hub) were verified `disabled_manually`. Preview/hosted-run holds remain; no new hosted run or deployment was requested. Existing unrelated ingestion schedules and their separately admitted source SHA are untouched.

Fresh read-only verification is recorded in [production status](admin-social-20261029/production-status.json). Both live application deployments remain at accepted SHA `7797ecb4266169c438ecd2c82e6d817d6577ff19`. Render backend artifact `dep-dbhm6regekts73ble1b0` is healthy/ready (HTTP200), with auto-deploy disabled. At 01:26 UTC on 30 October, a read-only database transaction confirms all four global controls false, both accounts publishing disabled, no targets and unchanged migration `a756b20a0001`. A positive-control `/proc` inventory identifies Gunicorn and no social worker/supervisor. The stopped heartbeat is stale, as expected while workers are off.

The authenticated production status page works after a fresh reload; the earlier unavailable response is no longer reproduced, with no speculative cause assigned. All four current authority/snapshot views exist and grant SELECT to the app login; live FFmpeg/ffprobe execute successfully. These observations verify the current held production state, not provider acceptance, upload readiness or the publishability of a historical revision. No production setting or draft changed. Reconfirm runtime holds and status at any separately approved rollout; missing/error status keeps rollout held.

The fresh [platform status check](admin-social-20261029/platform-status.json) confirms stored Facebook/Instagram identities only, both paused with adapters unavailable. Threads is supported in code but not connected/configured here; X has no admitted access/budget and TikTok product access is unavailable. New connection callbacks remain held. All five loopback accounts are illustrative samples. No provider connection or activation changed in this release preparation.

Keep global and per-account publishing and automatic approval/scheduling/publishing false. Keep `SOCIAL_WORKER_SUPERVISOR_ENABLED`, `SOCIAL_NATIVE_ENABLED`, `SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED`, `SOCIAL_POLICY_AUTOMATION_ENABLED`, `SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED` and `SOCIAL_MEDIA_ENABLED` false or their documented absent/default-off state. Do not start manual social/studio/media/retirement worker commands, register provider transports, admit API budgets, run a backfill, acquire sources or change the ingestion write-approved SHA as a deployment side effect.

The inert build API/Supabase values are fixtures, not production image configuration. Successful local tests/build do not certify resolved production environment parity, provider acceptance, public social visibility, trending hashtags or reach. The policy uses official references with explicit review/access status and a review deadline; it does not scrape trends or automatically claim performance optimization.

## Deployment and rollback handoff

After owner review, record the complete merged SHA, immutable backend/frontend artifact identifiers, resolved safe configuration and fresh health. The confirmed current frontend is [the deployment at accepted main](https://audit-h2pibl3oq-rodgers31s-projects.vercel.app), GitHub deployment `7416253537`; the independently confirmed backend is Render deployment `dep-dbhm6regekts73ble1b0` on service `srv-d6hr3t5m5p6s73bomqu0`. Reconfirm both previous artifacts immediately before rollout rather than inferring one from the other.

Deploy backend and frontend from the same approved complete SHA, preserving every hold. No migration, source ingestion or draft rewrite is needed. Read-only smoke checks: admin queue/review/preview, source selection, exact public report/figure views and original citations, explicit source-unavailable states, old revision readability and policy-version separation. Do not create production source events, prepare existing drafts, approve/schedule posts or start workers as smoke tests.

If read-only checks fail, runtime status is unavailable, a source view substitutes another period/amount, a refusal becomes a pass, or unexpected worker/provider activity appears: stop rollout, retain the holds and restore both prior immutable application artifacts. Keep the database and immutable social history intact; no schema downgrade or destructive cleanup is involved. Recheck publishing/account controls, worker/process inventory and queue/publication counts immediately and within five minutes of a separately authorized rollout.

Production cohort acceptance in [#849](https://github.com/Rodgers31/audit_app/issues/849), actual publisher acquisition latency, provider access/consent/visibility acceptance and eventual activation remain separate work. This packet authorizes none of them.
