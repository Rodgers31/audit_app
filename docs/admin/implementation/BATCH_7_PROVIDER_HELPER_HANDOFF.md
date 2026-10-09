# Batch 7 legacy provider-helper handoff

Issue [#567](https://github.com/Rodgers31/audit_app/issues/567), parent [#545](https://github.com/Rodgers31/audit_app/issues/545). This is bounded legacy compatibility maintenance; active Users acceptance remains the baseline.

## Sources and ownership

- Owned managed worktree: `/Users/roger/.codex/worktrees/batch7-provider-helper/audit_app`.
- Branch: `codex/batch7-provider-helper`.
- Exact baseline: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`, tree `712b43650b1203ffd84583b67d07d30775669b1e`.
- Reviewed implementation commit: `856176512b470e37d6df55c7c8c545820db69b15`.
- Final helper blob: `674a7c7c8ca3ca4c27c9cefce7e50bc6659d9a7b`; SHA256 `fdb2ba0c7e95da9bcdf945d244f6cff67d9899d8ea6371c4fc5c40891c04d003`.
- Frozen scope and examples were read from the Batch 7 session directory on 2026-10-09; their identities are in the manifest. They remain read-only.
- Changed production file: `backend/supabase_admin.py`. Added only `test_batch7_supabase_helpers*.py`, this handoff and lane evidence. Active provider/router, shared auth/core, models, migrations and manifests remain byte-identical to the pinned base.

Attached artifacts were inspected first (none); the managed worktree was created from the exact base and registered before any application import or mutation. Its clean baseline and tree were verified before the lane branch was created. No applicable AGENTS.md/CLAUDE.md was found in the checkout or ancestors; CONTEXT.md was read. No repository policy/agent setup was added. Applied skills: git-workflow, implement/TDD, regression-fixture-on-fix, verify-boundary-shapes, no-silent-fallbacks, claims-need-receipts, adversarial-verify, code-review, git-commit and git-pr.

## Result

Retain the public compatibility helper after the complete [caller inventory](batch7-provider-helper-evidence/CALLERS.md). Authentication still imports the shared module for profile reads; active Users routes use the independently verified replacement. No product caller of the legacy role mutation or count was found; repository absence alone does not justify removing a public compatibility function.

The old role helper supplied headers twice and raised TypeError before transport. `_raw_request` now collapses per-call header case variants once, then applies required service-role headers. Prefer appears once. HTTPX `auth=` is rejected with a static 400 before transport because HTTPX otherwise replaces Authorization after header construction; no inventoried caller uses it. Non-2xx replies cannot certify a role update.

`update_profile_roles` returns only a single representation whose id and roles exactly match the request and which contains no canonical failure verdict. Empty-list missing-profile replies retain 404. Malformed JSON, absent/malformed/mismatched/multiple representations and explicit failure markers produce a static 502 without returning their payload. Existing upstream HTTP error statuses/bodies and transport exceptions continue to propagate; raw legacy error diagnostics are separately tracked below. Count implementation is untouched and its real memory transport returns the supplied count of 3 before/after.

The public function/error/import identities are retained. No role vocabulary or arbitrary profile-column allowlist was added. A failed acknowledgment means the mutation is unconfirmed; transport failure may follow upstream mutation, so these local controls do not authorize automatic mutation retry.

## Executed verification

The [red/green receipt](batch7-provider-helper-evidence/RED_GREEN.md) includes actual commands and outcomes:

- Pinned initial role/count: **1 failed / 2 passed**, duplicate-keyword TypeError with **zero role requests**, passing filtered/unfiltered count controls.
- Pinned active Users controls: **164 passed**.
- Response-boundary red: **22 failed / 12 passed** before acknowledgment validation; canonical failure-verdict red: **8 failed** before its guard.
- HTTPX auth-override red: **1 failed** before its guard; green: **1 passed** with zero transport requests.
- Final: **232 passed** (68 helper/fresh-import cases plus 164 retained Users route/provider/auth/audit controls). Two existing SQLAlchemy deprecation warnings.
- Default pytest collection of new tests: **68 passed** without a special marker/confcutdir exclusion. Product lifespan was not entered.
- Scoped critical flake8 7.3.0: output **0**, exit 0. Diff whitespace and bounded staged credential-pattern/manual fixture checks pass.

Independent [Standards](batch7-provider-helper-evidence/STANDARDS.md): **0 documented violations / 0 actionable heuristic findings**. Independent [Spec](batch7-provider-helper-evidence/SPEC.md): **0 missing/partial, 0 scope, 0 implementation findings**; independently replayed **232 passed** with socket.connect blocked. Both review axes ran concurrently on the pinned diff and exact implementation SHA. Independent [adversarial review](batch7-provider-helper-evidence/ADVERSARIAL.md): **147 checks per actual import mode**, 294 total, covering malformed acknowledgments, upstream/transport errors, 51 header configurations, supported role arrays, count, signed auth and active provider. The initial auth override finding was fixed with retained author red/green and independent final recheck. No remaining confirmed acceptance finding.

## Runtime, evidence and cleanup

Read-only product runtime: `/Users/roger/Documents/projects/audit_app/venv/bin/python`, Python 3.13.9. No frontend runtime reuse/install is needed. The shared venv lacked flake8; a separate owned external lint venv contained flake8 7.3.0 / pyflakes 3.4.0 / pycodestyle 2.14.0 / mccabe 0.7.0. It was removed after final lint, with version receipt retained. No shared runtime or primary-checkout file was edited or installed into.

Product tests use clean environments, absolute owned backend PYTHONPATH, no dotenv, synthetic JWT/provider identities, `.invalid` URLs and actual in-memory HTTP/ASGI transports. SQLite paths are owned import-smoke resources, not PostgreSQL semantic evidence. No server, bound port, container, PostgreSQL service, real user/email/provider/storage write or production startup/deployment/migration was needed. Test subprocesses ended; reviewer temporary resources were removed. Managed worktree and external evidence remain for coordinator review. Small automatically retained pytest import-smoke files follow pytest retention; no shared temporary tree was deleted.

Bulky logs, executed probe scripts, complete all-state inventories and source snapshots remain outside git under `/Users/roger/.codex/visualizations/2026/10/09/01a11f2c-ff0e-7d61-9c3d-752e78d1ebe4/batch7-provider-helper-evidence/`. [Manifest](batch7-provider-helper-evidence/MANIFEST.json) gives SHA256 identities and ownership/cleanup. Compact review/red-green/caller receipts are committed here.

## Issue accounting and limits

- #567 implemented locally; remains open for coordinator acceptance/closure after integration. Parent #545 remains open.
- [#569](https://github.com/Rodgers31/audit_app/issues/569): existing broad critical-lint gate flags `scripts/r2_producer_acceptance.py:440` captured closure; exact pinned file produces the same F821. A minimal closure/deletion runtime control passes. This is a tooling-gate failure, not a demonstrated runtime PDF defect; the producer was not changed or executed.
- [#570](https://github.com/Rodgers31/audit_app/issues/570): residual legacy profile-read query/identity/payload contracts. Independent and author memory replays reproduce concatenated caller query filters, a mismatched returned identity and wrong-container bulk fallback. Shared auth already rejects mismatched identities (#550); active Users uses its accepted replacement (#551).
- [#571](https://github.com/Rodgers31/audit_app/issues/571): shared legacy exception text/body still contains raw provider diagnostics. Synthetic-marker replay establishes internal exception behavior only; no browser leak or real secret exposure is claimed. Accepted private wrapper controls (#564) remain closed.

Follow-ups were deduplicated across all issue and PR states (initial 277 issues / 291 PRs, refreshed before helper follow-ups; actual #550/#551/#564 bodies read). They are separate maintenance, not grounds to reopen accepted Users workflows or silently extend this lane into a shared security rewrite.

Full unrelated backend/frontend/ETL suites, real PostgreSQL semantics, hosted backend/frontend/ETL/security/quality gates and production provider behavior are unexecuted. GitHub Actions is disabled per the batch scope; no workflows/rules/statuses were changed or fabricated. Broad backend critical lint is **not green** because of #569. Local fixtures do not certify deployed readiness.

Delivery stops at a pushed scoped branch and attached **draft PR**. No merge, bot review request, production activation, publishing or paid service/design request is included. Coordinator owns combined replay, established PR-comment handling, issue closure and integration.
