# Admin and social release review packet

Prepared for owner PR review. The complete generated-post workflow is implemented in the existing draft PRs. Nothing is merged, deployed, approved, scheduled or published by this preparation; no production worker, upload service or provider connection is started. Owner review and a separate production rollout gate remain outstanding.

## Scope and merge order

| PR | Scope |
|---|---|
| [#850](https://github.com/Rodgers31/audit_app/pull/850) | Private admin shell, readable queue and full review pages |
| [#851](https://github.com/Rodgers31/audit_app/pull/851) | Bounded complete-cohort generation |
| [#852](https://github.com/Rodgers31/audit_app/pull/852) | Evidence-bound captions, relevant per-account hashtags, exact AuditGava source views, historical replay and publication-link guards |
| [#853](https://github.com/Rodgers31/audit_app/pull/853) | Prepared previews, automatic media format/save/validation, admin session boundaries, public report UI and illustrative local examples |

The integration checkout merges both stacks onto accepted main `7797ecb4266169c438ecd2c82e6d817d6577ff19`. Suggested topological merge order after review: #851 → #852 and #850 → #853. Deploy the resulting complete tree with both backend and frontend present. Intermediate PR heads are not independently deployable product packages. Preserve the tested bytes when updating PR bases and revalidate any conflict resolution or additional code change.

Reviewed product candidate: `review-ready-candidate-4`, 5,754 files. File-entry manifest SHA256 `2735528d6b36a6c35bc060868abf9b2cb6982e1f077356d6f1426f666a030258`; complete manifest-file SHA256 `6068da4c65d9309191bdffb4ef30f9f6f67bdd01e0c24eee59a04b3b73dbcbe1`. The subsequent failure audit changes nine test files and release documentation; all backend/frontend product bytes remain identical. Its native full-run input manifest SHA256 is `608b12555ada62080f413c4eca88900adf895b0b835af99dbfe8c984edce91c4`. Test repairs and runtime provenance are pinned in [the latest validation receipt](admin-social-20261029/failure-audit-validation.json). Reports and handoff documentation are finalized after execution.

The [workflow and policy notes](../social-publishing/review-ready-workflow-20261029.md) describe the implemented behavior, dated platform rules, review exceptions and model-free approach. New generated posts include caption, topic/location tags, configured account variants, an AuditGava destination and source references. Optional media preserves those fields and automatically saves/validates a new revision. Explicit review and publication controls remain required.

## Validation

Execution uses capped, owned offline Docker: Python 3.12, Node 24, locked frontend dependencies and guarded PostgreSQL 17 at unchanged migration `a756b20a0001`. No hosted workflow allowance, model call, paid service, provider request, production ingestion or live publication is part of the evidence.

| Check | Result |
|---|---|
| Entire merged frontend | 207 suites, 2,792 passed, one existing skip; TypeScript, lint and production build pass |
| Public county pending-bills API | 32 passed |
| Actual source/public HTTP and preparation regression selection | 51 passed: current county/national writers, exact public views, same-date corrections, actual prepare HTTP200/same-key replay/stale409, hashtags and legacy replay |
| Backend PR branch selection | 88 passed; its own base stack remains intact |
| Full merged social suite, corrected native setup | **4,473 passed, zero failures/errors; 708 guarded historical-fixture skips; 84 passing subtests** |
| Original 60 failures + 33 errors | All 93 execute exactly once and pass in the full suite; zero skipped or missing |
| Independent audit of the test repairs | 137 affected unit cases, four identity controls, 18 real-PG cases; cross-review 89 + ten cases; three additional boundary attacks; all pass |
| Independent Spec | 159 distinct normal cases (109 independent, 50 repository) plus seven optimized repeats; all original and newly discovered REDs close |
| Independent Standards | 45 backend and 29 UI cases, no skips; actual qualified county correction and both actor-cache cases pass |
| Browser review | Chrome desktop and 390px mobile, light/dark, contextual account tags, optional image save/new revision, exact landing figures and source citations; mobile document width equals viewport width |

The full native run took 472.26 seconds (479.613 seconds including orchestration). [The failure audit](admin-social-20261029/failure-audit.md) and [93-case ledger](admin-social-20261029/failure-audit.json) supersede the earlier baseline-parity result as release evidence. That historical [parity receipt](admin-social-20261029/review-ready-baseline-parity.json) is retained: matching main established no introduced failure identities, but did not establish their cause or safety. The original launcher itself was defective under multiprocessing spawn. The corrected run uses native `python -m pytest`, the exact previous 97 Python distribution versions, verified read-only FFmpeg/process tools, an actual private Git index and two named isolated PostgreSQL fixtures. No production code or source guard was changed to obtain a pass.

The 708 skips require separately named historical database/role fixtures. Their exact reasons are preserved in the ledger; they are **unverified coverage**, not passing checks. No original failure/error was skipped, no new skip/xfail was added, and those historical fixtures were not redirected to the current schema. The explicit synthetic SQLite authority port only restores later workflow assertions inside named unit setups; the real verifier rejects its marker. Current-PG approval/hold and hostile source-mutation controls execute without that port. Native package resolution and each test repair were independently cross-checked.

The full 46-county changed cohort with installed current authority previously passed in 99.234 seconds, creating 46 pending-review drafts and zero publications; the corresponding cohort cases also pass in the latest full run. Existing frontend/API results above remain applicable because product bytes are unchanged by the failure audit.

The independent reports are [Spec](admin-social-20261029/review-ready-spec-review.md) and [Standards](admin-social-20261029/review-ready-standards-review.md). They include execution scope and limits. A retained comparison replays 41 accepted prior text/metadata/link/fingerprint/policy-scope records exactly. New template/policy/profile hashes bind the package to its saved revision; a legacy external destination remains readable but cannot regain dispatch permission.

All generated supported source families open AuditGava first. Public source pages preserve exact entity, period, figures, reporting qualifications and original citations. Unchanged qualified reacquisition preserves the URL; a genuine same-date correction makes the old view unavailable and the new view valid. No private social post/event/account data enters public responses.

## Holds and operational observations

This change adds no migration and changes no workflow, deployment descriptor or activation flag. All four PRs remain drafts. CI/CD Pipeline and Build and Deploy (Docker Hub) were verified `disabled_manually`. Preview/hosted-run holds remain; no new hosted run or deployment was requested. Existing unrelated ingestion schedules and their separately admitted source SHA are untouched.

Fresh read-only verification is recorded in [production status](admin-social-20261029/production-status.json). Both live application deployments remain at accepted SHA `7797ecb4266169c438ecd2c82e6d817d6577ff19`. Render backend artifact `dep-dbhm6regekts73ble1b0` is healthy/ready (HTTP200), with auto-deploy disabled. At 01:26 UTC on 30 October, a read-only database transaction confirms all four global controls false, both accounts publishing disabled, no targets and unchanged migration `a756b20a0001`. A positive-control `/proc` inventory identifies Gunicorn and no social worker/supervisor. The stopped heartbeat is stale, as expected while workers are off.

The authenticated production status page works after a fresh reload; the earlier unavailable response is no longer reproduced, with no speculative cause assigned. All four current authority/snapshot views exist and grant SELECT to the app login; live FFmpeg/ffprobe execute successfully. These observations verify the current held production state, not provider acceptance, upload readiness or the publishability of a historical revision. No production setting or draft changed. Reconfirm runtime holds and status at any separately approved rollout; missing/error status keeps rollout held.

Keep global and per-account publishing and automatic approval/scheduling/publishing false. Keep `SOCIAL_WORKER_SUPERVISOR_ENABLED`, `SOCIAL_NATIVE_ENABLED`, `SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED`, `SOCIAL_POLICY_AUTOMATION_ENABLED`, `SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED` and `SOCIAL_MEDIA_ENABLED` false or their documented absent/default-off state. Do not start manual social/studio/media/retirement worker commands, register provider transports, admit API budgets, run a backfill, acquire sources or change the ingestion write-approved SHA as a deployment side effect.

The inert build API/Supabase values are fixtures, not production image configuration. Successful local tests/build do not certify resolved production environment parity, provider acceptance, public social visibility, trending hashtags or reach. The policy uses official references with explicit review/access status and a review deadline; it does not scrape trends or automatically claim performance optimization.

## Deployment and rollback handoff

After owner review, record the complete merged SHA, immutable backend/frontend artifact identifiers, resolved safe configuration and fresh health. The confirmed current frontend is [the deployment at accepted main](https://audit-h2pibl3oq-rodgers31s-projects.vercel.app), GitHub deployment `7416253537`; the independently confirmed backend is Render deployment `dep-dbhm6regekts73ble1b0` on service `srv-d6hr3t5m5p6s73bomqu0`. Reconfirm both previous artifacts immediately before rollout rather than inferring one from the other.

Deploy backend and frontend from the same approved complete SHA, preserving every hold. No migration, source ingestion or draft rewrite is needed. Read-only smoke checks: admin queue/review/preview, source selection, exact public report/figure views and original citations, explicit source-unavailable states, old revision readability and policy-version separation. Do not create production source events, prepare existing drafts, approve/schedule posts or start workers as smoke tests.

If read-only checks fail, runtime status is unavailable, a source view substitutes another period/amount, a refusal becomes a pass, or unexpected worker/provider activity appears: stop rollout, retain the holds and restore both prior immutable application artifacts. Keep the database and immutable social history intact; no schema downgrade or destructive cleanup is involved. Recheck publishing/account controls, worker/process inventory and queue/publication counts immediately and within five minutes of a separately authorized rollout.

Production cohort acceptance in [#849](https://github.com/Rodgers31/audit_app/issues/849), actual publisher acquisition latency, provider access/consent/visibility acceptance and eventual activation remain separate work. This packet authorizes none of them.
