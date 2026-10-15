# Native runtime and retained-copy recovery

This implementation closes the missing production composition seam in #476 and
adds a conservative opt-in recovery path for #490. Code completion does not
establish production operational acceptance or authorize publishing.

## Default-off composition

`SOCIAL_NATIVE_ENABLED=false` and
`SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED=false` are the defaults. Both must be
literal `true` to install native Facebook Pages and Instagram Graph adapters.
Enablement also requires validated existing Meta configuration, the credential
keyring, enabled private R2 storage, and working JPEG/PNG inspection. Invalid or
partial configuration refuses startup. An explicitly supplied configuration map
never borrows missing credentials from the process environment.

The API lifespan owns one media runtime per app and shares it with native
composition, media routes and system status. HTTP never constructs the global
CLI cache. Shutdown detaches the app bindings and closes its SDK client once,
including when media is enabled while native adapters are off. Concurrent app
instances own separate clients. The lifespan installs only the registry and
credential/media ports; it starts no worker or scheduler. Shutdown detaches the registry before closing adapters
and the R2 SDK client. Partial construction and failing closes still attempt all
owned resource closures, with sanitized public errors.

The explicit separate process is:

```text
python -m social.worker --database-url <private-existing-DSN> \
  --deployment-version <accepted-commit> --native-meta --once
```

The DSN must remain private; use the existing operator's protected process
configuration, not chat, screenshots, or shared command history. `--once` runs
one bounded scan and exits with a stopped heartbeat. No flag in this change
creates a paid service, scheduled job, provider account, hosted Actions run, or
always-on process. Omitting `--once` deliberately runs the existing loop; that
requires separately accepted hosting, ownership and cost evidence. A web
registry alone does not promise scheduled delivery.

`SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED=true` is an operator attestation, not a
shortcut. Keep it false until the exact deployed privacy, backup/recovery,
telemetry, role/access, media and cost gates have receipts. Local fixture tests
set it only for their isolated scope. Existing database global/account publishing
controls and human approval remain authoritative.

## Retained-copy decision (RET-001, 2026-10-15)

`SOCIAL_MEDIA_RETAINED_WRITES_ENABLED=false` is the default. When explicitly
accepted and enabled, successful completion verifies both the quarantine and
ready original by positive metadata and actual byte hashes, then records an
immutable retained fence. R2's create-only `If-None-Match: *` check is atomic at
commit; leaving the committed keys present prevents another creation at those
keys. This is **not evidence that earlier requests drained**. See
[Cloudflare's consistency contract](https://developers.cloudflare.com/r2/reference/consistency/).

Both objects must remain present, both copies stay charged in the global and
uploader byte budgets, and only the pending-upload slot is released. Repeated
calls recheck charged-byte lower bounds. During first verification, a changed/missing original or quarantine, stale
scope, active/lost lease or insufficient ledger refuses success. Existing-marker
replays check recorded scope and charged bytes without fresh storage reads;
they do not continuously monitor object existence or integrity.
An existing ready original's inspection metadata is never rewritten.

There is no automatic deletion for retained pairs, even after expiry, archive or
reference removal. `ready_retention_days` is not a deletion promise. Default
limits remain 2 GiB global, 200 MiB per uploader, three pending uploads; this mode
holds two copies per successful image within those limits. Quota exhaustion
blocks new uploads. It never silently drops either object or releases bytes.
Changing retention, deleting retained evidence, repairing a damaged ledger or
retiring the bucket credential requires a separate reviewed operator procedure.
Cloudflare account-level free usage is not a hard spending cap; these limits do
not account for unrelated buckets or other applications' request volume.

## Explicit unknown-outcome recovery

Public completion never blindly retries an unknown finalization. The operator
must observe the exact upload version and grant/finalization epochs using the
read-only maintenance report, then separately issue one scoped command:

```text
python -m social.media.maintenance --database-url <private-existing-DSN> \
  --recover-retained-upload <asset-UUID> --actor-id <initiating-admin-UUID> \
  --expected-version <observed-version> --expected-grant-epoch <observed-epoch> \
  --expected-finalization-epoch <observed-finalization-epoch> --once
```

An absent finalization epoch is represented by omitting that argument, only for
a state where the recovery contract permits it. Do not invent an epoch. Recovery
is incompatible with cleanup and report pagination in the same invocation. It
re-inspects the immutable quarantine, uses the existing completion command and
create-only original, then verifies and retains the pair. Conflicting bytes fail;
no deletion or quota release is used to force progress. All storage I/O happens
outside database transactions. Existing write-drain reconciliation refuses a
retained record before changing its version.

The report counts retained fences separately while still honestly reporting
unknown browser writes. Database-only reporting supplies no write-quiescence or
original-deletion authority. Non-ready failed/archived uploads remain held until
a separately supported reconciliation exists. General quarantine cleanup is
still unwired and must stay disabled for unknown writes.

## Migration, rollback and first observation

Apply additive revision `a490b15a0001` after `a611b12a0001` before starting the new
ORM/API. Its nullable field preserves existing history; its database constraint
forbids settling grants, cleanup or capacity release on retained records, and its
trigger forbids replacing/clearing a recorded fence. Lock timeout is 2 seconds
and statement timeout 30 seconds. Downgrade takes an ACCESS EXCLUSIVE upload-table lock before checking history,
so an in-flight fence writer cannot commit between the check and destructive
DDL. Lock acquisition is bounded by the same timeouts. Migration failure must
abort the release.

Before deployment, retain the exact accepted source/configuration, resolved
flag values and schema revision, and verify both global and account publishing
are paused. Ship all new flags off first. First observation is startup/readiness,
unchanged paused Chrome controls, current migration head and no new provider
attempts/worker heartbeat.

Rollback to previously accepted backend
`ba89a7f4245a952aefd8ca140b1ac00330ae6514` by selecting that exact commit in the
existing Render service. First set both native flags and the retained/media
flags false, stop the explicit worker and all reconciliation/cleanup commands,
and preserve the additive schema, keys, retained objects and full reservations.
Do not run old reconciliation commands against retained history: an older
implementation can change the version underlying the immutable marker. The old
cleanup query's grant-settlement guard excludes retained rows, but this is not a
blanket compatibility claim. New migration downgrade deliberately refuses once
any retained history exists. No automatic destructive downgrade or object purge.

Any later bounded production acceptance must have a fresh exact object/byte/
request budget. The earlier four-PNG/1 KiB/30-request storage approval is already
consumed and is not an ongoing test allowance. Abort on unpaused publishing,
unexpected account identity, quota/accounting drift, remote mutation, unexpected
request volume, readiness failure or resource leaks. Keep all new enablement off
until the cause is resolved. A real publication requires separately approved
content/destination; no publication is part of this implementation.
