# Executed baseline and vertical slices

Pinned source `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`, tree
`712b43650b1203ffd84583b67d07d30775669b1e`. Worktree was clean before edits.
All commands used `env -i`, `PYTHON_DOTENV_DISABLED=1`,
`PYTHONDONTWRITEBYTECODE=1`, absolute owned backend PYTHONPATH and an inert
explicit DATABASE_URL. Interpreter: primary venv Python 3.13.9, read-only reuse.

Baseline command: `python -m pytest backend/tests/test_admin_operations_lane.py
backend/tests/test_admin_operations_adversarial.py backend/tests/test_etl_admin_endpoints.py
backend/tests/test_web_ingestion_ownership.py backend/tests/test_ingestion_query_transfer.py -q`.
Actual result: **134 passed, 2 warnings in 1.85s**.

Before product edits, `python -m pytest backend/tests/test_batch7_etl_contract.py -q`
executed the actual mounted pinned router, inert administrator auth, and
`GET /api/v1/admin/etl/dispatch`. Actual failure:

```
assert response.status_code == 200
E assert 404 == 200
1 failed, 2 warnings in 0.06s
```

This exercised the missing public contract, not source text or a mocked executor.
After the first repair the same fixture plus existing Operations route controls
passed: **38 passed, 2 warnings in 0.98s**.

Initial PostgreSQL acceptance/history run exposed a real SQL join defect:
history returned static 503 rather than the expected bounded 200 page.
Result **1 failed, 5 passed**; after correcting the anchored single-snapshot
count/page join, **6 passed in 0.42s**. The unchanged test retains the regression.

Initial process harness used the wrong subprocess PYTHONPATH; this was a test
infrastructure failure, not a claimed product red. Corrected process run:
**5 passed in 16.76s**. Initial migration fixture mistook JSON text for a SQL
bind parameter; corrected with jsonb_build_object. Actual migration roundtrip:
**2 passed in 1.38s**. No product migration was applied outside owned PostgreSQL.

Final author combined run before independent review: **207 passed, 3 warnings
in 21.61s**; output retained in `final-author.txt`. This includes all new lane
tests, 134 current Operations/calendar/ingestion controls and native CLI budget
and seeding utility controls. The full repository/deployment/coverage gates
have not been executed; hosted Actions is disabled.
