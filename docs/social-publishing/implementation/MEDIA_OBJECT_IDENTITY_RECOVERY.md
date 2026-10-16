# Media object identity recovery boundary

This slice of #490/#488 rejects malformed stored upload identities before a
mutation can authorize, inspect, create or delete an object. The frozen source
baseline is `3f3b1f1981b93c3317e204defbd235121c1df084` (PR679), including
PR675 retained fences and PR676 metadata request limits.

## Confirmed defect and scope

Initiation allocates `quarantine/{uploader UUID}/{asset UUID}/source` and
`ready/{asset UUID}/original`. Before this change, ordinary recovery and cleanup
used stored keys without checking that allocation. A legacy or damaged upload
row could point its quarantine key at another asset's ready original. The
baseline inert regression returned one cleaned orphan and deleted that original.
No production row or object was inspected to reproduce this defect; the fixture
is synthetic, not evidence of damaged production history.

`MediaService._rows` now checks both exact keys and the asset/upload identity
under the existing row locks. A mismatch raises private, nonretryable
`MEDIA_OBJECT_IDENTITY_MISMATCH`; the transaction rolls back and capacity remains
held. No key is normalized, repaired, reallocated or inferred from object
existence. Cleanup and backlog use the same exact allocation in SQL **before**
the candidate limit, then cleanup rechecks locked rows. A malformed oldest row
cannot consume every batch and hide later eligible cleanup.

The read-only reconciliation inventory reports `OBJECT_IDENTITY_MISMATCH` on the
specific upload. It exposes no object keys and never calls storage. The reason
suppresses cleanup-candidate classification while preserving every existing
write-proof, retained-fence, lease, reference and ledger reason. Inventory remains
a database observation; all write-quiescence, quota-release and ready-deletion
authority fields stay false. Operators must inspect a mismatch separately; this
change supplies no repair or deletion command.

## Mutation paths checked

| Path | Coverage |
|---|---|
| New initiation | Constructs exact keys; checks the persisted row before returning a signed authorization |
| Same-intent grant replay | `_rows` rejects damage before a new signing attempt/epoch change |
| Completion / same-command replay | `_rows` before object I/O, finalization fencing and ready commit |
| Explicit unknown retained recovery | `_rows` at scope acquisition, completion and retained verification; existing retained scope checks remain |
| Write-quiescence reconciliation | `_rows` before renewal freeze and after verifier I/O; no capacity released by reconciliation |
| Bounded cleanup | Exact SQL predicate before LIMIT, then `_rows` under locks before object I/O and ledger commit |
| Read-only inventory | Emits mismatch reason without interpreting it as cleanup permission |
| Library and preview | Library remains observational; preview checks the allocated asset/upload identity before HEAD/signing, then verifies immutable object metadata; neither releases capacity |

There are no shared-model, worker, migration, role, route or feature-flag changes.
This is an application guard for service mutations, not a new database constraint
or authority for out-of-band SQL writers. Existing direct/manual storage or SQL
operations still require their own approved operational controls.

## Retention and operational gates

- Native media, uploads, retained writes and publishing remain OFF. No R2 calls,
  bucket mutation, credentials, provider dispatch, paid review or hosted Actions
  are part of local validation.
- Unknown puts retain their durable epochs, pending capacity and two-copy byte
  reservations. Lease expiry, age and HEAD do not establish write quiescence.
  Ordinary completion still refuses blind retry after ambiguous finalization.
- Retained markers continue to forbid cleanup and hold both immutable copies and
  all reserved bytes. Repeated retained recovery uses the existing scope fences.
- Eligible settled nonready cleanup may delete only the exact allocated orphan
  pair. Ready cleanup may delete only its quarantine copy, never its original.
  Ambiguous delete acknowledgements and crashes retain reservations for explicit
  fenced retry; no completed deletion is inferred.
- Retention policy and ready-original deletion authority remain unapproved.
  Historical references, ready originals, checksum/ETag/version evidence and
  audit/provenance records are preserved. Age alone grants no deletion authority.
- Privacy callbacks remain `pending_review` with `deletion_completed: false`.
  This patch performs no privacy deletion and makes no completed-deletion claim.

