# Independent Standards review — Batch 9 reconciliation

Review requested against pinned `9e97ca3f1ca43f103a8655447a86d889456a218a`, including untracked reconciliation files. Initial product HEAD is the pinned source; this is an uncommitted working-copy review. No product edits, production operations, GitHub mutations, or shared-runtime installation were performed by this reviewer.

Standards sources read: `CONTEXT.md`, `TESTING_GATES.md` (historical hosted-execution assertions are not used as evidence), `docs/admin/implementation/BATCH_8_EXCLUSION_CONTRACT.md`, `docs/admin/implementation/BATCH_8_NATIVE_EXCLUSION_HANDOFF.md`; required current skills `code-review`, `state-persistence-invariants`, `verify-boundary-shapes`, `no-silent-fallbacks`. No applicable `AGENTS.md`/`CLAUDE.md` was found in the worktree, backend/docs trees, or filesystem ancestors checked. `docs/agents/issue-tracker.md` is absent; this reviewer does not install configuration or mutate issue tracking.

## Implementation re-review status

All three historical findings below are repaired on reviewed product source `5540a23bce38dc943a80bf649da93a448f14bc6dcab8cf856bfe913799bbfde9` (`backend/seeding/reconciliation.py`). The final independent receipts prove genuine terminal adapter/CLI refusal acceptance, permitted Unicode durable storage, and rollback when the signed freshness window expires during a real PostgreSQL update. The expiry regression passes on both CPython 3.13.9 / SQLAlchemy 2.0.46 and CPython 3.12.15 / actual SQLAlchemy 2.0.23. Host/scheduler statements now require the signed promise `fence_release=explicit_operator_after_durable_audit`; elapsed freshness time never authorizes restoration. Final `_maintenance` and `_continuity` checks run before the same lock-holding transaction commits. The final product source is `4ccaf416c5d1180e24bf45a020b50b559289128836d9b33ab35aa26663607e1e`; its change since the prior reviewed source removes an unused import. **No unresolved implementation or operator-procedure Standards blocker is identified.**

The author's `current-core-green.json` and `minimum-core-green.json` were independently read: each reports **87 passed**, no skips/xfails, on this same product source hash, including real native/worker/adapter/orphan process and pre-claim legacy-schema controls. These are author-executed suites, not this reviewer's own test execution. This reviewer owns only this report and uniquely named standards generators; no product file or operational settings were edited.

Final procedure review read `operator-procedure.md`, `read_only_census.sql`, `writer-census.json` and its generator. The document clearly states that actual Supabase superuser/catalog admission and direct-path feasibility remain uncertified; it cannot infer directness from a URL label or backend PID, infer pooler cutoff from server settings, or treat a signature as truth. It distinguishes whole-database outage/readiness effects, complete host/scheduler/application/manual/legacy/bootstrap inventory, separate trust-policy provisioning, signed effects context, exact pre-claim untagged observations, uncertainty after lost commit/report, and explicit durable-audit restoration. No timer restores writers. The read-only census contains only diagnostics and explicitly begins READ ONLY; its effective setting must be inspected as instructed, rather than assumed from startup connection options. This procedure is a reviewed candidate, not production-operation authorization or proof that the current provider can execute it.

The final readback receipt verifies all **397** writer-census source hashes and the inventory generator, **15** native domains and **1218** candidate anchors, preserving the stated limit that runtime/deployment coverage is unverified. `final-current.json` and `final-minimum.json` each report **102 passed**, exit 0, no skips/xfails, on final source `4ccaf416...607e1e`; these were author-executed and independently read back here. One non-blocking wording nit was sent to the author: clarify that tabs/newlines are rejected when they make a field whitespace-only, while any NUL is rejected; the code intentionally accepts meaningful text containing ordinary whitespace. No materially risky judgment smell is raised.

## Historical documented-rule findings (repaired)

