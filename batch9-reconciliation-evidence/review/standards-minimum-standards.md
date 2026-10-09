
## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T23:41:25.603360+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "dda31979da6cf3867bb7e8076740e4233af0d68a3c56d01782ccef0b9a5c16a2",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "4ccaf416c5d1180e24bf45a020b50b559289128836d9b33ab35aa26663607e1e",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2",
    "batch9-reconciliation-evidence/operator-procedure.md": "db705d8dcddfbd251f43a4aade9fd93e31c2f38e1ee197563e6a3c05a5453106",
    "batch9-reconciliation-evidence/read_only_census.sql": "3bab1b6073c4e915d2cd12cf6ed52f649cae59ffea6f8739dd6d2e88a4e44f26",
    "batch9-reconciliation-evidence/writer-census-review.json": "bb1be409583d3f1243ae5eb45a7054d23ae96dcd0182fa1fe10adbf779694ca6",
    "batch9-reconciliation-evidence/inventory_receipt.py": "9c9de44e28889ed0517556f8aa0d2aab52895ad61911bf01b567d7b9f1074d98"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "93f39ded212edb9e847221cdb7def25900015159",
  "command": [
    "/Users/roger/.codex/worktrees/a46a/audit_app/.batch9-min/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py"
  ],
  "environment": {
    "PATH": "/usr/bin:/bin:/usr/local/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONPATH": "/Users/roger/.codex/worktrees/batch9-pr592-review/audit_app/backend",
    "DATABASE_URL": "[REDACTED]",
    "BATCH9_RECONCILIATION_DATABASE_URL": "[REDACTED]"
  },
  "runtime": {
    "python": "3.12.15 (main, Oct  3 2026, 00:54:33) [Clang 22.1.3 ]",
    "sqlalchemy": "2.0.23",
    "platform": "macOS-27.0.1-arm64-arm-64bit"
  },
  "controls": [
    {
      "control": "valid_ascii",
      "expected_accepted": true,
      "actual_accepted": true,
      "diagnostic": "accepted"
    },
    {
      "control": "valid_unicode_max_effects",
      "expected_accepted": true,
      "actual_accepted": true,
      "diagnostic": "accepted"
    },
    {
      "control": "whitespace_only_why",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Nonblank bounded text required"
    },
    {
      "control": "boolean_version",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Unsupported evidence version"
    },
    {
      "control": "artifact_wrong_container",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Complete host and scheduler scope evidence required"
    },
    {
      "control": "missing_effects_artifact",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Incomplete or unreferenced evidence"
    },
    {
      "control": "uncertain_writer",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Live or uncertain writer evidence"
    },
    {
      "control": "duplicate_scope",
      "expected_accepted": false,
      "actual_accepted": false,
      "diagnostic": "Missing or duplicate deployment scope"
    },
    {
      "control": "allowed_unicode_effects_durable_record",
      "evidence_validation": "accepted",
      "durable_record_characters": 2193,
      "constraint_limit": 4000,
      "storage_rejected": false,
      "diagnostic": "insert accepted",
      "durable_fixture_rows_before_cleanup": 1,
      "interpretation": "fixed representation"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded",
  "receipt_safety_sha256": "02ac0d6ae12205d4a818301367bced2787f65e0fe71eebdfa89e6c95f275a2c4"
}
```
