# PR #531 review receipt — 8 October 2026

Reviewed head: `6ed0fe6a45f1a6886cf8f0b312959fa15c1d6909` on
`codex/social-operating-evidence`. Three inline findings and the body's
receipt-kind compatibility concern were executed before repair. A separate
import-status consistency probe also reproduced a defect. These checks use
standalone helpers, declared fixtures and a private PostgreSQL server; they
authenticate no production receipt, billing amount or operating acceptance.

## Classification and repairs

| Finding | Observed behavior before repair | Repair and retained control |
| --- | --- | --- |
| Sequence ownership, thread 4224222096 | Direct/inherited sequence owners and USAGE/UPDATE grants returned `OBSERVED_COUNTERS_ONLY`. | Check ownership across non-catalog relation kinds, and sequence USAGE/UPDATE separately from table/column privileges. SELECT-only sequence access remains accepted. |
| Idle transaction timeout, thread 4224222159 | Actual `0`, `4s` and `10s` sessions returned observed counters despite the requested `5s`. | Read back and require `idle_in_transaction_session_timeout = 5s` before statistics collection. |
| Supplied open slot, thread 4224222204 | Partial receipts or malformed partial sections discarded the seven-slot ledger and six valid closed days. | Keep the open slot missing with no bounds after basic record identity validation. Exclude its unvalidated sections from activity and measurement-basis aggregates. |
| Receipt-kind compatibility, review body | Decoded/cumulative provider-kind declarations discarded the ledger; protocol-kind equivalents passed. | Match the unchanged evaluator's two permitted kinds for these unmeasured bases. They still have zero covered days and explicit unmeasured transfer. Measured kinds remain exact. |
| Imported status consistency, independent probe | A `PARTIAL_OBSERVATION` label with complete data and empty unknowns returned `DECLARED_COUNTER_DELTA_ONLY`. | Require status derived from validated snapshot unknowns on both imports, in addition to payload and unknown-list consistency. |

All five are confirmed defects. Sequence mutation grants and ignored open-day
aggregates expand the corresponding review hypotheses to the full invariant.
No caller gains authority from a label, content hash, decoded estimate or
cumulative counter. The full evaluator and its schema are unchanged.

## Observed red and green commands

Commands ran from the owned worktree with the existing Python 3.13.9 interpreter.
The focused tests were retained before changing product code.

```sh
SOCIAL_OPERATING_OWNED_PG=61281 PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -B -m pytest --noconftest -p no:cacheprovider backend/tests/egress/test_social_operating_owned_postgres.py -q --tb=short -k 'sequence or idle_transaction'
```

Red: **7 failed, 1 passed, 11 deselected**. The matched positive was SELECT-only
sequence access. After repair the complete private PostgreSQL module passed
**19 tests**, including existing column/schema/owner guards and connection
cleanup. The explicit injected driver is not production TLS evidence.

```sh
PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -B -m pytest --noconftest -p no:cacheprovider backend/tests/egress/test_social_operating_collection.py -q --tb=short -k 'open_slot or unmeasured_social_receipt'
```

Red: **4 failed, 3 passed, 85 deselected**. Both supplied partial/malformed open
sections and both provider-kind unmeasured declarations failed; missing open
sections and protocol-kind declarations were controls. Green: all seven cases
pass. Closed-day ledger counts and missing/unverified markers are asserted.

```sh
PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -B -m pytest --noconftest -p no:cacheprovider backend/tests/egress/test_social_operating_independent.py -q --tb=short -k partial_artifact_without
```

Red: **2 failed, 91 deselected**; before and after imports returned a declared
delta instead of refusal. Green: both return `BLOCKED` with
`SNAPSHOT_STATUS_MISMATCH`.

Final combined command:

```sh
SOCIAL_OPERATING_OWNED_PG=61281 PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -B -m pytest --noconftest -p no:cacheprovider backend/tests/egress/test_operating_acceptance.py backend/tests/egress/test_social_operating_collection.py backend/tests/egress/test_social_operating_independent.py backend/tests/egress/test_social_operating_owned_postgres.py -q --tb=short
```

