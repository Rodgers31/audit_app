# Batch 8 legacy Supabase helper handoff

Originating issues [#570](https://github.com/Rodgers31/audit_app/issues/570) and
[#571](https://github.com/Rodgers31/audit_app/issues/571); parent
[#545](https://github.com/Rodgers31/audit_app/issues/545).

## Source and ownership

- Managed worktree: `/Users/roger/.codex/worktrees/2262/audit_app`, attached to this
  chat; branch `codex/batch8-provider-helper`. Its initially clean HEAD/tree
  matched the fixed source before branch creation or application edits.
- Base commit: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`; tree
  `f22a430a4402d79867da63ad97db8c8d474d3a71`.
- Final implementation source: `2ae043cc3930d40bb15deb25525fe49c5b13ee1e`; tree
  `529438255b340f3c8a32274e7d0164b6314f74ee`. Later commits are handoff/evidence
  delivery only; the exact delivered Git head is recorded in external
  `DELIVERY.json`, PR metadata and the author final response.
- Helper blob: `96969c07d98f57ec15c2a33e4474e5bcf2b191fa`; SHA256
  `9a74e003f90b333c38503ca2fde4683cfd99ddcf70a1b8d5fd4ae1291612b5b1`.
- Only production change: `backend/supabase_admin.py`. Changes also include two
  directly related new test files, the old helper's transport-error expectation,
  this handoff and owned evidence. Shared auth, active provider/router, main,
  models, native CLI, producer, frontend and financial sources are unchanged;
  [source controls](batch8-provider-helper-evidence/SOURCE.json) retain exact hashes.

The frozen Batch 8 spec and exact issue snapshots/current GitHub updates were
read, together with CONTEXT.md, TESTING_GATES.md and Batch 6/7 acceptance/helper
briefs. No applicable AGENTS.md was found in checkout/ancestors. All named lane
skills were read/applied, including the independent Standards/Spec and adversarial
execution requirements. No repository agent-policy setup was added. The dirty
primary checkout and other sessions' runtimes/caches/processes were never mutated.

## Result and compatibility

Actual generic reads validate string UUID inputs before transport and construct
one identity filter through HTTPX parameters. Supported spellings, duplicate
caller behavior and provider membership rules are explicit in
[DECISIONS.md](batch8-provider-helper-evidence/DECISIONS.md). Bulk request UUIDs
deduplicate in request order; valid returned rows retain their fields and provider
order. Missing requested bulk rows are allowed. Only a valid empty row array
means missing. Invalid containers/rows/identities, duplicate/unrequested IDs and
failure verdicts reject the whole response with safe 502. Caller query syntax,
wrong types and malformed UUID spellings produce safe 400 before transport.

Shared exceptions keep public imports/class identity, status and constructor
argument compatibility. Provider body is neither rendered nor retained;
`.body` is always `None`. HTTP errors retain status, HTTPX failures become safe
503, rejected JSON becomes safe 502. Malformed configuration URL/key construction
errors become safe 500, and invalid per-call headers safe 400. Ordinary formatted
tracebacks suppress original sensitive exception chains. Python's internal
`__context__` and frame locals can still retain the original inputs; deliberate
exception/frame introspection is outside these ordinary diagnostic guarantees.
The Standards probe and author replay confirm this limit. No trusted diagnostic
channel or automatic retry was added. An unconfirmed mutation can already have
occurred upstream.

The [caller inventory](batch8-provider-helper-evidence/CALLERS.md) establishes that
signed auth is the remaining product consumer of the retained profile reader.
It catches the same exception and still grants only valid roles. Active Users
uses a separate implementation, shares configuration/exception imports, and
keeps its status-only wrapper classification. No repository consumer needs raw
exception body. Actual signed JWT, active provider, route wrappers and both fresh
import modes were exercised. #550/#551/#564 accepted paths are preserved.

## Verification and review

[RED_GREEN.md](batch8-provider-helper-evidence/RED_GREEN.md) and
[exact run receipts](batch8-provider-helper-evidence/RUNS.json) retain commands,
observed exits/output identities, source/fixture hashes and earlier failures.

- Exact original baseline probe observed duplicate `id` filters returning wrong
  identity, malformed bulk object returning `[]`, and HTTP503 marker in exception
  text/body; actual memory calls with socket transport denied.
- Final fixture on exact baseline: **209 failed / 6 passed**, exit1. Final
  implementation suite: **449 passed**, exit0, two existing SQLAlchemy warnings.
  This includes 215 new helper cases, two new fresh-import cases, 68 retained
  helper/import cases and 164 retained auth/Users/audit controls. Counts overlap
  earlier runs and are not additive coverage.
- Scoped critical flake87.3.0: output `0`, exit0. Broad critical lint: unchanged
  producer F821 tracked by #569; base/current producer SHA256 matches. No broad
  lint green or full unrelated backend/frontend/ETL claim is made.
- Independent [read execution](batch8-provider-helper-evidence/ADVERSARIAL_READS.md):
  **592 controls**, **376 actual memory requests**, both modes exit0. Initial
  permissive UUID normalization observation was deliberately tightened with
  observed red/green fixtures; no query-injection defect was inferred from it.
- Independent [error execution](batch8-provider-helper-evidence/ADVERSARIAL_ERRORS.md):
  initial **233 passing / 16 failing** probes found InvalidURL and credential/header
  encoding leaks; author reproduced them. Final **564 controls** across both modes
  exit0, plus independently replayed **449 tests**. Both findings are valid and
  resolved; unsupported raw argument misuse is classified separately.
- Independent [Spec](batch8-provider-helper-evidence/SPEC.md): **0 remaining
  missing/partial, scope or incorrect-implementation findings**. It caught the
  in-memory SQLite URL in the documentation; the corrected documented command
  independently passes 449 tests. Its failed attempt remains retained.
- Independent [Standards](batch8-provider-helper-evidence/STANDARDS.md): **0 hard
  implementation violations / 0 remaining documentation findings**, **one optional
  duplication advisory** for the read/mutation failure-verdict guard. Existing
  read/mutation identity/role semantics remain distinct in this scoped repair;
  a shared predicate is discretionary maintenance, not an acceptance blocker.
  Its valid evidence wording correction was independently reproduced and fixed:
  ordinary tracebacks suppress original exceptions, but internal context remains.
  Its final completion wording recheck passes; initial findings/probes remain
  retained. The two axes are independent; no optional design finding is counted
  as a tool-enforced standard or acceptance blocker.

All provider/JWT/user values are inert fixtures. Tests use actual MockTransport
and ASGI/dependency boundaries, deny socket connect/connect_ex, and disable dotenv
and bytecode writes in fresh clean environments. Product lifespan, real provider,
browser/production diagnostics and real database semantic acceptance are outside
these receipts. Hosted Actions remains disabled and unexecuted.

## Evidence, runtime and cleanup

Committed compact evidence:
`docs/admin/implementation/batch8-provider-helper-evidence/`.
Larger raw logs, executed probes, issue snapshots/catalog and final delivery packet:
`/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-74018ef2d342/batch8-provider-helper-evidence/`.

Read-only product runtime: `/Users/roger/Documents/projects/audit_app/venv/bin/python`,
Python3.13.9, macOS27.0.1 arm64, httpx0.28.1, pytest9.0.2, SQLAlchemy2.0.46.
Lint used an owned external venv with flake8 7.3.0, pyflakes3.4.0,
pycodestyle2.14.0 and mccabe0.7.0. No shared environment installation occurred.
Owned lint/cache/test temporary paths were removed; their observed absence is
recorded in [CLEANUP.json](batch8-provider-helper-evidence/CLEANUP.json).
Independent adversarial agents removed their disposable
test trees. No server, bound port, worker group or container was needed/created.
No other session's resources were stopped or removed. Managed worktree and raw
evidence remain for coordinator review.

## Issues and next action

Current all-state GitHub catalog: 282 issues, including actual comments; #570/#571
remain open with no new comments. #550/#551/#564 remain closed. Additional
confirmed diagnostics fall within #571, and supported UUID grammar falls within
#570; no duplicate issue was opened. #569/#572/#494 belong to the other lanes,
and broader/operational parents remain open. No Actions, rules, security gates,
live users/providers/storage, publishing/ETL activation or financial behavior was
changed. No deployment, production migration or paid/bot review was requested.

Local scoped implementation and independent acceptance are complete. Next action:
coordinator exact-head review of the scoped draft PR, combined integration and
manually requested Copilot handling. #570/#571 remain open until that acceptance
and closure; #545 and operational acceptance remain broader work. Do not merge
from this author session.
