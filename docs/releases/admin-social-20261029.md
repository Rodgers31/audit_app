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

Final executable candidate: `review-ready-candidate-4`, 5,754 files. File-entry manifest SHA256 `2735528d6b36a6c35bc060868abf9b2cb6982e1f077356d6f1426f666a030258`; complete manifest-file SHA256 `6068da4c65d9309191bdffb4ef30f9f6f67bdd01e0c24eee59a04b3b73dbcbe1`. Reports, parity records and this handoff documentation are added after freezing; executable product/test/fixture bytes are checked against that manifest again before pushing.

The [workflow and policy notes](../social-publishing/review-ready-workflow-20261029.md) describe the implemented behavior, dated platform rules, review exceptions and model-free approach. New generated posts include caption, topic/location tags, configured account variants, an AuditGava destination and source references. Optional media preserves those fields and automatically saves/validates a new revision. Explicit review and publication controls remain required.

## Validation

Execution uses capped, owned offline Docker: Python 3.12, Node 24, locked frontend dependencies and guarded PostgreSQL 17 at unchanged migration `a756b20a0001`. No hosted workflow allowance, model call, paid service, provider request, production ingestion or live publication is part of the evidence.

| Check | Result |
|---|---|
| Entire merged frontend | 207 suites, 2,792 passed, one existing skip; TypeScript, lint and production build pass |
| Public county pending-bills API | 32 passed |
| Actual source/public HTTP and preparation regression selection | 51 passed: current county/national writers, exact public views, same-date corrections, actual prepare HTTP200/same-key replay/stale409, hashtags and legacy replay |
| Backend PR branch selection | 88 passed; its own base stack remains intact |
| Full merged social suite | 4,343 passed; the same 60 failures, 33 errors and 727 skips as accepted main; 70 passing subtests |
| Independent Spec | 159 distinct normal cases (109 independent, 50 repository) plus seven optimized repeats; all original and newly discovered REDs close |
| Independent Standards | 45 backend and 29 UI cases, no skips; actual qualified county correction and both actor-cache cases pass |
| Browser review | Chrome desktop and 390px mobile, light/dark, contextual account tags, optional image save/new revision, exact landing figures and source citations; mobile document width equals viewport width |

Final normal full social failure/error identities are compared with accepted main under the same image and namespace bootstrap. See [the parity receipt](admin-social-20261029/review-ready-baseline-parity.json). All 93 failure/error identities match exactly; there are no added or resolved baseline failure/error cases. The final run took 486.15 seconds. The full 46-county changed cohort with installed current authority passed in 99.234 seconds, created 46 pending-review drafts and zero publications.

The broad suite is **not wholly green**. Its baseline failures include legacy `SOURCE_REVIEW_REQUIRED` approval/registry fixtures, metrics contracts, worker rehearsal Git/output prerequisites and media-tool prerequisites absent from the offline Python image. Historical guarded databases are not redirected to the current schema; skips are not acceptance claims. The external test bootstrap resolves an installed third-party `tests` package masking the repository's namespace, identically for baseline and candidates. No skip/xfail or product-source bypass was introduced to hide those results. Positive low-level validation fixtures now include the newly required AuditGava destination; unrelated historical revision bytes stay unchanged.

The independent reports are [Spec](admin-social-20261029/review-ready-spec-review.md) and [Standards](admin-social-20261029/review-ready-standards-review.md). They include execution scope and limits. A retained comparison replays 41 accepted prior text/metadata/link/fingerprint/policy-scope records exactly. New template/policy/profile hashes bind the package to its saved revision; a legacy external destination remains readable but cannot regain dispatch permission.

All generated supported source families open AuditGava first. Public source pages preserve exact entity, period, figures, reporting qualifications and original citations. Unchanged qualified reacquisition preserves the URL; a genuine same-date correction makes the old view unavailable and the new view valid. No private social post/event/account data enters public responses.

## Holds and operational observations

This change adds no migration and changes no workflow, deployment descriptor or activation flag. All four PRs remain drafts. CI/CD Pipeline and Build and Deploy (Docker Hub) were verified `disabled_manually`. Preview/hosted-run holds remain; no new hosted run or deployment was requested. Existing unrelated ingestion schedules and their separately admitted source SHA are untouched.

A read-only production page initially displayed publishing paused, no available adapters or queued destinations, automatic publishing off, media storage disabled and per-account publishing disabled. A later status refresh returned unavailable/invalid-request, so that refresh is **not** positive operational-health or live process-inventory evidence. No production setting or draft was changed during this implementation. Worker status was stale/unavailable; no claim of a healthy or inspected production worker process is made. Reconfirm resolved runtime holds before any eventual rollout; missing/error status keeps rollout held.

Keep global and per-account publishing and automatic approval/scheduling/publishing false. Keep `SOCIAL_WORKER_SUPERVISOR_ENABLED`, `SOCIAL_NATIVE_ENABLED`, `SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED`, `SOCIAL_POLICY_AUTOMATION_ENABLED`, `SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED` and `SOCIAL_MEDIA_ENABLED` false or their documented absent/default-off state. Do not start manual social/studio/media/retirement worker commands, register provider transports, admit API budgets, run a backfill, acquire sources or change the ingestion write-approved SHA as a deployment side effect.

The inert build API/Supabase values are fixtures, not production image configuration. Successful local tests/build do not certify resolved production environment parity, provider acceptance, public social visibility, trending hashtags or reach. The policy uses official references with explicit review/access status and a review deadline; it does not scrape trends or automatically claim performance optimization.

## Deployment and rollback handoff

After owner review, record the complete merged SHA, immutable backend/frontend artifact identifiers, previous backend artifact, resolved safe configuration and current health. The previously observed successful production frontend is [the deployment at accepted main](https://audit-h2pibl3oq-rodgers31s-projects.vercel.app), GitHub deployment `7416253537`. A backend artifact identifier must be captured before rollout; it is not inferred from the frontend record.

Deploy backend and frontend from the same approved complete SHA, preserving every hold. No migration, source ingestion or draft rewrite is needed. Read-only smoke checks: admin queue/review/preview, source selection, exact public report/figure views and original citations, explicit source-unavailable states, old revision readability and policy-version separation. Do not create production source events, prepare existing drafts, approve/schedule posts or start workers as smoke tests.

If read-only checks fail, runtime status is unavailable, a source view substitutes another period/amount, a refusal becomes a pass, or unexpected worker/provider activity appears: stop rollout, retain the holds and restore both prior immutable application artifacts. Keep the database and immutable social history intact; no schema downgrade or destructive cleanup is involved. Recheck publishing/account controls, worker/process inventory and queue/publication counts immediately and within five minutes of a separately authorized rollout.

Production cohort acceptance in [#849](https://github.com/Rodgers31/audit_app/issues/849), actual publisher acquisition latency, provider access/consent/visibility acceptance and eventual activation remain separate work. This packet authorizes none of them.