**371 passed, zero skips, zero warnings**: unchanged evaluator 163,
collection/preparation 96, independent preparation 93, private PostgreSQL 19.
The three offline modules also passed **352 tests** under actual
`/usr/bin/python3` **3.9.6**. That runtime reported two existing unknown-pytest-
option warnings because its asyncio plugin is absent. `--noconftest` isolates
these standalone tests from application startup; no full-application runtime
compatibility claim is made.

Additional hostile direct-call matrix:

```sh
PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/venv/bin/python -B /Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_5_REVIEW/pr531_adversarial_collect.py
/usr/bin/python3 -B /Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_5_REVIEW/pr531_adversarial_collect.py
docker run --pull=never --rm --network none -v /Users/roger/.codex/worktrees/social-operating-evidence/audit_app:/scope:ro -v /Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_5_REVIEW:/review:ro -v /Users/roger/.codex/worktrees/social-operating-evidence/audit_app:/Users/roger/.codex/worktrees/social-operating-evidence/audit_app:ro -e PYTHONDONTWRITEBYTECODE=1 -e PYTHON_DOTENV_DISABLED=1 python:3.12-slim python -B /review/pr531_adversarial_collect.py
```

Each runtime (**3.13.9, 3.9.6, 3.12.15**) rejected **194/194** hostile inputs,
with zero unexpected accepts and a matched seven-statement fake-driver positive.
Cases include numeric/time/history, reader/auth scope, malformed identity rows,
session settings, files, direct/CLI refusal and absence of authority promotion.
The existing Linux image ran with network disabled and read-only mounts.
Replacing the script in these three commands with `pr531_runtime_compat.py`
also passed the missing-seven-days/blocked-synthetic smoke on 3.9.6 and 3.12.15.
No dependency was installed.

Root independently inspected the shared reader/preparation gates and reran
**352 offline plus 19 actual private PostgreSQL tests**, all passing with zero
skips and warnings. The scope-owned `audit-pr531-operating-review-pg` container
was then stopped and removed. Exact-name Docker inventory and loopback 61281
listener checks returned no remaining container or listener.

## Invariant and callers

- `_snapshot` is the single executed reader/session gate used by `collect`.
  Collector CLI calls the same `collect`; PLAN_ONLY neither reads private
  credentials nor connects. Tests exercise direct and CLI entrypoints.
- `_day` is called only by `coverage`; preparation CLI calls that same function.
  Closed-day activity and social-basis aggregates now exclude every open slot.
- Fresh `collect` and `_import_snapshot` both call `validate_snapshot`.
  `delta` imports both endpoints through `_import_snapshot`; preparation CLI
  calls the same delta path. Missing/reset/eviction history and offset-equivalent
  instant comparisons retain the original guards.
- Receipt validation and the full evaluator remain shared and unchanged. Only
  preparation's unmeasured-kind compatibility changes; it never converts those
  assertions to measured transfer or acceptance.

## Tracking and remaining gates

Read-only GitHub searches for sequence/idle collector, operating history and
counter-status defects found parent #481/#476 but no exact concrete duplicate.
Root filed the grouped defects as [#539 reader boundary](https://github.com/Rodgers31/audit_app/issues/539),
[#540 history/status/workload coverage](https://github.com/Rodgers31/audit_app/issues/540),
and [#541 partial ledger/receipt kinds](https://github.com/Rodgers31/audit_app/issues/541).
The scoped repairs above address those fixed issue IDs; root owns review replies,
issue resolution and publication. The prepared issue bodies remain in
`BATCH_5_REVIEW` as `issue_operating_reader_boundary.md`,
`issue_operating_history_coverage.md`, and `issue_operating_partial_ledger.md`.

The drafts include the original author's saved red evidence for column/schema/
relation ownership, six missing/changed history cases, three equivalent-offset
cases and all-zero workload coverage. Those historical logs were inspected;
this review reran their current retained green tests but did not recreate the
original first draft.

Real seven closed representative post-rollout days, a provisioned approved
reader, source-authenticated wire/provider measurements, caller attribution,
accrued allowance/reserve reconciliation, complete host inventory and owner
hosting/connection acceptance remain pending under #481. No live query,
deployment, job activation, purchase or production mutation was performed.
The review's disposable PostgreSQL server is confined to loopback 61281;
coordinator and other scopes' ports were untouched.
