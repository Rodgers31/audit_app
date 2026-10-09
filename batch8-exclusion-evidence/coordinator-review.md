# PR #584 coordinator review repair

Fixed author source: `4f1e1ea767544982c774c657c9a2e68297dd92f5`.
Review baseline: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`.
This report records local code review; it does not satisfy the unexecuted
pre-merge/activation gates in #583 or authorize migration or activation.

| Copilot thread | Classification and result |
|---|---|
| `4232924736` | **Valid.** JSON string `"true"` was accepted as a boolean refusal by PostgreSQL text extraction. `finish()` now requires JSON type `boolean` and text value `true`. Missing, null, false, numeric and string values retain the uncertain claim. The actual CLI's correlated boolean refusal remains a valid positive control. |
| `4232924837` | **Re-litigating recorded policy.** `register_worker()` deliberately retains every old running claim on restart, including never-entered claims. Replacement-generation fencing does not authorize automatic reconciliation. The regression registers a new generation, invokes the actual old-generation adapter, and proves no handler entry/effect and retained ownership; native and subsequent worker acquisition remain refused. No restart release path was added. |
| `4232924933` | **Valid.** Any string previously exempted a RUNNING observation. The shared guard now parses UUIDs and requires an unreleased claim for the observation's domain. Empty/garbage tags and absent, released or other-domain claims remain blocking in both native CLI and worker entry. A valid active claim is still enforced by the existing unique-domain acquisition boundary. |
| `4232924996` | **Half-right: confirmed continuity-fencing defect; concurrent handler execution was not established.** The actual CLI acknowledges after the synchronous handler/session returns, but a terminated lock connection could still be followed by a successful release on another connection. Acknowledgement now uses a savepoint on the existing lock transaction and commits that same outer transaction. Rejected observations roll back only their savepoint; loss of that backend before commit rolls back the acknowledgement and retains ownership. |

## Executed evidence

Raw commands, outputs, source SHA-256 identities, fixture normalization and the
replay runner are retained in the coordinator's `BATCH_8_REVIEW/exclusion-coordinator/`
artifact directory. The runner copies backend source into an owned runtime and
normalizes only existing fixture literals from port 55485 to the coordinator's
owned port 55486; product source is unchanged in that verification copy.

| Run | Actual result |
|---|---|
| `red-harness-error.txt` | Initial copy excluded the real `cache` package; import failure, not defect evidence. Preserved and corrected. |
| `red.txt` | **9 failed, 13 passed**, exit 1, against unrepaired author code with coordinator regressions. This includes five unresolved RUNNING tags, string refusal, both forced connection-loss timings and the original separate commit-backend identity. |
| `green.txt` | **22 passed**, exit 0, initial targeted repairs. |
| `impacted.txt` | **195 passed, 2 failed**, exit 1. One new positive-control harness targeted a locally imported name incorrectly; the other exposed rollback ending the original lock after a rejected observation under the first `control_fully` approach. Both were corrected; this superseded run is retained. |
| `acknowledgement-green.txt` | **57 passed**, exit 0, scope/migration/coordinator regressions on the final savepoint/outer-commit approach. |
| `final-etl.txt` | **197 passed**, zero failures/skips/xfails, exit 0. All Batch 7 ETL PostgreSQL/process/migration/review/adversarial suites and Batch 8 scope/SQLite/migration/native-process/coordinator suites. |
| `acknowledgement-minimum.txt` | **4/4 actual PostgreSQL controls passed** on CPython 3.12.14 + supported SQLAlchemy 2.0.23: normal same-backend commit; backend loss after continuity; backend loss immediately before commit; rejected observation followed by a valid acknowledgement. |
| Changed-scope critical lint | Flake8 `E9,F63,F7,F82` passed for both changed product modules and the three changed regression modules, using the coordinator helper/producer lane's read-only lint installation. |

Current suite runtime: CPython 3.13.9 + SQLAlchemy 2.0.46, macOS arm64;
owned PostgreSQL 16.15 on aarch64 Alpine, UTC, idle-transaction timeout 0.
The minimum-version probe reused the prior read-only SQLAlchemy 2.0.23 install
with an owned psycopg2-binary 2.9.11 CPython 3.12 target. No shared environment
was installed into. SQLAlchemy 2.0.23 cannot import under CPython 3.13 due its
pre-existing `TypingOnly` compatibility failure; the supported probe used 3.12.

The PostgreSQL fault controls terminate only the current fixture execution's
backend. The claim is then re-read from a fresh session and the actual native
CLI is refused while it remains retained. Normal completion permits another run.
All `seed.yml` invocations of `seeding.cli` and native CLI domain runs use the
same `enter_domain` guard; worker
acquisition uses `unclaimed_running`; every acknowledgement uses the corrected
shared transaction seam. Financial handlers/parsers/writers are unchanged.

All process tests stopped their owned workers/children. The owned coordinator
database remains available solely for the root coordinator's subsequent
serialized integration checks and cleanup. Production census, real pooler
behavior and all external writer/quiescence gates remain **unexecuted** (#583).
Existing uncovered-writer issues #581/#582 remain unchanged. No new issue,
GitHub reply, push or commit was made by this repair subtask.
