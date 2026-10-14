# Durable audit release preparation

The separate audit target is `a611b12a0001`, descending directly from baseline
`e602b11a0001`. Accepted starting source is
`c8970e3953717fc0f0ca3a54e22f7e3e509eec0f`, tree
`1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8`. Review round 2 strengthens the
additive migration's effective public-role REFERENCES postcondition; its
revision, ancestry, DDL, data, triggers and uncertified startup are unchanged.
Never substitute `upgrade head` for either independently reviewed release step.
Lane D's preparation contract V3 is at source
`9cb9cfc37d7c8881e857892171eb38e8bac4ca62`; its baseline target excludes audit.
The coordinator must refresh and verify both final published contracts before
any combined rehearsal or production decision. This runbook grants no execution
or certification authority. #611, #583, #554 and #545 retain their production
criteria.

## Admission and custody

| Population or operation | Supported disposition |
| --- | --- |
| Empty legacy database migrated from the reviewed baseline | Fresh identity starts uncertified. Under separately witnessed custody and complete role/writer acceptance, empty history may become eligible for certification. |
| New committed ORM/Core/raw audit INSERT under continuously retained triggers | Capture stores the root `pg_current_xact_id()` atomically with the audit row; rolled-back root/savepoint rows have no committed provenance. |
| Populated pre-trigger legacy rows, absent sidecar, incompatible incarnation or unknown root | Entire audit population stays unavailable, including filters that hide unknown rows. Never infer provenance from `xmin`, ID order, timestamps or migration time. |
| Savepoints and more than 64 subtransactions | Store the root xid8, never the child xid. Native SQL controls verify the boundary separately from a natural billion-transaction rollover. |
| VACUUM FREEZE / VACUUM FULL table rewrite | Stored xid8 provenance survives; admission still checks identity, capture, immutable triggers, constraints, roles and external custody. |
| UPDATE / DELETE / TRUNCATE retention | Unsupported; append-only triggers refuse. No retention or pagination expiry permits deleting history. |
| Logical restore into a new database / clone / promotion | Revoke external incarnation/key authority before service startup. Copied certified state is insufficient; changed database/system/timeline refuses. No automatic recertification. |
| Restore/import into the same database, byte-identical physical clone, privileged forged provenance or deleted history | Catalog identity/completeness cannot establish continuity. These remain outside supported custody. Fence all privileged actors, revoke external authority, and require a new reviewed recovery design. |
| Prepared transactions, recovery, unsafe role drift or partial schema | Unavailable. Preserve data and the actual refusal. |

