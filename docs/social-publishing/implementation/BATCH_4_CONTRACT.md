# Batch 4: operational evidence and Meta privacy prerequisites

Authorized 2026-10-08, continuing the three-agent development and independent
verification process. Base main: `f5239ed63e146650bee2d0fb1cec9b23616eb648`.
PRs #513, #514 and #515 are merged. This batch prepares reviewable offline
tools and privacy primitives; the operational issues remain open until actual
deployment evidence and owner decisions exist.

## Ownership and boundaries

Three existing GPT-6.1 Sol/xhigh agents reuse their managed worktrees. Root owns
integration, independent behavioral review, merge receipts and final handoff.

| Owner | Branch | Owned paths |
| --- | --- | --- |
| Media | `codex/social-media-acceptance` | `backend/social/media/acceptance.py`, `backend/scripts/social_media_acceptance.py`, `backend/tests/social/test_media_acceptance.py`, `docs/social-publishing/implementation/MEDIA_OPERATIONAL_ACCEPTANCE.md`; narrow media README refresh |
| Native/privacy | `codex/meta-privacy-prerequisites` | `backend/social/connections/signed_requests.py`, `backend/social/connections/ownership.py`, their two corresponding social test files, `docs/social-publishing/implementation/META_PRIVACY_CALLBACKS_PREREQUISITES.md` |
| Operating budget | `codex/social-operating-acceptance` | `scripts/verification/evaluate_social_operating_budget.py`, `backend/tests/egress/test_operating_acceptance.py`, `docs/infrastructure/supabase-egress/OPERATING_ACCEPTANCE.md`, `docs/infrastructure/supabase-egress/fixtures/social-operating-synthetic.json` |
| Root | `codex/social-operational-integration` | This contract, `BATCH_3_HANDOFF.md`, `BATCH_4_HANDOFF.md`, combined verification and scoped PR integration |

All worktrees are under `/Users/roger/.codex/worktrees`, preserving their prior
branches. Authors do not push, merge, install dependencies, edit other scopes,
or truncate PostgreSQL fixtures. Finish code, execute tests, and report readiness
before committing; independent agents attack each new verdict/parser before
root authorizes scoped commits. Root creates draft PRs after combined checks.
The dirty primary checkout remains untouched.

## #490 media evidence

Provide a bounded strict offline packet validator/evaluator. Bind purpose
`social_media_490` to exact account endpoint, private bucket, browser origin,
intended host, build and configuration fingerprint. Require independent gates
for privacy, least privilege, signed-PUT semantics, actual-browser CORS,
intended-host inspection/resource limits, inventory/retention/quota/backup and
accepted hosting profile. Source-storage receipts and local OPTIONS/signing
tests cannot substitute for social workload or actual-browser evidence.

Distinguish missing evidence, unverified supplied evidence and readiness for
operator review. A matching packet/hash validates declared evidence only; it
does not authenticate receipts, accept production, authorize publishing or
prove write quiescence. Keep these outputs explicitly false/not run. No runtime
storage calls, deletion, maintenance activation, configuration enabling or
new quiescence authority. Ready-original deletion remains deferred.

Declared child resource limits must match the existing inspection implementation.
Probe disposition must be explicit and consistent with inventory/reservations;
asserted probe removal does not prove outstanding writes are quiescent. Parser
errors must not retain raw input in exception context. File readers refuse
nonregular, symlinked and oversized inputs without blocking.

## #488 privacy prerequisites

Implement strict bounded HMAC-SHA256 verification of the original encoded Meta
signed-request payload, with injected secret and expected app ID. Reject bad
base64url/signature sizes, duplicate JSON keys, unknown algorithm, malformed
subject and optional timestamps/app identity. Constant-time signature comparison
and sanitized exceptions/representations must hide secrets, raw requests and
app-scoped subjects. Signature verification alone establishes neither freshness
nor idempotency nor completed deletion.

Add exact app/inspected-ASID/credential UUID/version ownership binding. Missing,
legacy or mismatched ownership is unverified; supplied matching inputs do not
establish provider verification. No router, schema, loader, grant scanning,
callback activation, public policy change or claim that callbacks are installed.
Document durable indexed ownership, idempotent receipts, uncertain/in-flight
delivery preservation, deletion/backup/retention policy and key restoration as
remaining gates. Use current official Meta sources without inventing contracts.

## #481 operating evidence

Implement a standard-library offline evaluator of bounded sanitized JSON.
Require seven consecutive complete closed deployed days, exact organization,
project, cycle, timezone, deployment and explicit as-of identities, provider
total uncached bytes with units/rounding and hashed receipts. Require measured
social transfer and representative API/cache/nightly/restart/deploy/worker
activity. Cumulative SQL counters and decoded fixtures are not billed bytes;
missing/reset/evicted query counters cannot establish delta attribution. Declared
delta history includes stable global deallocation counts and per-shape gathering
start timestamps; matching monotonic endpoints alone cannot prove continuity.

Use the existing planning targets (120 MB/day total and 200 MB/month social),
exact cycle length, conservative rounding, peak days, reserve and explicit
future increment overlap handling. Provider totals and included workloads must
not be double-counted. Already-accrued cycle usage must be retained from an
explicit provider receipt, or the observed window must cover all elapsed closed
cycle days. A seven-day estimate cannot replace prior charges. Social projection
uses the actual cycle length and includes additional social-worker increments.
Daily receipts bind exact dates/intervals; declared web capacity cannot understate
the unchanged build's five pooled plus ten overflow connections per process.
Hosting requires ownership/always-on/cost acceptance and
deployment-bound timestamps. Capacity accounts for replicas/processes/web
pool+overflow, worker and ETL/admin, against a matching verified limit kind.
Actions-off-only evidence or absent worker/process/host coverage is insufficient.

Return BLOCKED, OVER_BUDGET or CANDIDATE_FOR_OWNER_REVIEW with unknowns and
provenance; always retain `production_authorized:false`. The synthetic fixture
is visibly synthetic and cannot become real acceptance. Never query a database,
read credentials/environment defaults, make network calls or alter hosting/CI.

## Verification and closeout

Execute positive fixtures and direct hostile calls, not source-text assertions.
Cover missing/empty/malformed/duplicate/unknown JSON, bounded sizes, stale/mixed
identities, bool-as-number, NaN/inf, wrong units, incomplete evidence and secret
leakage. Exercise CLI help/default/error paths without external side effects.
For confirmed independent findings retain regressions with observed red results.
Root runs relevant combined suites and reports limits honestly.

The initial main base had three pre-existing TS2353 map-style errors, reproduced
with the same dependencies on main and the native branch. PR #516 subsequently
corrected those map/build compatibility prerequisites; TypeScript passes on the
review base `8ba731a` with matching dependencies. Batch 3 final-main backend
social tests passed 1,168 with zero skips and frontend passed 501. New code in
this batch has no frontend scope. Real bucket/app/host identifiers and deployed
operational receipts remain unverified; no live activation is authorized by a
fixture or a candidate report.

Review closeout is recorded in `BATCH_4_HANDOFF.md`. New independently reproduced
origin serialization and future zero-wire defects were tracked in #520/#521 and
fixed within #517/#519. The original scope/false-authority boundaries remain.
