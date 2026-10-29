# Restricted worker current-source authority (#802)

The privileged committed reader establishes the meaning of native report and financial evidence. A new generated revision can bind a separate `worker_authority` witness to its exact current dependency set. This annotation belongs to the immutable revision evidence, outside `SourceObservation`; semantic and report release fingerprints are unchanged. Existing immutable drafts are not backfilled or edited.

The worker uses a Core connection and reads only the pinned, security-barrier `social_native_source_authority` view. Its five columns contain source kind, native domain, record ID, ingestion ID and a SHA-256 fingerprint. It receives no financial cells, source metadata, receipts or additional business-table grants. The owner-only snapshot view is not granted. No definer function, login, password, policy or model migration is introduced.

The locked view covers four report domains (national budget, revenue, audits, pending bills) and three financial domains (national budget, revenue, pending bills). The existing county digest view covers legacy county financial evidence. The witness includes the business identity, source/country and relevant entity/period, current report, exact job, referenced receipts and original retained-byte receipts. Newer successful live/partial jobs supersede the old witness; audit supersession remains scoped to its report series. Post-commit generation telemetry does not invalidate source authority.

Capture takes the native domain lock, locks the complete dependency set, revalidates its exact canonical meaning through fresh privileged identities, and confirms that the fingerprint is unchanged. Delivery uses the same native lock and performs a second READ COMMITTED read after any row-lock wait. A missing, malformed, foreign, changed or superseded witness requires source review. Direct native ORM checks on a Core connection return that typed hold. Pre-install schemas can still create drafts; those drafts remain held for worker delivery.

## Explicit operator installation

After separate approval for the new digest-only SELECT, run the reviewed release on the existing owner connection using a named environment reference:

```sh
python -m social.worker.role_admin --database-url-env APPROVED_OWNER_DSN --role audit_social_worker --install --native-authority
```

This transaction first verifies the existing restricted login and all its existing grants/policies/guards. It creates the two exact public-schema views, revokes PUBLIC, verifies their pinned definitions and ownership, grants SELECT on only the locked view to that login, then verifies the full contract again. A complete repeat is idempotent; drift, unexpected authority or an incomplete existing installation refuses and rolls back. The installer supports the public-schema base role profile only, and cannot combine the optional platform profile or verify mode. No credential value is accepted as a command argument or printed.

Verify afterward through the actual restricted login with the existing `--verify` mode. Keep publishing, media uploads, workers, supervisor and dispatch off. Installation alone is not provider acceptance or permission to publish. Prior drafts without a witness need a separately reviewed new revision; never rewrite their immutable evidence.

## Acceptance boundaries

Synthetic local PostgreSQL producer/reader/revision/restricted-role checks establish code behavior and SQL access. They do not establish a live provider grant, current production source qualification, token recovery, storage capacity, privacy ingress or authorization to launch workers. Production installation and read-only verification remain explicit rollout steps under #699.

## Pending-bills source rollout prerequisite (#800)

The existing manual seed workflow now offers `reacquire_pending_pdf=false` by default. Selecting true requires exactly `domain=pending_bills`, with bootstrap and the unrelated OAG repair unselected. Schedules and other domain selections refuse the option. The child seeding process receives PDF cache TTL zero; the shared parent environment is unchanged. That manual run skips restore/save of the ordinary GitHub PDF cache, so it starts without old partials and leaves the all-source cache bank intact. There is no new workflow or runner type and no timeout increase: CoB transfer remains 420 seconds within the existing 600-second domain limit.

Use this existing GitHub runner for the 53,561,130-byte CoB report, whose full parse was measured above the Render service's 512 MiB allocation. A current HTTP download is new acquisition evidence; never assign its time to old receipt 10970 or job 3497. First run the selected dry-run qualification. Operational jobs and immutable source-storage objects can still write during a dry run. Verify the exact reviewed report SHA-256, MD5, size, current publisher metadata, retained-byte readback, both distinct aging populations and terminal job result before any write rollout. If the dry run rolls its database receipt back, the write run must obtain its own genuine acquisition. Restore both acquisition flags on any failed gate, and preserve history; turning flags off does not revoke already-adopted source pointers.

This manual option supplies transport evidence, not automatic source acceptance. It does not change ordinary nightly caching, source selection, write-admission SHA, global/account publishing, uploads or worker controls. The public repository's standard runner and the existing Standard R2 allowance are used; verify current usage before dispatch and stop before exceeding included capacity. No additional resource or paid plan is part of the change.
