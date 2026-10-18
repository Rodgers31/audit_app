# Recorded-history legacy media recovery

## Supported boundary — owner decision, 18 October 2026

Recover app-recorded conditional-write histories. Keep unknown histories
quarantined with their objects and quota held. No arbitrary off-system writer
termination, retrospective declaration of history, timestamp-based release or
blanket cleanup is supported. The owner explicitly selected this boundary in
the B18 coordinator conversation; this is a scope decision, not an upstream
claim that unknown writers drained.

This completes the supported legacy recovery engineering boundary after the
B18 fix is reviewed and accepted. It does not certify live storage/provider
custody, actual-host worker shutdown/capacity or a publishing/upload pilot.
Those remain operational acceptance under490/488/699 and the original parents.

## Why a current storage capability is insufficient

R2 evaluates conditional writes against committed state atomically. A pair of
retained keys can fence writes that were actually admitted with create-only
conditions. A HEAD observation cannot prove an unknown earlier write ended.
See [Cloudflare consistency and conditional writes](https://developers.cloudflare.com/r2/reference/consistency/).

The storage runtime's current `retained_create_only` capability describes its
current implementation. It does not describe previously admitted requests.
The durable per-upload `write_protocol=conditional_create_v1` must therefore
exist **from allocation**. Its existing PostgreSQL trigger forbids UPDATE or
DELETE changes to protocol history; this release adds no migration or backfill.
Current retained allocations record that protocol before any bearer can escape.
The service flushes and refreshes the upload before signing, so a suppressed
insert or an old same-intent retry cannot replace durable proof with an in-memory
assignment. Unknown old intents cannot get another grant under retained mode.

| Observed history | Supported action |
| --- | --- |
| Recorded conditional protocol, ready original | Explicit retained recovery verifies actual bytes of both copies and releases only the pending slot once |
| Recorded protocol, ambiguous finalizer | Explicit same-original recovery re-inspects bounded quarantine, uses create-only finalization, verifies both copies and retains full byte accounting |
| Recorded protocol, failed/orphan/unreferenced bytes | Existing separately approved payload-retirement policy may install permanent fences; no raw delete or inferred drainage |
| Complete owned signer history, no bearer escaped | Existing owned-quiescence command can settle only its independently proven history; it does not backfill legacy protocol |
| Unknown protocol, untracked writers, missing/rebound history | Refuse recovery/renewal under retained mode; preserve objects, uncertainty and quota |

An existing complete owned history retains its separate proof protocol. The
new legacy check does not convert an issued grant into a never-issued grant or
mark an uncertain finalizer completed from a storage lookup.

## Operator sequence

1. Read the existing private maintenance report, at most20uploads per page.
   Unknown unsettled history now includes `LEGACY_WRITE_HISTORY_UNPROVEN`.
   The report never authorizes release or writes and pages are separate snapshots.
2. For a candidate with the recorded conditional protocol, observe exact asset,
   initiating administrator, upload version and grant/finalization epochs.
   Keep the original completion key/history. Do not populate missing fields.
3. Use the existing bounded `--recover-retained-upload` maintenance command with
   those exact expected versions/epochs, through the existing protected operator
   process configuration. Recovery needs the already reviewed media/retained
   runtime; all production switches remain off until separately accepted.
   No new DSN, credential, role, public endpoint, scheduler or service is created.
4. Re-read the result and accounting. Success keeps both copies charged and
   present, releases only the pending slot and retains immutable evidence.
   Same-state explicit replay must not create another object or refund bytes.
5. Any stale scope, active/lost lease, missing object, conflicting bytes,
   unacknowledged creation, missing protocol or damaged ledger remains held.
   Never substitute expiry or current port capability for admission history.

`MEDIA_WRITE_HISTORY_UNPROVEN` refuses before object I/O through the shared
retention, explicit recovery, completion/replay and retained signing boundaries.
Existing mutation authorization, resource bounds, admission locks, scope/lease
checks, inspection and accounting remain. No ready original is deleted.

## Validation and deployment

Issue752 records observed failing-first receipts for the prior capability/
provenance confusion. New formal regressions cover each direct service entry,
unknown stored-but-lost replies, positive recorded historical recovery/replay,
pre-bearer protocol visibility, suppressed admission and old-intent renewal.
The real migrated PostgreSQL case verifies that NULL history cannot be
backfilled and refusal preserves accounting with zero object calls. Existing
race, immutable-history and payload-retirement cases remain in the cohort.
Independent Spec and Standards reviews execute the actual service with inert
storage, normal and optimized Python. These are local implementation receipts,
not production storage or whole-host shutdown acceptance.

Deploy only the accepted source with existing additive schema in place, all
publishing/uploads/native/supervision/retained features off. No new migration,
configuration switch, grant or provider request is required by this code change.
First check exact source, health, paused controls, existing media/target counts
and accounting. Abort on source/flag/data drift. Preserve all media/protocol/
retained history on rollback; do not undo the immutable schema or use older
recovery code to bypass the newly required history. Code rollback is the prior
accepted40c5a0fb970f7a2882bc39bac867d2aed9b57bc9 with all media/native/retained
switches kept off; preserve schemae621b17a0001 and objects/quotas.

No paid resource, hosted Actions, bot review, storage upload, publishing or
worker activation is part of this implementation. A real storage test needs a
fresh bounded object/byte/request allowance; prior consumed allowances are not
reused. Unknown histories remain deliberately quarantined under the approved
supported boundary, rather than an unfinished promise to force-clean them.
