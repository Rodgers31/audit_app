# Existing GitHub connection qualification and bounded ingestion

This is a preparation contract, not a successful production receipt. The owner
requested one bounded refresh and nightly ingestion only after it passes.
Publishing/uploads remain off. No new login, grant, service, plan or paid review.

`ingestion-preflight.yml` purpose `github-writer-target` reads only the existing
DATABASE_URL and DATABASE_POOLER_URL secrets, one at a time. The URI must use canonical /postgres and exactly one authority separator, matching the actual application URL parser. A reviewed exact
commit must first be admitted through INGESTION_DATABASE_QUALIFICATION_SHA. Only
main and the fixed qualification-review branch are accepted. The legacy reader
inspection job retains its separate disabled admission; target qualification is
not the reader's broader source/worker/custody qualification.

The independent expected identity is project xznjxwrkbkahwtnbstbj, postgres/OID5,
cluster7626352619084395911, primary PostgreSQL17, revisiona756b20a0001. These
come from the accepted Supabase/operator observations, not from the secrets
under test. The tool refuses unrelated authorities and URI query overrides
before connecting. It forces verify-full TLS using normal system public roots
and the already accepted project CA (SHA256700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7).
No trust bypass, new project CA or application import is introduced.

Each connection runs BEGIN REPEATABLE READ READ ONLY, seven transaction-local
settings and four fixed catalog reads, each returning at most two rows. Statement
timeout3s, lock1s and idle-transaction5s apply. The outer process kills/reaps each
child after20s; there is no retry. Effective DSN verify-full is checked as well as encryption. Both rollback and close must complete before
success is returned. Only fixed diagnostics, database bytes and matching flags
reach stdout; driver messages/URLs/passwords are not logged. No artifacts or
cache upload. Database size is an observation, not billed-egress/Free acceptance.

## Ordered activation

1. Keep unrelated workflows and the seed workflow disabled. Record existing
   global/per-workflow settings and the old #599 run identities. If old runs
   cannot be cancelled, restrict allowed actions to the two immutable checkout
   and setup-python references used by this inspection. Do not permit the old
   verification workflow's moving tags during qualification. Verify policy
   readback before admitting the exact qualification SHA. No bot request.
2. Run the reviewed manual inspection once. Verify its final target_verified_read_only
   report for both existing secrets and a successful run conclusion. On failure
   disable Actions again, remove the admission variable, preserve sanitized logs
   and investigate the exact refusal; do not substitute a different credential.
3. Review/merge #794 and this workflow change through the usual independent
   review/comment process. Required-check bypass is a separate explicit owner
   decision after a normal merge refusal. Deploy the accepted backend; verify
   installed writer hash and publishing/upload/dispatch flags remain off.
4. Admit only the accepted main SHA through INGESTION_WRITE_APPROVED_SHA. The
   routine workflow now prepares the same credential-free public CA policy in each database job, forces explicit verify-full/root DBAPI arguments in both real engine constructors (overriding URI sslmode=require), qualifies that job's stored connection before database effects,
   requires exactly the already accepted Alembic head and does not run DDL.
   A new main SHA or schema head is refused until reviewed/admitted again.
5. After private receipt-store access/capacity/recovery readback, enable only the
   reviewed seed workflow. Run one explicit OpenData domain (its opt-in is needed),
   dry_run=false, run_bootstrap=false, run_validation=false. Broad county validation is deliberately excluded from this bounded source run. Perform bounded source-specific readback instead; do not label global validation passed. Observe exact native
   job/claim/source/extraction IDs, source hash, counters, durable closure and
   allowed row changes. The known workbook is224617 bytes/2125 numeric cells;
   preserve the existing object/receipt caps and source deadlines. Unknown
   effects, retained claims, schema/target drift, budget refusal or failed
   validation stop the next write; no automatic retry or force release.
6. Only after that passes leave the accepted schedule enabled. Standard public
   ubuntu-latest minutes are free; use existing storage/services and included
   limits. Inspect run summaries, source freshness/fallbacks, API revalidation,
   R2/storage and Supabase usage. Do not claim a Free-plan fit from one run.
   CRA/discovery remain off unless their own acceptance passes. Social flags
   remain off throughout; scheduled ingestion is a separate channel.

## Stop and rollback

Disable workflow236444319 and remove INGESTION_WRITE_APPROVED_SHA before another
writer is admitted. Cancel a not-yet-running manual dispatch; for an active seed,
use its bounded native stop/recovery procedure and retain uncertain claims rather
than clearing them. Do not roll back data by blindly deleting rows or restoring a
database over unrelated changes. Record the exact failed job and reconcile its
effects. Disable the repository again if unrelated Actions start. Removing the
manual qualification admission prevents another inspection dispatch.
