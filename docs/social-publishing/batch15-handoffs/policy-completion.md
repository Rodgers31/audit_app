# B15 selective policy completion

Worktree: `/Users/roger/.codex/worktrees/b15-policy-completion/audit_app`.
Branch: `codex/b15-policy-completion`.
Exact dependency/base: PR704 head `2f3b36e2749a48dbe7d93f001081ddc756a61412`.
The new draft PR and final commit are recorded externally in
`FULL_PLAN_COMPLETION_B15/lane/policy-completion-status.md` and this lane's
`policy-completion-evidence/delivery.json`, avoiding a circular commit hash.
Primary dirty, peer and coordinator checkouts were not edited/installed/reset/stashed.
PR707 is not imported. Root owns combined integration and migration ordering.

## Implemented

- Independent immutable human operating-evidence acceptance, authorized policy
  snapshots and exact post/revision/hash decisions. A shadow rule is never
  sufficient authority. Evidence acceptance requires explicit human attestations,
  report URL/hash and matching human-authorized/published shadow outcomes.
  No operating evidence or accepted policy is seeded or shipped.
- Existing source-event consumer invokes dormant policy authorization/scheduling;
  no new service or independent delivery engine. Expected refusals preserve the
  pending human draft with a durable reason; unexpected storage/runtime failures
  propagate. Private admin commands use existing atomic audit/idempotency receipts.
- Deterministic single-actual-fact dataset scope freezes source/entity/metric/period/
  comparison/template/link semantics. Exact-decimal materiality threshold is frozen
  in the snapshot, with same-semantics prior event required. Tiny, bootstrap,
  edited/customized, sensitive/correction/allegation/contested/reputational classes
  retain human review. Current event/cursor, fingerprint, exact hash, provenance,
  verified freshness, materiality and capabilities are checked again at admission.
- Immutable cross-rule/account cadence reservations and shared queue scheduling:
  max1–3/account/rolling24h, min60–1440min, both future and past windows, bounded
  history, validity deadlines and actual prior public-permit/publication spacing.
  Cancellation/restart cannot erase reservations; missed/conflicting slots refuse.
- Fresh same-transaction worker mutation checks for environment ceiling, current
  policy/selection/snapshot/evidence, expiry, source, controls, account, permissions,
  capability, budget and frozen payload. Rule/source writers share the existing
  global dispatch ordering lock. Read-only recovery remains independent.
- Default-off environment ceiling `SOCIAL_POLICY_AUTOMATION_ENABLED` and separate
  approval/schedule/publish controls. X remains refused without inventing paid
  reservations; TikTok unattended publication requires explicitly accepted exact
  product and supported unattended capability. Human queue/resume/retry commands
  cannot reuse policy authority. Existing UI handles nullable human identity,
  labels policy authorization and suppresses human schedule reuse.

Detailed contracts/operator ports and limits: `backend/social/automation/README.md`.
There is no browser activation toggle. Pauses/refusals do not manufacture renewed
policy authority; invalid/blocked work needs a newly reviewed revision when the
original authority no longer qualifies. Global pause retains existing queue behavior.

## Shared edits / migration / integration

New namespace: `backend/social/automation/**`.
Shared: `social/__init__.py`, `api.py`, `models.py`, `service.py`,
`generation/service.py` and README, `worker/repository.py`, `worker/role_contract.py`.
Frontend: `lib/api/social.ts`, three existing social components plus Automation
copy and their focused tests. No dependency/lock/main.py or provider adapter edits.

Additive migration `a706b15a0001` follows `a704b15a0001` only. It adds private/RLS
history/selection tables, composite publication authority FK and immutable decision
link guard, preserves original guard bodies, and makes independent automation
controls structurally expressible with false defaults/hierarchy constraints.
No new policy/control seed or role/grant installation. Downgrade refuses existing
policy publication history or enabled automatic controls.

Root must serialize the sibling chain and independently replay its exact merged
source. Additional worker read/trigger contract is coded and inspected, not granted
or production-qualified. The reviewed ETL caller/qualified source adapter and
publisher evidence remain separate dependencies; no peer source is silently included.

## Tested / source-bound evidence

