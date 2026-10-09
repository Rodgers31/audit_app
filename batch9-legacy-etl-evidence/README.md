# Batch 9 legacy ETL evidence (#581)

Author delivery only; coordinator and production acceptance remain pending.
Base: #584 head `9e97ca3f1ca43f103a8655447a86d889456a218a`. Main was and remains
`672c5c011ce57dc41551f5fbc642bc4e69134c43` at the recorded final read.
The committed handoff is `docs/admin/implementation/BATCH_9_LEGACY_ETL_HANDOFF.md`.

## Final evidence

| Receipt / report | Meaning |
| --- | --- |
| `process-final-minimum.json` | 77 passed: 60 actual PostgreSQL process controls, 14 portable legacy session controls, 3 existing native SQLite regressions. Python 3.12.14 / SQLAlchemy 2.0.23. No failures/skips/xfails. |
| `process-final-current.json` | Same 77 passed on Python 3.13.9 / SQLAlchemy 2.0.46. No failures/skips/xfails. |
| `baseline-final-red.json`, `baseline-replay-execution.json` | Final unchanged process test/fixture bytes replayed against the exact six owned pinned-base files, with the new ownership module absent. Three expected defect failures; candidate bytes restored in finally. The outer replay exit 0 means the expected red occurred and restore succeeded. |
| `refusal-storage-red.json`, `refusal-storage-green-{current,minimum}.json` | Same immutable recording-fault probe: OperationalError became bounded DomainOwnershipError, zero effect and conflicting claim retained. |
| `critical-lint-final.json` | CI critical Python error set E9,F63,F7,F82 passes for every owned product/test file. |
| `migration-current-chain.json` | Actual fresh Alembic chain reaches e572b8c9a001 on separate owned PostgreSQL database; required partial unique index inspected. Database removed in finally. |
| `runtime-{current,minimum}.json` | Executed runtime/dependency identities. No primary installation. |
| `spec-final-recheck.md` | Independent Spec recheck, 4 controls passed, no blocker. Final receipts use `*-final-independent-green.json` and `refusal-storage-final-spec-independent.json`. |
| `standards-final-addendum.md`, `standards-final-replay-readback.json` | Independent Standards recheck: 6 final controls passed on both runtimes, no finding. Receipt names contain `final2`. |
| `behavior-review-recheck.md`, `behavior-review-recheck-acceptance.json` | Independent Behavior recheck: 8 final executions on both runtimes, zero failures/skips, current source and immutable generator hashes verified. |
| `writer-inventory.md`, `writer-callsite-search.json` | Supported entry/lifetime decisions and executed callsite search. |
| `native-schema-defect-2.json`, `schema-issue-dedup.json`, `followup-594.json` | Reproduced out-of-lane missing-index native admission defect, all-state dedup and created issue #594. Exit 0 here verifies the defect reproduction; it is not acceptance of that shared behavior. |
| `dependency-ref-final.json`, `main-ref-final.json`, `workflows-read-only.json` | Read-only GitHub identities/status. All five repository YAML workflows were disabled_manually; dynamic Copilot workflows active. No hosted CI claim or workflow change. |
| `delivery-provenance.json` | Reopens final receipts, compares source/generator hashes, compares baseline sources to git objects and unchanged measurement bytes, inventories artifacts with hashes. |

Every wrapper receipt records exact argv/cwd, interpreter, explicit selected
environment, source hashes, HEAD, generator hash, full combined command output,
exit and verdict. HEAD was still the dependency base while candidate files were
uncommitted; **source hashes identify the tested candidate**, and the handoff
names the subsequent implementation commit. Do not interpret that recorded HEAD
alone as the tested implementation. Immutable `run_receipt.py` SHA256 is
`519b548f3760f324c3a44fa2616a2e56ff4819d6fa9f5909a94e0d14868011bd`.
Reviewer generators record their own hashes, source start/end hashes and outputs;
the read-back assessments verify their final receipts. Historical generators
are retained as versioned snapshots. Raw child stdout/seed logs for original
red, final red, final minimum and final current are in `process-logs/`; a manifest
records original temporary paths and file hashes.

## Preserved failures and superseded runs

- `baseline-red.json` / `-2` lacked required inert SourceDocument fields.
  `baseline-red-3.json` had an examiner import namespace error. None is defect
  proof. `baseline-red-4.json` is the original valid three-failure reproduction;
  final red is an additional replay with final measurement bytes.
- `process-green-1.json` is intermediate and overlapped an implementation edit;
  it is not final source-stable acceptance. `process-green-2.json`,
  `process-current-r3.json`, `sessions-current.json` and
  `process-minimum-3.json` passed earlier candidates/subsets and are superseded.
- `process-minimum-1.json` failed global conftest's unrelated uvicorn import.
  `process-minimum-2.json` recorded 5 failures/68 passes after early native
  subprocesses lacked tenacity (plus one cleanup PermissionError); an interrupt
  was attempted. They are unsuccessful environment/control runs. Required
  dependencies were installed only in the owned minimum runtime. Final suites
  use `--confcutdir=backend/tests` to avoid global web-app/provider setup.
- `critical-lint-red.json` exposed pre-existing logger-before-definition in
  optional pipeline imports; logger initialization was moved earlier.
- Original independent findings, reds and setup errors remain in
  `spec-review.md`, `standards-review.md`, `behavior-review.md` and their named
  receipts. Their later rechecks supersede candidate bindings, not history.
  `standards-readback-source-drift.txt` honestly records a failed source binding
  before those controls were replayed against final bytes.
- `native-schema-defect.json` is a registry-order setup error, preserved with
  `native_schema_control_v1.py`. The corrected control imports the actual scope
  first; `native-schema-defect-2.json` is the valid reproduction.
- Two author inventory wrapper attempts referenced missing absolute gh/rg paths
  and stopped before writing receipts. Corrected commands are in the successful
  `schema-issue-dedup.json` / `writer-callsite-search.json`; no failed attempt is
  counted as a pass. `issue-dedup.json` is raw read-only issue inventory, not an
  executable test receipt.

Pytest warnings (ORM/logging deprecations, optional fuzzy matching acceleration;
minimum also lacks an asyncio plugin registering two config keys) remain visible
in raw output. Critical lint has zero errors. These local scoped checks are not
the repository's full deployment gate, frontend/web test suite or production
migration approval. No provider transport or production access was used.

One raw failed SQLAlchemy diagnostic contains trailing spaces in its emitted SQL.
The local evidence `.gitattributes` disables whitespace diagnosis for that exact
raw `.txt` file to preserve its original bytes. Product/test/document whitespace
checks remain active. The first delivery verifier failed while assuming every
independent producer used the author wrapper schema; `verify_delivery_v1.py` and
`delivery-provenance-setup-error.txt` preserve that examiner failure, and the
corrected verifier validates each producer's actual schema and generator.