- **P2 — legitimate terminal dispatch refusal is rejected as an invalid entry correlation.** In `backend/seeding/reconciliation.py` the `related` branch accepts a dispatch command/token as a relationship, then requires `seeding_claim_id` for all such rows. Actual CLI refusal rows have the command/token but no seeding claim tag, `status=FAILED`, and JSON boolean `ownership_refused=true`; the existing actual adapter/CLI control `backend/tests/test_batch8_exclusion_review.py::test_actual_cli_boolean_refusal_permits_never_entered_finish` documents that shape. A retained never-entered dispatch claim plus this receipt cannot be planned after supervisor loss. This violates the `verify-boundary-shapes` requirement to enumerate real input shapes and the Batch 8 recorded refusal/retention contract. It is a fail-closed availability defect, not unsafe release. Initial evidence is code-path inspection; an executed reconciliation-path control is still required before considering this finding confirmed or resolved.
- **P2 — accepted Unicode evidence overflows the durable reconciliation bound.** `meaningful(...,1500)` accepts 1500 meaningful Unicode characters for `effects`, but `apply_plan` stores `canonical(record).decode()` using ASCII JSON escapes in a column constrained to 4000 characters. The independent receipt below measures the accepted evidence and actual SQLite model constraint; the resulting transaction rolls back. `verify-boundary-shapes` requires proof at the durable boundary, and the existing meaningful-Unicode constraint test does not cover the operator representation. A repair must reject oversize durable records during plan with a clear bounded diagnostic or preserve permitted text within the stored bound, then measure the actual operational apply.
- **P1 — signed quiescence hold window can expire during release mutations.** On the revised source with signed effects-context binding, actual PostgreSQL `apply_plan` accepted a 3-second `hold_until`, then a fixture `pg_sleep(4)` trigger on the ingestion observation update held execution beyond that window. It committed a release and audit and returned `status=applied` after the signed window had expired. This violates the required committing-transaction revalidation of quiescence evidence (`state-persistence-invariants` and the reviewed operational contract). The `--expiry` receipt below records the exact database clocks, committed rows, source hash, generator hash and readback. The owner must revalidate evidence after all mutations before committing, and the operational procedure must maintain host/scheduler/pooler fences until explicit post-commit restoration; a timestamp must never itself authorize automatic resumption.

## Judgment smells

No materially risky Fowler-baseline smell identified on the initial pass. Frozen whitespace duplication in model/migration/runtime is intentional to preserve standalone migration history and SQLite DDL, and is not raised as a style finding. The full database admission fence is conservative; feasibility and host/pooler assurance must be stated in the operational procedure, not inferred from an environment-variable name.

## Positive controls and limits

The apply mutation is committed in the transaction holding database admission, domain continuity, table and row locks; it resnapshots the retained claim/correlation/observations and revalidates evidence time after locking. An unsuccessful statement propagates through the transaction context and rolls back the audit/claim/dispatch/observation changes together. Original claim entry/return columns are not rewritten. Evidence trust policy is loaded separately at startup and fingerprinted; submitted evidence does not provide its own authority keys.

The independent controls here include synthetic signed evidence, an inert SQLite storage boundary, actual PostgreSQL release/rollback and a real separate adapter/CLI process. They establish only those named local behaviors. Production host quiescence/provider feasibility and hosted execution remain unexecuted here; broader migration/runtime acceptance is assessed from the separately identified author receipts. Several initial repository inventory commands encountered absent optional paths or unmatched shell globs; these were read-only setup diagnostics, not passing verification controls.

## Unsuccessful first PostgreSQL refusal control

The first `--postgres-refusal` run on CPython 3.13.9 / SQLAlchemy 2.0.46 failed fixture setup: the actual adapter returned 1 but created no observation, so `db.query(IngestionJob).one()` raised `sqlalchemy.exc.NoResultFound: No row was found when one was required`. No reconciliation acceptance was established. Its sibling database `batch9-reconciliation-standards-a46a` was dropped by the generator's `finally` path. Generator setup had installed the inert registry before the actual audits scope package registered itself; it now imports the real scope first, matching the established Batch 8 process fixture. The failed command was:

```text
env -i PATH=/usr/bin:/bin:/usr/local/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/Users/roger/.codex/worktrees/a46a/audit_app/backend DATABASE_URL=postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-standards-a46a ADMIN_ETL_DISPATCH_ENABLED=true /Users/roger/Documents/projects/audit_app/venv/bin/python batch9-reconciliation-evidence/standards_evidence_generator.py --postgres-refusal
```

Original failure output (exit 1), retained honestly:

