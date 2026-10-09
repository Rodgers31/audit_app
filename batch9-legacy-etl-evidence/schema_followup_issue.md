Found during #581's independent readiness review. Related #572 / draft #584; separate from #583's operator reconciliation and production facts. This is outside the legacy ETL file ownership, so shared native code is unchanged in this lane.

The shared native CLI assumes `uq_seeding_active_domain` exists but does not check it. On an owned temporary SQLite database with real ORM schema, retain an entered `audits` claim, drop that index, then call the actual `seeding.cli.run_seed_command` with an inert registry handler. It returns 0 and commits one effect while the original claim remains unreleased. A PostgreSQL continuity lock would exclude a live backend, but an abandoned retained claim must also block after its backend has closed; PostgreSQL reproduction remains an acceptance item.

Reproduction in the dependent legacy branch:

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONPATH=backend \
  .local-dev/current/bin/python batch9-legacy-etl-evidence/native_schema_control.py
```

Executed receipt: `batch9-legacy-etl-evidence/native-schema-defect-2.json`, generator SHA256 `5b92d7ad0f4536ea6d77e18e0e4c7caf01805ba9e653a17971b1985b4c4dbccc`, result `native_exit=0; effects=1; retained=1`. The control first imports the actual audits scope, then substitutes only its inert handler. No provider, production or financial data used. The initial receipt `native-schema-defect.json` is an examiner setup error (late domain registration), not this reproduction.

Impact: incomplete or drifted ownership schema can silently bypass durable retention after writer death. Normal migrated schema is protected; this does not claim a deployed index is missing. Legacy ETL now refuses missing-index storage, but native/dispatch readiness remains separately owned.

Acceptance:

- Validate the essential ownership schema before native/dispatch admission; missing table/columns/active-domain unique partial index must refuse visibly before any handler/effect.
- Execute missing-index retained-claim controls on owned PostgreSQL and SQLite, plus minimum/current SQLAlchemy. Preserve the existing claim and start zero work.
- Keep valid-schema behavior, atomic acknowledgement, dry-run and default-off dispatch semantics intact; no automatic expiry/reclaim or operator release.

Dedup: searched open AND closed issues with `"seeding_domain_claims"` (limit 500) and the broader ownership/exclusion inventory. Only #581 and #583 matched the exact schema term; neither tracks this admission defect. Exact search command/output is in `schema-issue-dedup.json`.
