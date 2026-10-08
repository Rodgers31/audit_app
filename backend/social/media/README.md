# Private media maintenance

The separate bounded entrypoint is `python -m social.media.maintenance
--database-url <explicit PostgreSQL DSN> --once`. It reports compact ledger and
backlog counts by default. `--allow-cleanup --limit 20` explicitly permits one
bounded cleanup batch. Importing the module starts no process or scheduler;
there is no API lifespan hook, recurring job or implicit application DSN.

Storage remains disabled by default. The existing explicit media configuration
and separately authorized bucket/host acceptance are still required. The runner
does not provision storage or provide write-settlement evidence.

Browser PUT grants can be renewed only inside the original upload TTL window.
Every signing attempt first commits an unknown durable grant epoch. The signed
expiration is parsed from the signature and persisted under version/epoch fences
before the URL can return. Orphan expiry is a separate deadline. A grant may be
used more than once, and an admitted request may complete after signed expiry.
An age timestamp, HEAD, DELETE or database lease expiry cannot prove write
quiescence.

`MediaService.reconcile` is an internal operator port. It accepts a strict
`ReconcileUpload` with expected upload/grant/finalization versions and an opaque
receipt identity/hash. It freezes renewal, verifies outside SQL locks, and
rechecks current versions, leases, state and all historical references before
accepting evidence. A trusted `WriteQuiescenceVerifier` must affirm that **all**
admitted browser and server writes for those epochs have stopped or are
irrevocably fenced. It must validate the receipt through an independently
reviewed operational evidence mechanism. The production default verifier is
unsupported; there is no browser Boolean, timestamp or object-metadata shortcut.

Confirmed reconciliation can abandon an unreferenced nonready upload, or settle
a ready asset's quarantine hazard. It releases no quota by itself. Cleanup
requires settled browser and server writes, locks the global budget, uploader
budget and asset, then rechecks eligibility. Only confirmed single-attempt R2
DELETE responses (`HTTPStatusCode=204`, `RetryAttempts=0`) permit ledger release.
Failures or process crashes retain reservations until a fenced cleanup retry.
The explicit `pending_released` marker prevents command-version changes from
releasing pending capacity twice. New ready/failed uploads retain pending
capacity while browser writes remain unknown.

Ready originals, immutable ETag/version/checksum evidence, audit records and
historical revision references are retained. Automatic original retention or
deletion is deferred. Revision insertion and maintenance share the asset row
lock; a nonready row with historical references is protected. Cleanup of a ready
asset removes only its quarantine copy.

Backlog counts include already-released legacy rows with unknown historical
grants. `reserved_bytes` and `pending_uploads` are the actual ledger, so they do
not estimate the storage deficit those legacy hazards could have caused.
An unreleased ready row with a historical `quarantine_cleaned` marker can be
reconciled when writes remain unknown or pending capacity remains held. The
marker and ledger remain unchanged until trusted scoped verification succeeds.
That confirmation resets the quarantine marker and requires a fresh confirmed
DELETE; an old DELETE cannot exclude a subsequently completed browser PUT.
Ready cleanup releases only reserved bytes above the original's declared size,
so a historical one-copy reservation is never decremented again. Pending
capacity is released once after that fresh acknowledgement.

Fully released legacy reservations remain an inventory/backlog acceptance
boundary; the runtime cannot reconstruct their missing accounting or establish
write quiescence from historical cleanup. No backfill fabricates settlement.
Enabling storage requires a separate inventory and reconciliation decision;
never clear uncertainty to admit another upload. The root-owned migration
backfills pending markers using `version > 1 OR reservation_released = 1`;
archived version-one rows may represent failed deletes and still hold capacity.

Tests use explicit fake storage and deliberately injected affirmative verifier
evidence. They establish code behavior, PostgreSQL fencing and crash recovery;
they do not establish live R2/CORS behavior or production write-drain evidence.
Issue #490 retains those operational acceptance gates.

The offline declaration reviewer is `python -m scripts.social_media_acceptance`.
It validates a bounded packet against an independently supplied social scope and
explicit review time. Review readiness authenticates no receipt and authorizes
no storage, maintenance or publishing; all reports keep write-quiescence and
production acceptance false/not run. The exact input/gate contract and remaining
live evidence are in [MEDIA_OPERATIONAL_ACCEPTANCE.md](../../../docs/social-publishing/implementation/MEDIA_OPERATIONAL_ACCEPTANCE.md).

Storage contract references: [R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/),
[S3 DeleteObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObject.html),
[Boto3 retries](https://docs.aws.amazon.com/boto3/latest/guide/retries.html).
