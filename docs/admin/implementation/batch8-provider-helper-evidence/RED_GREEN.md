# Executed regression receipts

External evidence root:
`/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-74018ef2d342/batch8-provider-helper-evidence/`.
Every recorded run has an exact argv/cwd/environment, exit code, helper/test
SHA256 and log SHA256 in `<label>.json`, with the full observed output in
`<label>.log`. The compact committed `RUNS.json` reproduces those receipts.
Pre-commit runs correctly record HEAD as the pinned base and separately hash
the actual working helper; they are not claims of a passing committed head.

Base: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, tree
`f22a430a4402d79867da63ad97db8c8d474d3a71`, helper SHA256
`fdb2ba0c7e95da9bcdf945d244f6cff67d9899d8ea6371c4fc5c40891c04d003`.
The final fixture baseline replay imports the exact `git show BASE:backend/supabase_admin.py`
snapshot in a fresh process without changing the worktree or any runtime.

| Run | Observed result |
| --- | --- |
| `baseline-observations` | Exit 0; actual original issue inputs give two `id` filters and wrong identity; object bulk → `[]`; HTTP503 text/body include inert diagnostic marker; three memory calls, no sockets. |
| `profile-core-red` / `profile-core-green` | Exit1, 2 failed/1 passed → exit0, 3 passed. |
| `diagnostics-red` | Exit1, 30 failed/3 deselected: HTTP error body retained, raw HTTPX failures, rejected/invalid/deep JSON. |
| `diagnostics-green` | Exit1, 9 failed/24 passed because two empty-bulk control assertions had been misplaced in the JSON test. Test-authoring error, not a remaining product diagnosis. Retained unchanged. |
| `diagnostics-green-corrected` | Exit0, 33 passed; all nine actual legacy operations print status503, static text and body `None`. |
| `expanded-baseline-red` | Exit1, 178 failed/6 passed against pinned helper snapshot. Earlier expanded fixture retained, not replaced. |
| `active-baseline-control` | Exit0, 164 retained auth/Users/audit cases pass with pinned helper. |
| `profile-matrix-green` / `imports-green` / `combined-green` | Exit0: 252, 2 and 418 passed respectively; overlapping selections, not additive coverage. |
| `independent-findings-author-red` / `independent-findings-author-green` | Exit1, 23 failed → exit0, 23 passed; InvalidURL/credential/header diagnostics and explicitly narrowed UUID grammar. |
| `final-fixture-baseline-red` | Exit1, **209 failed/6 passed** against exact pinned helper, final fixture SHA256 `ffe58e48bb67882fd5794b1ce2b9ada60c45951d6f17469c81f7377d2c18a374`. |
| `final-combined-green` | Exit0, **449 passed**, two existing SQLAlchemy warnings. Includes 215 new helper cases, two fresh import cases, 68 retained helper/import cases, 164 active Users/auth/audit cases. |
| `final-scoped-lint` | flake8 7.3.0 critical gate, output `0`, exit0 for changed helper/tests and committed socket-denial runner. |
| `broad-lint` | Exit1, unchanged `scripts/r2_producer_acceptance.py:440:9 F821 undefined name 'captured'`, tracked #569. The producer is byte-identical to base: SHA256 `15b2a796171a9bd8b994d1de16bc8a4e49b863a57dc85dd77baa78395aad1028`. |
| `context-claim-author-confirm` | Exit0, two inert probes confirm normal tracebacks suppress encoding-error markers while internal `__context__.object` retains them. Overbroad report wording corrected; no ordinary-surface product defect inferred. |

All provider values, identities, keys and JWTs are synthetic fixtures. Actual
HTTPX MockTransport executes the real helper. Socket connect/connect_ex are
refused before application imports, and tests retain their own refusal fixture.
Fresh subprocess controls supply clean environments and both supported import
modes. App modules are imported under the ordinary conftest; product lifespan
and live provider operations are not entered. No browser leak is asserted.

Reproduce the final relevant suite from `backend/`, with an owned temporary
directory and a compatible runtime (Python3.13.9/httpx0.28.1/pytest9.0.2 used):

```sh
env -i PATH=/usr/bin:/bin PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 \
  PYTHON_DOTENV_DISABLED=1 DATABASE_URL=sqlite:////owned/temp/provider-helper-import.sqlite \
  SUPABASE_URL=https://batch8-helper.invalid \
  SUPABASE_SERVICE_ROLE_KEY=inert-batch8-service-key \
  SUPABASE_JWT_SECRET=inert-batch8-jwt-secret \
  /path/to/read-only/python ../docs/admin/implementation/batch8-provider-helper-evidence/pytest_no_sockets.py \
  -p no:cacheprovider --basetemp=/owned/temp/provider-helper-replay \
  tests/test_batch8_supabase_helpers.py tests/test_batch8_supabase_helpers_imports.py \
  tests/test_batch7_supabase_helpers.py tests/test_batch7_supabase_helpers_imports.py \
  tests/test_admin_users_boundaries.py tests/test_admin_users_review.py \
  tests/test_admin_users_adversarial_replay.py tests/test_admin_users_audit_policy.py -q
```

`--basetemp` must be owned/disposable: pytest may remove it at startup. Do not
reuse another session's directory. Create the owned parent directory first;
keep the import SQLite path outside `--basetemp`. An in-memory `sqlite://` URL
does not accept the existing database factory's pool arguments; use a file URL
as in the actual retained receipts. The Spec review's failed reproduction attempt
is retained separately; it established a documentation error, not a product bug.
Whole unrelated backend/frontend/ETL suites,
real provider/production/database semantics and disabled hosted gates are not
certified by this lane selection.
