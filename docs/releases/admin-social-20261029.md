# Admin and social release review packet

Prepared for owner review. The four PRs remain drafts. Nothing has been merged, deployed, scheduled or published by this preparation; no production worker has been started. Review approval and a separate production rollout gate remain outstanding.

## Candidate and merge order

| PR | Scope | Reviewed stack head before national-link follow-up |
|---|---|---|
| [#850](https://github.com/Rodgers31/audit_app/pull/850) | Private admin shell, readable queue and full review pages | `01f663a28396c7e67e08959dec8b3b59d95c60c2` |
| [#851](https://github.com/Rodgers31/audit_app/pull/851) | Bounded complete-cohort generation | `f92e32c59d34205116f7d93965c72af0043c48c5` |
| [#852](https://github.com/Rodgers31/audit_app/pull/852) | Shared readable copy, qualified destinations and national-link follow-up | `47a1490318ab2897c74ce9704bff68597ac9b677` plus reviewed follow-up |
| [#853](https://github.com/Rodgers31/audit_app/pull/853) | Admin task flows, source selection, saved previews and dated county readers | `34bb250e9a7157623116e3c86ac035fd2c1816bb` |

The actual integration checkout merges both stacks onto accepted main `7797ecb4266169c438ecd2c82e6d817d6577ff19`; the merges are clean. This validates a combined tree, rather than substituting backend files into a separate UI run. Suggested topological merge order after review: #851 → #852 and #850 → #853. Deploy only the resulting complete tree, with both backend and frontend changes present. Preserve the tested product bytes when updating PR bases; revalidate any conflict resolution or additional code change.

Final frozen candidate: `combined-release-candidate-4`, 5,730 tracked files, manifest SHA256 `7a90b35eef28e40825392676344a4ffd2f6ed70f7eece1ef51419ae82cbad8e1`. Candidate 4 changes only the new national-report test's owned witness fixture from candidate 3; all product/frontend bytes match candidate 3. Subsequent release documentation does not change that executable candidate.

## Validation

All project execution uses capped, owned offline Docker. Python 3.12, Node 24, locked frontend dependencies and guarded PostgreSQL 17 at unchanged migration `a756b20a0001`. No hosted workflow allowance, paid model, provider request, production ingestion or live publication is part of these receipts.

| Check | Result |
|---|---|
| Entire merged frontend | 204 suites, 2,761 passed, one existing skip; TypeScript, lint and production build pass |
| Public county pending-bills API | 32 passed |
| Final focused source/copy/destination/current-PG/budget selection | 302 passed in normal Python; receipt: `combined-final-focused-green.txt` |
| Full 46 changed counties with installed current authority | Final normal Python: 46/46 drafts awaiting review, zero publications; test wall time 98.55 seconds; optimized check 90.5 seconds. Receipt: `combined-final-cohort-normal.txt` |
| Strict direct helper regressions | Root reproduced six independent failures before repair; final direct-boundary and added regression selection: 29 passed |
| Independent Spec and Standards | Spec: 351 unique passes + 11 optimized repeats. Standards: 86 backend + 40 UI passes; corrected author case separately passes. Reports: [Spec](admin-social-20261029/spec-review.md), [Standards](admin-social-20261029/standards-review.md) |

The final combined normal social run produced **4,287 passes, 727 skips, 60 failures, 33 errors and 70 passing subtests**. Accepted main under the same image/namespace bootstrap produced **3,994 passes, the same 727 skips, 60 failures, the same 33 errors and 70 passing subtests**. All 93 failure/error IDs match exactly, with no additional failure/error case. The final focused run also passes all 302 cases, including the actual national report writer/backfill with the existing restricted current-witness fixture.

The broad suite is **not wholly green**. Its unchanged failures include legacy `SOURCE_REVIEW_REQUIRED` approvals/registry cases, old metrics contracts, worker rehearsal Git/output/legacy-helper prerequisites and media fixture prerequisites missing from the offline Python image. Historical guarded databases are not silently redirected to the current schema; 727 skips are not acceptance claims. The root broad invocation uses a tiny external namespace bootstrap because an installed third-party `tests` package otherwise masks this repository's namespace. The same bootstrap is applied to both candidates. The baseline archive includes the full repository, including worker rehearsal tools. No skip, xfail, source-check bypass or production code change was added to conceal these results. The [baseline parity receipt](admin-social-20261029/backend-baseline-parity.json) includes every matching case ID; full logs remain in the task evidence directory.

## Holds and production observations

The code adds no migration and changes no workflow, deployment descriptor or activation flag. Read-only production UI verification after reload showed publishing paused, no available adapters, no queued destinations, automatic publishing off, media storage disabled and account publishing disabled. The worker heartbeat is stale/unavailable; that is not a positive worker-health or process-inventory attestation. No production controls or records were changed in this preparation.

GitHub CI/CD and Docker deployment workflows remain manually disabled. Preview and hosted-run holds remain. Existing separately admitted ingestion keeps its approved SHA `7797ecb4266169c438ecd2c82e6d817d6577ff19`; repository draft/report hook variables already set true were left untouched. Native financial admission and policy automation are not enabled by this release. Do not update the ingestion write-approved SHA, enable a hook/worker, run a backfill or start delivery as a side effect of UI deployment.

At the separately approved rollout, compare **resolved runtime values** with these held requirements, without printing credentials:

- Global and per-account publishing, automatic approval/scheduling/publishing: false.
- `SOCIAL_WORKER_SUPERVISOR_ENABLED`, `SOCIAL_NATIVE_ENABLED`, `SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED`, `SOCIAL_POLICY_AUTOMATION_ENABLED`, `SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED`, `SOCIAL_MEDIA_ENABLED`: false or their documented absent/default-off state. No manual social/studio/media/retirement worker process or scheduled command is started.
- No provider transport registration or budget admission; no uploads, source acquisition or generation command is part of deployment.
- Frontend public API and Supabase build values match the intended production environment. Offline build values are inert fixtures and are not a production image. A successful offline build does not certify production configuration parity.

## Deployment and rollback handoff

After owner review, capture the final combined merge SHA, immutable backend/frontend artifact identifiers, prior backend artifact identifier, resolved safe configuration and current health before deploying. Do not deploy intermediate stack heads. The currently observed successful production frontend is [the deployment at accepted main](https://audit-h2pibl3oq-rodgers31s-projects.vercel.app), GitHub deployment `7416253537`. Its source SHA is the accepted main above. No production backend artifact identifier has been invented from that frontend receipt.

Deploy backend and frontend from the same approved combined SHA, preserving all holds. No schema migration or data rewrite is needed. Read-only checks immediately after deployment: admin queue/review/preview and source selection; a dated county URL selects the exact county/day or explicitly reports absence; national report links use the exact qualified publisher document and report year; old revisions and their policy scopes retain their recorded versions. Do not create a production source event, approve a post, schedule delivery or run a worker as a smoke test.

If read-only checks fail, publishing becomes enabled unexpectedly, a destination selects a different period, a current-source refusal becomes a pass, or worker/provider activity appears: stop rollout, retain the holds, and restore both prior immutable application artifacts. For the frontend, restore the recorded Vercel deployment above; for the backend, restore the artifact recorded immediately before rollout. Keep the database and immutable social history intact; there is no schema downgrade or destructive draft cleanup. Accepted-code rollback was rehearsed by executing the accepted tree in the same offline environment. Actual platform rollback and production configuration parity must be verified during the separately authorized rollout, before promoting new artifacts.

Check publishing status, account holds, worker/process inventory and queue/publication counts immediately and again within five minutes of an eventual rollout. A missing/error/stale status is a stop condition, not evidence that the system is safely enabled or healthy. Production acceptance of [#849](https://github.com/Rodgers31/audit_app/issues/849), actual publisher acquisition latency and any future activation remain separate work.