Evidence root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/policy-completion-evidence`.

- `final-v3/receipt.json`: **103 backend cases passed normally, same103 with -O,
  zero skips;465 frontend cases passed**. Exact command/runtime/source-before/
  source-after, per-test identities, JUnit and raw log hashes retained. Earlier
  final-v1/v2 successes are explicitly historical/superseded by subsequent changes;
  neither is relabeled as final acceptance. Review inventories overlap these counts.
- Backend command: `PYTHONPATH=backend:backend/tests/social PYTHON_DOTENV_DISABLED=1
  B15_POLICY_TEST_DB_URL=<assigned owned fixture> .venv/bin/python [-O] -m pytest
  --confcutdir=backend/tests/social backend/tests/social/test_automation.py
  backend/tests/social/test_automation_postgres.py backend/tests/social/test_generation.py
  backend/tests/social/test_generation_api.py backend/tests/social/test_domain_commands.py
  backend/tests/social/test_api_admin.py backend/tests/social/test_worker_policy.py -q -rs`.
- PostgreSQL17 full empty-chain upgrade to a706 succeeded. Tests force concurrent
  authorizations (one exact authority), real rule-writer ordering, immutable history
  and unbacked-null authority refusal. Independent Standards also executed actual
  QueueRepository._gate/fresh-control proof in the held transaction and read-only
  role-trigger/schema inspection. No roles/grants installed. Official `alembic check`
  refuses two existing raw-SQL ownership tables absent from ORM metadata; log retained.
  Explicit comparison has no other/new-policy differences. This is not a clean full
  Alembic-check claim. The first final-v2 migration launch raced fixture readiness;
  its failure/partial red harness logs are retained, then actual full-chain replay ran.
- `observed-red-v4/receipt.json`: eight expected assertion failures under normal/-O
  for pre-fix NULL-version authority, cadence displacement, rule-ordering and missing
  materiality guards, with exact mutated/original/test/log hashes and restored bytes.
  Initial missing-policy-entry failure was observed on704. Manual Publish Now audit
  refactor regression also reproduced before repair; original audit action restored.
- Independent executable Spec reports `spec/REPORT-v2/v3/v4.md`: wrong exact authority,
  fresh-worker controls/capabilities/expiry, source-hook rollback, X/TikTok, materiality
  equality/granularity/reversal/large-value/missing-history and2000 cadence oracle cases.
  Standards reports `standards/report-v2/v3/v4.md`: both confirmed initial defects
  red→green, PG ordering/gate/trigger evidence, malformed state, persistence rollback,
  hostile/large Decimal bounds and restored manual audit semantics. No unresolved
  confirmed finding in those executed scopes. Receipts preserve exact source identities.
- `chrome-v1/receipt.json`: Chrome155.0.8059.80,1280/390px, policy label and disabled
  manual Publish/Schedule controls, no horizontal overflow/external requests/errors.
  Scope is static DOM rendered by the actual composer in Jest; not a hydrated
  browser command workflow or provider qualification. Screenshots retained.
- Frontend command: `node_modules/.bin/jest __tests__/admin/social
  __tests__/social-generation.test.tsx --runInBand --silent`.
  Full typecheck remains blocked solely by unchanged `StyledGeography.tsx:36`
  CSSProperties mismatch in reused cached dependencies. `typecheck-baseline.json`
  binds identical704/current file bytes; no clean lockfile install is claimed.

## Deployed / live accepted / external blocks

DEPLOYED: no migration, code release, permissions or grants applied here.
LIVE ACCEPTED: no live policy, shadow pilot acceptance, provider post/upload or
unattended-product acceptance created. Synthetic test outcomes are visibly local
fixtures and are never supplied to a real environment as operating acceptance.
Global/account publishing and uploads were not changed; all new controls default off.
No credentials, cloud/provider configuration, hosted Actions/previews, paid reviews,
new paid resources, merge, override or deployment. Actions readback was disabled.

Remaining original acceptance: genuine shadow-versus-human operating outcomes and
explicit human acceptance; production source/publisher qualification and reviewed
ETL integration; separately qualified worker privileges, provider/product/cost,
capacity/egress/retention/custody/recovery acceptance; authorized narrow live rollout.
Source/format/category expansion remains human-only until separately evidenced.
Parent #476 remains open. Local coding/tests do not establish full-plan/live completion.

Owned PostgreSQL55406 and Chrome33509 resources are cleaned up with exact container,
mount/volume and reusable-port readback recorded externally. The worktree and owned
cached runtime clones remain for review. No peer process/resource was stopped.