The [PostgreSQL xid8/snapshot contract](https://www.postgresql.org/docs/17/functions-info.html)
requires a root xid for `pg_visible_in_snapshot`; subtransaction IDs do not supply
that contract. Owned fixture epoch reset is a scoped SQL control, never proof of
historical or production custody. A storage UUID copied with a backup does not
prove continuous capture. Custody includes all owner/superuser/replication/import
and restore channels, external incarnation and bookmark-key holders, scheduler,
API, manual writer and provider maintenance/restart paths.

## Concrete staged release and abort

1. Freeze the reviewed application source, exact revision file hash and both
   lane contracts. Independently verify source/tree, migration ancestry, installed
   Python/ORM/PostgreSQL/image, database endpoint/system ID/OID/timeline and every
   credential target. Fresh authenticated provider and database readbacks are
   prerequisites; historical metadata and local receipts are not production proof.
2. Complete Lane D's independently reviewed baseline release to exactly
   `e602b11a0001`. Its production fences, direct/retained operator backend,
   complete writer/restart/background admission census, effects reconciliation
   and backup acceptance must pass. Audit is not consumed by that baseline step.
3. Hold the dedicated worker stopped and fence every audit writer and privileged
   schema/import/restore channel. Revoke old external audit authority. Verify
   actual ready-worker rows, other active/idle sessions and prepared transactions
   under the reviewed maintenance procedure; an instantaneous idle census does
   not fence reconnection. Preserve root transactions in progress rather than
   guessing their outcome. No author phase executes these production actions.
4. Capture an encrypted, custody-bound database/roles/ACL/RLS backup and the exact
   pre-migration revision/counts. Independently preserve external-effect custody
   where relevant. Test restoration in an owned isolated target before release.
   A dump alone omits physical WAL/PITR and external object bytes. Record backup
   bytes/hash/tool/source/role and restore identities/outcomes. Copies retain
   unavailable audit authority; restored data must not be silently certified.
5. Apply **only** `alembic upgrade a611b12a0001` through the reviewed operator
   connection. The revision uses transactional DDL, 2-second lock timeout and
   30-second statement timeout. It refuses ready workers, partial/preexisting
   audit objects, unsafe groups/memberships, recovery, malformed identity and
   nonpositive IDs. Never stamp over a refusal, force a reset, alter the deadline,
   truncate history or invent legacy provenance. Read back actual applied revision,
   three table schemas, validated constraints, exact ALWAYS functions/triggers,
   policy/column/sequence ACLs, group flags and private effective principals.
   The connected reader must have exactly the direct `audit_log_reader` parent
   and no administrative membership. Both audit groups need effective schema
   USAGE without CREATE. Public `anon`/`authenticated` roles must have no table
   or column REFERENCES authority, including inherited grants. Already-applied
   migrations do not rerun strengthened postconditions; runtime admission still
   revalidates the observed role and privilege contract on every request.
6. Inventory legacy history without RLS hiding rows. Populated unknown history
   prevents admission; retain unavailable behavior and request a separate reviewed
   custody/legacy solution. Empty or continuously captured history alone does not
   authorize certification: independently witness every writer and privileged
   channel, actual source/database continuity and external authority custody.
7. Review the concrete certificate decision separately. Fresh `certified=false`
   and absent external incarnation/key must produce private sanitized 503. Only
   the coordinator's separately authorized operation may certify an eligible
   population and distribute a fresh incarnation plus a 32-byte bookmark key to
   the isolated reader. Use `ADMIN_AUDIT_DATABASE_URL` with the validated private
   reader, REPEATABLE READ, private/no-store responses and administrator auth.
8. Execute authenticated deployed API/UI acceptance: administrator vs other user,
   lower-ID late commit, stable transferred pages, empty filters, actor/scope/time/
   signature refusal, 15-minute expiry, no secret payload, unavailable and refresh
   states. Match every actual deployed writer to the source census below and verify
   atomic row/provenance, transaction ownership and failure acknowledgements. Reopen
   writers only under a separately reviewed staged release, then fresh readbacks.

Abort on any unknown/refused/incomplete step. Keep writers fenced, external audit
custody revoked, audit service unavailable, and retain raw error/backup/source and
actual transaction state. Transactional migration failure should leave baseline
revision and data intact; read back rather than infer rollback after ambiguous
commit. Do not retry uncertain writes or migration automatically.

An empty **uncertified** audit can use the reviewed downgrade to
`e602b11a0001`; it preserves private RLS/groups. Populated or certified storage
refuses downgrade. Application rollback must keep audit unavailable and preserve
append-only rows/sidecar. Never deploy the old xmin reader as recovery for a
post-epoch-zero population. Restore/PITR/promotion changes require new external
custody and a separately reviewed provenance/compatibility decision.

## Actual source writer census

| Source entry | Transaction and release obligation |
| --- | --- |
| `backend/utils/audit.py::record_admin_action` | Independent short session commits its audit even if the caller rolls back. Fixed error on missing/uncertain audit; do not infer underlying action rollback or retry. |
| `backend/admin_users_provider.py::record_admin_action` | Independent session returns explicit persistence boolean after provider acceptance. Provider effects and uncertain audit acknowledgement remain distinct. |
| `backend/admin_etl_dispatch.py::accept` | Audit INSERT, command and FK share the acceptance transaction. No command means no accepted worker execution; preserve UUID replay/fencing/default-off semantics. |
| `backend/seeding/reconciliation.py::apply_plan` | Core INSERT and exact-effect release share the retained sole-session backend/locks. Required stored values and deferred triggers must pass before commit; uncertain release remains fenced. |
| Raw SQL, SQLAlchemy ORM/Core and subtransactions | Existing ALWAYS capture is the database choke point; only the restricted writer's seven input columns are writable. Owner paths require external custody. |

This whole-backend source census does not discover external/deployed writers or
prove every caller completed its provider/domain effect. Runtime catalogue
admission proves the observed population under one snapshot, not future immunity
to privileged edits. Release requires both source execution evidence and the
separate independently trusted operational census. Canonical session-owned empty
templates, original writer behavior, append-only history and baseline scope remain
unchanged.