Separate production acceptance requires an authorized deployment, fresh bounded
read-only inventory, investigation of any malformed identity, actual private
storage/CORS/host and immutable-write receipts, backup/retention custody, reviewed
write-drain evidence and maintenance composition. Actual retained inert
acceptance objects must remain untouched. A schema/reference locking contract
and an explicit retention decision are prerequisites for any future ready-byte
deletion. See [the existing retained recovery runbook](NATIVE_RUNTIME_AND_RETAINED_RECOVERY.md)
and [media integration acceptance](MEDIA_INTEGRATION_ACCEPTANCE.md).

Rollback stops the new application code while preserving all rows, retained
markers, objects and reservations. It restores the old application's missing
identity guard; keep media and maintenance disabled until this protection or an
approved equivalent is present. No schema downgrade or accounting adjustment is
required or authorized.

## Local validation and review receipts

Validation used Python 3.13.9, SQLAlchemy 2.0.51, Pydantic 2.13.4 and owned
PostgreSQL 17 containers from the already cached image. All object operations
were synthetic. Test fixtures' existing strict loopback guards were preserved;
worker/domain schemas used port 62124, and read-only operator schemas port 62249.

| Executed cohort | Result |
|---|---|
| Final regression files replayed on frozen product source in a separate managed baseline checkout | 19 failed, 4 passed; failures demonstrate redirected cleanup, unguarded commands, false candidate verdicts, stale selection and malformed migrated history |
| Same final files within candidate media cohort | All pass |
| `python -m pytest -q -rs backend/tests/social/test_media_*.py backend/tests/social/test_native_media_ownership.py` with all three local DSNs explicitly assigned | 839 passed, zero skips |
| `python -O -m pytest -q` over object-identity, PG identity, retained-recovery and request-limit files | 54 passed, zero skips; normal pytest optimized-mode warning disclosed |
| Critical flake8 (`E9,F63,F7,F82`) on changed Python files; `git diff --check` | Passed |

Earlier setup attempts are not acceptance: one invocation had an incorrect test
creation path, the initial broader run had 809 passes/21 unassigned-database
skips, and the first fully assigned run had 831 passes/two fixture conflicts.
The final assigned run resolves those skips and conflicts. The migration
fixture's actor-less quarantine key was never the allocator's format:
`git show 1549653:backend/social/media/service.py` and `5319393` both contain the
uploader UUID. The corrected canonical cases preserve all old settlement,
ledger and fresh-delete assertions. New malformed cases retain the old key
shape and assert refusal and unchanged capacity.

The full media cohort executes existing signer-crash/durable-marker cases,
pre/post-finalize crashes, confirmed/rejected/ambiguous puts and deletes,
metadata/byte mismatches, timeouts, repeated recovery, retained reservations,
PostgreSQL row races/migration rollback guards and strict payload limits.
These are local behavior receipts, not live storage acknowledgements.

Two independent executable reviews found no blocking issue. The spec review
ran 76 direct hostile predicates, 34 SQL/Python key comparisons and 96 command
attacks per database, plus the 17-test identity cohort. The standards review ran
12 independent PostgreSQL/durability probes and a 48-test existing cohort. It
also independently substantiated and executed all four canonical/malformed
migration cases. Source fingerprints matched the final product files.

One spec observation is valid and nonblocking: manually storing uppercase raw
UUID text in SQLite can make ORM identity pass while SQL cleanup stays held.
Normal ORM SQLite storage and production PostgreSQL UUID storage are canonical;
PostgreSQL agreement passed the probe. The primary agent reproduced the safe
hold and no object I/O/capacity release. Raw noncanonical SQLite representation
support is deferred; no production or unsafe-success claim follows from it.

Full logs, independent probe sources/reports, source hashes, exact commands and
final PR/head are recorded in the coordinator's batch-14 media evidence lane.
No paid or remote reviewer was requested. Draft review and coordinator integration
remain separate from production acceptance and release authority.


## Coordinator preview follow-up (#687)

Copilot's preview finding was half-right: the exact same-provider/bucket key cannot be shared by two live asset rows because the database has a unique constraint. A malformed row can still reference an unallocated retained ready object with identical bytes and metadata, and the old preview signed that key. Preview now refuses a missing upload or mismatched ready/quarantine allocation before any storage call. It retains metadata/ETag verification for valid rows.

Three inert cases (unallocated equal-content object, missing upload, wrong quarantine key) were observed failing on the original PR source and passing with the guard. The final object-identity/service selection passes32 cases in normal and optimized Python; independent executable spec and standards probes also pass. These are synthetic corruption controls, not evidence of a live unauthorized preview or storage operation. Parent #490/#488 and production activation gates remain open.
