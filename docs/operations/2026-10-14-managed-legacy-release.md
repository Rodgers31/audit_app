# Managed PostgreSQL legacy-job repair

The retained strict reconciliation operator requires a superuser maintenance
backend. Supabase's customer `postgres` role is not a superuser. The separate
`backend/seeding/managed_legacy_release.py` compiler supports a reviewed managed
maintenance window without changing that operator or enabling runtime reclamation.

This tool marks the complete observed RUNNING legacy job population FAILED with
`execution_unverified`. It never infers successful execution from age or counters.
It preserves every existing job field except status, finish time and the appended
error/reconciliation metadata. Financial facts, prior audit rows and their genuine
transaction provenance remain unchanged.

Before repair, stop backend/native writers and hold GitHub, manual, schema/import,
external-effect and provider-queue custody. The policy records separately reviewed
artifact hashes for each fence. Shared table locks protect application rows; they
do not replace these operational fences or establish control over provider root
administration. Another ordinary reader is permitted. Prepared transactions,
competing writes, retained claims and a ready worker refuse the operation.

Take a consistent private backup and verify restoration in an isolated target.
For an empty legacy audit population, apply the accepted baseline migration
`e602b11a0001`, then the separate audit migration `a611b12a0001`, with runtime
writers still stopped. Verify the exact three job preimages across each migration.
Do not substitute `upgrade head` or create an audit row before capture is installed.
Populated unknown history needs a separate reviewed disposition; never invent
root transaction IDs or delete retained history to obtain admission.

The compiler admits only the exact capture and append-only audit triggers, canonical
validated constraints and sidecar column shapes. Storage must have the matching
database/system/timeline identity and remain uncertified. The audit INSERT uses
the accepted database capture trigger; the compiler never inserts fabricated
provenance. It checks exactly one new audit and same-root sidecar, unchanged prior
rows and storage, and a complete before/after census of other public tables.

Supply the complete current catalog, table row/hash census, full RUNNING job
preimages, database/OID/system/role/revision target, actor, reason, effect review,
six held-fence receipts and a UTC observation/hold window of at most five minutes.
The trusted `AUDIT_MANAGED_RELEASE_POLICY_SHA256` environment value must match the
independently reviewed canonical policy-object digest. It is an operator
checkpoint, not proof that an arbitrary newly hashed policy or fence is true.
From the backend directory, call `compile_sql(policy)` and execute the returned
entire guarded transaction. No automatic database access or activation occurs
during compilation. Reviewed text remains literal, including template markers,
quotes, backslashes and dollar delimiters.

After COMMIT, use a separate fresh read-only transaction to verify the three job
deltas, operation digest, audit/capture linkage and preserved facts. An ambiguous
response requires inspection before any retry. Sequence allocation can advance
after rollback; atomicity applies to committed rows and facts.

Certification, a separate restricted audit reader, external incarnation/bookmark
authority, backend deployment and administrator/worker acceptance remain distinct
steps. Preserve audit history/schema on application rollback after the first
captured row. Keep dispatch off until the deployed configuration and stop path
are verified. A bounded worker check can use the existing service instance's
normal shell; do not create a separately billed worker, ephemeral shell or one-off
job under a no-new-cost release.

Native regressions live in `backend/tests/test_managed_legacy_release.py`. They
require an explicit disposable loopback database named `codex_managed_release`
on a non-default port and run the actual accepted audit migration and emitted SQL
as a non-superuser. No production credentials or endpoints are used by these tests.
