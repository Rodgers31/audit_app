# Owned media write quiescence

This is a default-off recovery protocol for newly allocated uploads whose whole
application write history is recorded from allocation. It preserves the selected
conditional-create permanent-fence protocol. It supplies no historical backfill
or generic authority over R2, provider, browser, backup or off-system writers.

`SOCIAL_MEDIA_OWNED_QUIESCENCE_ENABLED=false` is the shipped default. Deployment,
effective roles, credential custody, exclusive application namespace/writers,
storage contract and legal retention acceptance require separate human authority.
Configuring a flag does not establish those external facts. HTTP upload enablement
and native worker read admission remain separate and off. No live acceptance is
claimed by the controlled fixtures.

The supported positive is an allocation whose local R2 signing attempts all
durably finished without returning a bearer. The concrete signer makes no R2
request. An issued bearer is reusable and cannot be drained by this client.
Every admitted server finalization must also have its real synchronous adapter
completion persisted. Missing/partial history, process death, caller cancellation,
remote timeout, lost acknowledgement, positive HEAD, elapsed time and lease expiry
never count as completion. Unknown/issued/off-system writers remain held.
Existing issued legacy grants require separately established upstream fencing or
drainage authority; this implementation does not invent it or retire that original
requirement. The existing selected conditional protocol is an alternative with
its own explicit external assumptions and permanent markers, not a write-drain
certificate.

## Admission and proof

`social_media_write_owners` is created only beside a new upload before its first
grant. A generation and SHA256 binding cover the exact asset, uploader, provider,
bucket, two allocated keys, endpoint and credential material. Neither credentials
nor signed URLs are copied into the history. Rotation/mismatch refuses; no
credential replacement or retroactive enrollment operation exists.

Each grant/finalizer gets a unique operation identity and epoch before effects.
The maximum is 32 attempts per upload. Terminal states are immutable. A grant
can end `not_issued` or `issued`; a finalizer can end `completed`. An `admitted`
attempt stays uncertain on timeout, cancellation or failure to persist. All
mutations share global-budget, actor-budget, asset/upload locking. Closing an
owner is permanent and prevents every application re-entry from admitting a new
writer, including after the flag is disabled. An already admitted operation can
record its actual terminal acknowledgement after closure.

Reconciliation first freezes renewal, closes ownership and advances the asset
lease/version in the database. The bounded verifier checks the complete grant
epoch sequence, all finalization attempts and current credential/object binding;
it hashes the exact scope, generation and ordered immutable attempt identities.
The committing transaction rechecks that manifest under the shared asset lock.
No client receipt/Boolean supplies proof. Stored settlement, result and audit are
read back before success; PostgreSQL deferred constraints run before readback.
Unknown commit outcomes require inspection/replay, never a forced refund.

The successful command archives only an unreferenced nonready asset. It records
settlement and a durable audit, keeping all pending/byte reservations until the
existing explicit orphan cleanup confirms deletion. It never deletes a ready
original. All historical references and retained/permanent-fence/deletion history
keep their existing guards. The privacy adapter retains independent approval,
signed intent, policy and reference requirements; this protocol grants no privacy
retirement authority and never repeats storage I/O from privacy reconciliation.

## Operator entry points and replay

Authenticated admin POST
`/api/v1/admin/social/media/uploads/{asset_id}/reconcile-owned` uses
`Idempotency-Key` and this strict body:

```json
{"expected_version":1,"expected_grant_epoch":1,"expected_finalization_epoch":null}
```

The same key and original body return the exact stored result while it still
matches current durable state; a changed scope/key/result refuses. A failed
verification leaves admission closed and capacity held. Inspect the maintenance
report for the new version and retry explicitly with that scope. A closure is
not silently reopened. No automatic resend or mutation retry exists.

The existing explicit-database, bounded maintenance process also accepts
`--reconcile-owned-command /absolute/regular-file.json`. The file has the same
three expected fields plus `actor_id`, `asset_id`, `command_id`. Files are bounded
to 4096 bytes, opened without following links or blocking on FIFOs, and cannot
be combined with cleanup/retirement/recovery. The read-only maintenance report
adds nullable `owned_writer_state`; it supplies no settlement authority.

Migration `a706b17a0001`, predecessor `a705b15a0001`, adds private RLS tables with
no browser/PUBLIC grants and immutable admission/terminal/result history. It
backfills nothing. Downgrade refuses recorded owners; rollback disables the flag
and preserves ownership, pending reservations, markers and all evidence. New
tables need explicitly reviewed effective application privileges before use;
this change installs no production grants.

## Storage contract inspected in authenticated Chrome, 18 October 2026

[R2 S3 API compatibility](https://developers.cloudflare.com/r2/api/s3/api/)
(page updated 14 October 2026) lists conditional PUT `If-Match` and
`If-None-Match`. [R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
(updated 22 August 2026) describes local signing and reuse until expiry. These
documentary capabilities do not certify any actual bucket, credential, lifecycle,
SDK installation or request drainage. No provider/storage request was made.
