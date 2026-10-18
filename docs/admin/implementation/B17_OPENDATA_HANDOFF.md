# OpenData workbook implementation handoff (#621/#602)

The official KNBS workbook route is implemented for review on base `78c305abe3cfb5b3d3f0ed800275f2f7e7bfb303`, branch `codex/b17-opendata`. See [the source and persistence contract](B17_OPENDATA_WORKBOOK_CONTRACT.md). It retains the actual KNBS publisher, all source cells/footnotes, missing markers, raw numeric strings, provisional/revised/unspecified labels, edition differences and published reconciliation discrepancies. It writes a source-bound document/extraction only; public financial qualification remains held.

`SEED_OPENDATA_INGESTION_ENABLED` defaults false. Migration `e621b17a0001` follows `a705b15a0001` and requires a stopped worker. No production migration, deployment, grant change, provider operation, feature activation, hosted run or paid bot review was performed. No application dependency or service was added. Existing CRA/native ownership code remains unchanged; legacy reference scope now holds fifteen domain keys on one backend and releases its distinct receipts atomically, within pool2/nooverflow.

## Executed local validation

Counts overlap; they must not be added as a whole-suite total. Each successful cohort had stable source inventories and owned PostgreSQL17.11 cleanup. Current runtime is Python3.13.9/SQLAlchemy2.0.46. Minimum runtime is cached Python3.12.15/SQLAlchemy2.0.23, with optional C-extension parity qualified in its receipt.

| Cohort | Result | Qualification |
| --- | --- | --- |
| Current workbook, CRA, migration, bootstrap, head/registry and financial-context selection | 200 passed | One explicit baseline main.py case deselected and separately reproduced below |
| Current optimized workbook/head/registry/context and legacy backend death | 136 passed | Same explicit baseline hold; new OpenData CLI children inherit `-O` |
| Current legacy loader/session/scheduler, CRA/OpenData contention and pool limits | 91 passed | Cached declared schedule1.2.0 wheel in a separate task runtime; primary environments unchanged |
| Minimum workbook/native/dispatch/storage/migration/legacy/bootstrap | 110 normal +110 optimized passed | Read-only cached runtime/package overlay; no package upgrade |
| All six dispatch mappings: retained-owner recovery, rollback, correlation, suppressed/deferred release and backend loss | 169 normal +169 optimized passed | Explicit owned template; financial handlers forbidden; signed fixture authority is not live operator authority |

No successful cohort had failures, errors or skips. Independent Standards controls passed57 storage/parser cases and11 legacy-group cases per mode; independent Spec controls passed66 semantic/boundary cases,8 native/dispatch recovery cases and14 legacy-group cases per mode. Both axes separately accepted the final test/contract-only delta. Cached Flake8 E9/F63/F7/F82 and diff whitespace checks passed.

The initial dry-run provenance false-green and fifteenth-domain pool exhaustion were reproduced before repair, then verified by executable red/green controls. Old schema-head, backend-count and recorder/setup failures remain preserved as historical failures in the external evidence packet; they are not counted as final passes. In particular, the first full-mapping launch omitted its required owned URL and refused169 setups; the corrected explicit-template run executed all169 cases in both modes.

## Acceptance hold and next command

Issues #621/#602 remain open. The unchanged accepted-base `backend/main.py` fails its financial-context guard: expected AST `094e1f9bd9d4563599fdc817d67207e8a73c284ead660f7a03e9ad826e666182`, actual `b9a5f0cdcf9bed49b53fd8a94389b6d2b95af1ec1fe7e4630d165ff4f6cf9b0a`. Main source SHA256 is `71a3c6e91a873e74e1b1331f389be99fbb7d2da4e6579882bb4689e55bcf35c1`, identical to the base. [#742](https://github.com/Rodgers31/audit_app/issues/742) tracks substantive current-context review; earlier #591 is historical and completed. Main.py and its inventory entry were not refreshed to obtain green. This scoped draft is not whole-plan or production acceptance.

After the #742 review, run from `backend` using the project runtime:

```sh
PYTHON_DOTENV_DISABLED=1 DATABASE_URL=postgresql://inert@127.0.0.1:1/inert python -m pytest 'tests/test_batch9_financial_review_context.py::test_actual_reviewed_sources_and_raw_sites_are_accepted[backend/main.py]' -q
```

Then carry the reviewed tree through the parent integration acceptance; production activation remains separately gated by #583/#554. No migration or enablement command is authorized by this handoff.

Exact commands, per-case JUnit, source/helper/runtime/config hashes, independent reviews and Chrome source/settings captures are retained outside the checkout at `FULL_PLAN_COMPLETION_B17/opendata/workbook-implementation-20261018`. Finalization must append the draft head/tree, complete PR feedback census, prior packet verification and final resource readback. The final binder must record this handoff as the sole documentation addition after frozen tests. The dirty primary checkout was not used for source edits or commits.