```text
Traceback (most recent call last):
  standards_evidence_generator.py:265 in <module>: main()
  standards_evidence_generator.py:244 in main: postgres_refusal_control()
  standards_evidence_generator.py:214 in postgres_refusal_control: row = db.query(IngestionJob).one()
  sqlalchemy/orm/query.py:2808 in one: self._iter().one()
  sqlalchemy/engine/result.py:1827 in one: self._only_one_row(...)
  sqlalchemy/engine/result.py:772 in _only_one_row: raise exc.NoResultFound(...)
sqlalchemy.exc.NoResultFound: No row was found when one was required
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:17:04.831445+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "ffe2b20580b35206cfac2c8c4d03e3264222c97d49dbdcdb3543b03609dd9626",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "de1c648739fcd4c905d9e6d37238da66c5c1db9f3d5833ca0a1aba4a7afee0d4",
    "backend/seeding/reconcile_operator.py": "c73f64b5fb747264d64b40d862bda9483e722d3704454c1b1d493ef91647964b",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "/Users/roger/.codex/worktrees/a46a/audit_app/batch9-reconciliation-evidence/standards_evidence_generator.py"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
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
      "durable_record_characters": 9693,
      "constraint_limit": 4000,
      "storage_rejected": true,
      "diagnostic": "CHECK constraint failed: ck_seeding_claim_reconciliation",
      "remaining_fixture_rows": 0,
      "interpretation": "reproduced valid-evidence/storage-boundary defect"
    }
  ]
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:19:08.160514+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "7005483448e29f62d50504347362f5e599e9f870c334e7332d6ce5860cbbbb3c",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "b74505f28cd458a704edf3cb24a00d71fdd628cafd35bb606f437a9fa3727055",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--postgres-refusal"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
  },
  "controls": [
    {
      "control": "actual_separate_adapter_cli_terminal_refusal_snapshot",
      "database": "batch9-reconciliation-standards-a46a",
      "command": [
        "/Users/roger/Documents/projects/audit_app/venv/bin/python",
        "/Users/roger/.codex/worktrees/a46a/audit_app/batch9-reconciliation-evidence/standards_evidence_generator.py",
        "--adapter",
        "6322baf5-d88a-4a2c-b790-c4656a0cd0b1",
        "1d76b746-561c-4552-9eba-d0723fa9543f",
        "05b99073-7a43-48de-a151-232c6dfd9544"
      ],
      "environment": {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
        "DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-standards-a46a",
        "ADMIN_ETL_DISPATCH_ENABLED": "true"
      },
      "actual_process_exit_code": 1,
      "stdout": "{\"actual_adapter_returncode\": 1, \"handler\": \"inert and expected uncalled\"}\n",
      "stderr": "{\"asctime\": \"2026-10-09 14:19:08,043\", \"levelname\": \"ERROR\", \"name\": \"seeding\", \"message\": \"Domain ownership unavailable; no handler started\", \"domain\": \"audits\"}\n",
      "observation_shape": {
        "id": 1,
        "status": "FAILED",
        "metadata": {
          "ownership_refused": true,
          "dispatch_command_id": "6322baf5-d88a-4a2c-b790-c4656a0cd0b1",
          "dispatch_claim_token": "1d76b746-561c-4552-9eba-d0723fa9543f"
        },
        "owner_entered_at": null,
        "owner_returned_at": null,
        "owner_released_at": null
      },
      "reconciliation_snapshot_rejected": false,
      "diagnostic": "snapshot accepted",
      "interpretation": "fixed legitimate-refusal boundary"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:21:02.657861+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "006256f3ea062d15eca1da77decc843bbea07ab9995ecc774130d799fce9a37f",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "b74505f28cd458a704edf3cb24a00d71fdd628cafd35bb606f437a9fa3727055",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--expiry"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
  },
  "controls": [
    {
      "control": "attestation_expires_during_actual_slow_postgres_update",
      "database": "batch9-reconciliation-standards-expiry-a46a",
      "signed_hold_until": "2026-10-09T19:21:01.595136+00:00",
      "database_clock_after_apply": "2026-10-09T19:21:02.644711+00:00",
      "after_hold_window": true,
      "actual_result": {
        "status": "applied",
        "audit_id": 1,
        "record": {
          "version": 1,
          "who": "fixture-operator",
          "why": "Exercise independent boundary controls",
          "effects": "Synthetic SQLite only; no financial effects",
          "evidence_sha256": "98afe9b950b95d43c9dabd464d7d6cb47af04f0062405a20987d035f06bc77dc",
          "plan_sha256": "ce22b8ce9a3fff4d83ac18bd29f768e4f6978535c6fa21e3e8457154e431cbd9",
          "policy_sha256": "7c576f73fb4dafecaedbdb5b1d4e7a06b956e67e22c1de4cdb29d0128f90fe2a",
          "target": {
            "database": "batch9-reconciliation-standards-expiry-a46a",
            "maintenance_role": "postgres",
            "database_oid": 19007,
            "system_identifier": "7694746568233562146",
            "revision": "e583b9c9a001"
          },
          "selector": {
            "domain": "standards-inert",
            "claim_id": "8b73f40c-dcc5-4d2b-98fa-69135d5ef71a",
            "legacy_job_ids": []
          },
          "reconciled_at": "2026-10-09T19:20:58.624804+00:00"
        }
      },
      "claim_released": true,
      "durable_audit_count": 1,
      "interpretation": "unsafe expired attestation accepted"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:22:07.442645+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "d5ae01bfb9e7f9da4f888752c6c699b9d4aa6c2ce7b7e9bd4dedf5985068283d",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "5540a23bce38dc943a80bf649da93a448f14bc6dcab8cf856bfe913799bbfde9",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--expiry"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
  },
  "controls": [
    {
      "control": "attestation_expires_during_actual_slow_postgres_update",
      "database": "batch9-reconciliation-standards-expiry-a46a",
      "signed_hold_until": "2026-10-09T19:22:06.381115+00:00",
      "database_clock_after_apply": "2026-10-09T19:22:07.427720+00:00",
      "after_hold_window": true,
      "actual_result": {
        "status": "refused",
        "message": "Stale, uncertain or mismatched scope evidence"
      },
      "claim_released": false,
      "durable_audit_count": 0,
      "interpretation": "expired attestation rolled back"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:22:13.322469+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "d5ae01bfb9e7f9da4f888752c6c699b9d4aa6c2ce7b7e9bd4dedf5985068283d",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "5540a23bce38dc943a80bf649da93a448f14bc6dcab8cf856bfe913799bbfde9",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
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
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:22:35.048815+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "d5ae01bfb9e7f9da4f888752c6c699b9d4aa6c2ce7b7e9bd4dedf5985068283d",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "5540a23bce38dc943a80bf649da93a448f14bc6dcab8cf856bfe913799bbfde9",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/.codex/worktrees/a46a/audit_app/.batch9-min/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--expiry"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.12.15 (main, Oct  3 2026, 00:54:33) [Clang 22.1.3 ]",
    "sqlalchemy": "2.0.23",
    "platform": "macOS-27.0.1-arm64-arm-64bit"
  },
  "controls": [
    {
      "control": "attestation_expires_during_actual_slow_postgres_update",
      "database": "batch9-reconciliation-standards-expiry-a46a",
      "signed_hold_until": "2026-10-09T19:22:33.998819+00:00",
      "database_clock_after_apply": "2026-10-09T19:22:35.034680+00:00",
      "after_hold_window": true,
      "actual_result": {
        "status": "refused",
        "message": "Stale, uncertain or mismatched scope evidence"
      },
      "claim_released": false,
      "durable_audit_count": 0,
      "interpretation": "expired attestation rolled back"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:22:36.245181+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "d5ae01bfb9e7f9da4f888752c6c699b9d4aa6c2ce7b7e9bd4dedf5985068283d",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "5540a23bce38dc943a80bf649da93a448f14bc6dcab8cf856bfe913799bbfde9",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--postgres-refusal"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
  },
  "controls": [
    {
      "control": "actual_separate_adapter_cli_terminal_refusal_snapshot",
      "database": "batch9-reconciliation-standards-a46a",
      "command": [
        "/Users/roger/Documents/projects/audit_app/venv/bin/python",
        "/Users/roger/.codex/worktrees/a46a/audit_app/batch9-reconciliation-evidence/standards_evidence_generator.py",
        "--adapter",
        "71cf4167-2604-438e-86dd-48dff6d62b30",
        "783d22a5-cfb2-4fd7-a1fd-fcea6a2495f1",
        "93f2bb48-6077-435d-a3ad-8445890ac739"
      ],
      "environment": {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
        "DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-standards-a46a",
        "ADMIN_ETL_DISPATCH_ENABLED": "true"
      },
      "actual_process_exit_code": 1,
      "stdout": "{\"actual_adapter_returncode\": 1, \"handler\": \"inert and expected uncalled\"}\n",
      "stderr": "{\"asctime\": \"2026-10-09 14:22:36,120\", \"levelname\": \"ERROR\", \"name\": \"seeding\", \"message\": \"Domain ownership unavailable; no handler started\", \"domain\": \"audits\"}\n",
      "observation_shape": {
        "id": 1,
        "status": "FAILED",
        "metadata": {
          "ownership_refused": true,
          "dispatch_command_id": "71cf4167-2604-438e-86dd-48dff6d62b30",
          "dispatch_claim_token": "783d22a5-cfb2-4fd7-a1fd-fcea6a2495f1"
        },
        "owner_entered_at": null,
        "owner_returned_at": null,
        "owner_released_at": null
      },
      "reconciliation_snapshot_rejected": false,
      "diagnostic": "snapshot accepted",
      "interpretation": "fixed legitimate-refusal boundary"
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```

## Independent boundary receipt

```json
{
  "generated_at": "2026-10-09T19:28:34.400198+00:00",
  "generator": "batch9-reconciliation-evidence/standards_evidence_generator.py",
  "generator_sha256": "84776750c759bf9874ad7999103f59c7febe0e11fa5f48875e02522ee720444d",
  "source_sha256": {
    "backend/seeding/reconciliation.py": "4ccaf416c5d1180e24bf45a020b50b559289128836d9b33ab35aa26663607e1e",
    "backend/seeding/reconcile_operator.py": "b81d97af7c0961c31b107563c6a73018794dd55553ffd3e9de2670ec88343f09",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py": "e5d060174e2ae64a4ceb64048fe9c6ff86fdff8a10f8eeaccf3315f5f2864a94",
    "backend/models.py": "9b7317a9553d0f9c31da7b9e56306b115bcd1a8a61e074f1901dcef9cbe5a4d2",
    "batch9-reconciliation-evidence/operator-procedure.md": "fe1e022ce69da8da5a05f95f145e758eb1853eb8c49ea055f38d70d88b697d0e",
    "batch9-reconciliation-evidence/read_only_census.sql": "3bab1b6073c4e915d2cd12cf6ed52f649cae59ffea6f8739dd6d2e88a4e44f26",
    "batch9-reconciliation-evidence/writer-census.json": "08fa19a907ebbbe1679e7163c2fcc7c9ea33ef9b7321ac429577911109a9c0ea",
    "batch9-reconciliation-evidence/inventory_receipt.py": "00ae40d00fe59a7c10ec1de1d1260a89018dfe4e87039716db94a45b2e0f3721"
  },
  "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "head_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
  "command": [
    "/Users/roger/Documents/projects/audit_app/venv/bin/python",
    "batch9-reconciliation-evidence/standards_evidence_generator.py",
    "--procedure"
  ],
  "environment": {
    "PYTHONPATH": "/Users/roger/.codex/worktrees/a46a/audit_app/backend",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHON_DOTENV_DISABLED": "1"
  },
  "runtime": {
    "python": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]",
    "sqlalchemy": "2.0.46",
    "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O"
  },
  "controls": [
    {
      "control": "writer_census_provenance_readback",
      "source_count": 397,
      "source_mismatches": [],
      "generator_hash_matches": true,
      "registered_domain_count": 15,
      "candidate_anchors": 1218,
      "scope_limit": "repository source candidates; runtime host inventory/deployed configuration unverified"
    },
    {
      "control": "author_final_suite_receipt_readback",
      "receipt": "batch9-reconciliation-evidence/final-current.json",
      "receipt_sha256": "1363395c3affbbc10aa6e7cd8d32aa350cf63a7146ba41e7f474278fd261a1af",
      "runtime": "3.13.9 (main, Oct 14 2025, 13:52:31) [Clang 17.0.0 (clang-1700.3.19.1)]\nSQLAlchemy 2.0.46\n",
      "exit_code": 0,
      "reported_passes": 102,
      "execution_owner": "author; reviewer readback only",
      "command": [
        "/Users/roger/Documents/projects/audit_app/venv/bin/python",
        "-m",
        "pytest",
        "backend/tests/test_batch9_reconciliation.py",
        "backend/tests/test_batch9_reconciliation_constraints.py",
        "backend/tests/test_batch9_reconciliation_processes.py",
        "backend/tests/test_batch9_reconciliation_migration.py",
        "backend/tests/test_batch8_exclusion_sqlite.py",
        "-q",
        "--tb=short"
      ]
    },
    {
      "control": "author_final_suite_receipt_readback",
      "receipt": "batch9-reconciliation-evidence/final-minimum.json",
      "receipt_sha256": "ae3ec18bdc0cce40445d4561d98d35575dc00eecb2170ed48be4384a1fc7b7ca",
      "runtime": "3.12.15 (main, Oct  3 2026, 00:54:33) [Clang 22.1.3 ]\nSQLAlchemy 2.0.23\n",
      "exit_code": 0,
      "reported_passes": 102,
      "execution_owner": "author; reviewer readback only",
      "command": [
        ".batch9-min/bin/python",
        "-m",
        "pytest",
        "backend/tests/test_batch9_reconciliation.py",
        "backend/tests/test_batch9_reconciliation_constraints.py",
        "backend/tests/test_batch9_reconciliation_processes.py",
        "backend/tests/test_batch9_reconciliation_migration.py",
        "backend/tests/test_batch8_exclusion_sqlite.py",
        "-q",
        "--tb=short"
      ]
    }
  ],
  "failure": null,
  "verdict": "executed controls recorded"
}
```
