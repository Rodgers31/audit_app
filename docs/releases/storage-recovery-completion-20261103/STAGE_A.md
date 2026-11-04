# Future Stage A: exact operation and refusal packet

**PREPARED; NOT AUTHORIZED OR RUN.** Every command below is conditional on a
later explicit parent-owned decision. The only currently permissible next work
is read-only observation, local review and completion of the named owner inputs.
No script here changes a flag or supplies authority from a policy digest.

## Admission record, completed before the window

The private decision must contain: exact reviewed source/tree/schema/package
inventory; backend/frontend/origin; actor UUID; unique new draft title; one
fixture's JPEG hash/length/1080-square decode; exact existing source bucket and
qualified writer inventory; provider-issued expiry and earlier accepted renewal
deadline; named attending/stop/custody/restore people and different independent
reviewer; policy/holds/exceptions and accepted decision time/offset; existing
destination/access/encryption/key-recovery/custody UUID; complete dependency
inventory and byte caps; exact 10/60-minute limits or an explicitly revised
window; positive current resource/DB/egress reserves; expected deltas; stop path
and independent readback cadence. Blank/refused/unverified fields mean HOLD.

The restored target must already be independently qualified with exact source,
actual media constraints/migrations and required tooling. A network-none local
container, no published ports and an owned Unix socket are the preferred shape;
no production credentials, external network or public/local TCP listeners.
Existing image references alone are not durable custody or a recovery test.
Preparation of a fresh destination, image copy or dependency archive requires
its exact additional authority and inclusive cap before execution.

Parent must separately bind actual current controls, the distinct draft master
and both repository generation hooks, paused saved accounts, workers/processes,
schema and financial/social/media observations. Do not compare tonight's DB
with a pre-nightly fingerprint as if scheduled ingestion had not run.

## One normal browser intake

1. Parent reads current source/config/actor/schema, qualified storage metadata,
   object inventory and database-only maintenance report. Browser is on
   `https://www.auditgava.com`. Record original version/idempotency identities
   privately; no bearer URL, secret or raw provider/account body enters evidence.
2. Parent enables only `SOCIAL_MEDIA_ENABLED=true` and
   `SOCIAL_MEDIA_RETAINED_WRITES_ENABLED=true` through the separately reviewed
   existing configuration path. Read both actual resolved values back before
   intake. Fenced retirement, owned quiescence, publishing/account consent,
   workers/supervisor, financial/general/draft generation, generation hooks,
   automatic approval/scheduling/publication and native/automatic source admission
   remain OFF/held. The decision explicitly permits ordinary proof-bound
   pending-slot release after both-copy verification, not byte release.
3. In a **new unsaved manual composer**, select no account targets and no source
   references. Upload the authorized one JPEG using the normal Images & video
   control before saving. `MediaUpload.tsx` retains separate initiation and
   completion keys; `SocialComposer.tsx:194` submits the attached document in
   its first `POST /posts`. Do not save an empty draft first, switch to an
   existing draft, call a provider endpoint or create another asset to retry.
4. Exact normal API contract, exercised by the mounted fixture:

   - `POST /api/v1/admin/social/media/uploads`, one UUID Idempotency-Key,
     `{filename, declared_mime_type:"image/jpeg", declared_size:N, alt_text}`.
     Expected201; capture returned asset UUID/version1. Returned method is PUT;
     signed Content-Length, Content-Type, host and If-None-Match guards must be
     present. Do not record the signed URL.
   - Browser sends exactly N bytes with `Content-Type:image/jpeg` and
     `If-None-Match:*` to the returned private URL. One successful conditional
     creation; no unconditional PUT, changed body or new key on uncertainty.
   - `POST .../uploads/{allocated_asset}/complete`, original completion UUID
     Idempotency-Key and `{"expected_version":1}`. Expected200, ready/version2,
     exact recorded JPEG hash, byte size, width1080 and height1080.
   - `GET .../assets`, `GET .../assets/{asset}/preview`, browser private GET.
     Expected200, private no-store API metadata, byte-identical preview. Actual CORS
     and private origin behavior must be observed in the browser; SDK doubles
     do not fill this check.
   - First `POST /api/v1/admin/social/posts`, one new command key, manual title,
     content_type announcement, harmless synthetic master text/alt text and
     exactly this asset in `document.master.media`; `targets:[]`, `references:[]`.
     Expected201, post version1 and one initial revision/reference. No PATCH,
     submit, approve, schedule, publish, destination validation or account/grant
     command is included. Extra revisions/delivery rows invalidate the envelope.

5. Parent promptly restores **both temporary flags false**, then independently
   reads back actual resolved values and every other hold, separate generation
   master/hooks, paused accounts and zero workers/targets/publications/attempts.
   “Command submitted” does not prove OFF restoration. If uncertain, stop and
   escalate to the accepted stop operator immediately.
6. On success read back both payload hashes/identities, immutable original
   protocol and retained fence, pending_count0 for each of the two budget rows,
   reserved_bytes=2N and bytes_used=2N on each scope. Browser grant epoch stays
   unknown (grant_epoch≥1, grant_settled_epoch0); finalization is settled once.
   No age, HEAD, lease expiry or restored fence establishes write quiescence.
   Failure keeps the actual pending/byte state; no forced settlement or refund.

## Consistent, dependency-closed custody capture

The following is the exact callable wrapper sequence for the parent's reviewed
bounded read-only wrapper. It creates no connection from an arbitrary CLI DSN.
Use the existing TLS verify-full authorized reader; refuse a different endpoint,
role/schema or missing CA instead of substituting TLS require/no verification.
The caller owns source/transaction/timeout/permission validation and custody
authorization. These symbols are supplied by that already-reviewed wrapper,
not guessed credentials or an ambient `.env`:

```python
from sqlalchemy import text
from sqlalchemy.orm import Session
from social.media.recovery_packet import publish_stage_a_packet, read_stage_a_packet

with approved_reader.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
    with connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL row_security=off"))
        connection.execute(text("SET LOCAL statement_timeout='5s'"))
        connection.execute(text("SET LOCAL lock_timeout='1s'"))
        with Session(bind=connection) as db, db.begin():
            manifest_sha256 = publish_stage_a_packet(
                db, approved_read_storage, actor_uuid, asset_uuid, new_post_uuid,
                approved_existing_private_root, accepted_custody_uuid, context,
            )

# Retain manifest_sha256 in the independent accepted custody/decision record.
# A different reviewer then opens the preserved original inputs:
rows_bytes, payloads, manifest = read_stage_a_packet(
    approved_existing_private_root, accepted_custody_uuid,
    independently_retained_manifest_sha256,
)
```

Keep the read-only snapshot through both bounded object reads. This yields a
consistent DB slice plus matched immutable object identities **only within the
independently qualified conditional-only writer envelope**. OFF flags, absent
versioning or an expired browser grant are insufficient against an unaccounted
administrator/client. Any writer/identity/intent drift stops capture.

The implemented wrapper publishes to the exact D3 destination/custody UUID using
fresh owner-only files and exclusive creation, flush+fsync each and its directory,
then reads back all bytes. It preserves incomplete captures on any failure and
writes exactly `rows.json`, `quarantine.bin`, `original.bin` and a ≤65,536 B
manifest containing their exact bytes/hashes, both keys/ETags/version values,
MIME/geometry, source/schema/runtime and generator inventory hashes, snapshot
cutoff, source-qualified writer/policy/appointment decision references, dependency
inventory references/bytes and custody UUID. Include all independently retained
applicable signed intent/later unresolved effects. No such missing ledger may
be replaced with an asserted empty list. Execution and its exact destination
remain parent-owned; the library deliberately has no arbitrary
filesystem-export or live-restore CLI.

Maximum newly captured data is720,896 B inclusive. No compression ratio is
assumed. Hash the outer manifest independently into the accepted decision/
custody record before reconstruction. All dependencies must be independently
available under the inclusive approved cap; stop before publication if they
are unapproved, unavailable or oversized. The exact `context` keys are
`source_commit`, `source_tree`, `schema_revision`, `runtime_sha256`,
`policy_sha256`, `decision_sha256`, `writer_inventory_sha256`,
`appointments_sha256` and `dependencies_sha256`; values refer to actual
independently reviewed records, never dummy hashes or credentials. Do not take a whole DB dump to avoid
resolving the slice, include credential/account ciphertext, or discard history.

## Independent nonempty isolated reconstruction

Named restore operator uses a different empty target, preserved input packet and
the exact already-qualified schema/migration/runtime. Source DB/store must not
be reused. No live credential is present. All objects are reconstructed only
inside the private fixture storage port, never R2 or production. Both input
payloads are read back from custody and passed to `verify_stage_a_payloads`.

```python
from sqlalchemy import text
from social.media.recovery import restore_stage_a_rows

with isolated_target.begin() as connection:
    # PostgreSQL only; SQLite rehearsal does not substitute for PG constraints.
    connection.execute(text("SET LOCAL row_security=off"))
    restore_stage_a_rows(connection, independently_read_rows_bytes)
```

After commit, a fresh REPEATABLE READ READ ONLY/row_security-off read must run
`capture_stage_a_rows` again and compare canonical bytes with the retained input.
This exercises actual stored state, not in-memory equality. Reinspect each local
JPEG through the actual intended inspector; mount the ordinary media/post APIs
with restored rows, fixture-only object transport and inert signing identity.
Require library, post/reference and private preview readbacks with exact hashes,
budgets, pending release, retained fence and unknown browser epochs. All upload,
publishing, generation and automatic availability must read OFF when mounted
with the ordinary OFF runtime. No remote object restore is implied.

Run preserved isolated variants with missing original, corrupt original,
missing quarantine and corrupt quarantine. `verify_stage_a_payloads` must refuse
each. Original preview may remain usable when only quarantine is missing; that
does not pass recovery. Missing upload/fence/budgets/revision/reference/audit/
receipt history, unknown child history, RLS filtering, cross-schema children or
extra source/account dependencies must refuse. Also catch a failed restore
inside the caller transaction and deliberately commit that caller: every capsule
table must still contain zero partial rows. Never repair a failed variant or
release quota to obtain a green result. Retain all variants under approved custody.

The different independent reviewer checks retained original input hashes,
actual stored rows after commit, mounted API behavior, true negative controls,
generator/source/runtime/dependency identities and OFF restoration. Record
actual cases per mode/runtime without summing overlapping reviews. Local or
inert-inspector proof is not real browser/custody/intended-host acceptance.

The inclusive operation inventory also counts the original fixture, browser/OS
caches, decoded buffers, normal inspector/transient copies and every preserved
restore variant. API no-store does not prove the direct R2 signed GET response
or browser cache is no-store. The existing `_signed_get` has no cache-control
override. Parent/privacy/admin must qualify the response/cache contract and an
observed browser copy budget; any unknown or exceeded bound holds/rescopes the
operation. No cache deletion or new privacy contract is installed here.

## Stop and final readbacks

Abort for missing decisions, expiry uncertainty/deadline breach, unknown writer,
schema/source/account/actor/config/version drift, any extra asset/revision/object/
provider/delivery/financial effect, failed identity/hash/history/readback, ambiguous
commit, resource/byte/time violation or loss of an attending operator. Parent
stops further actions, restores both temporary flags OFF and proves that state.
Preserve actual histories, original command identities, both remote copies where
created, every custody/restore variant, all quota charges, fences/markers and
uncertainty. No automatic retry with a new identity, second intake, age/HEAD/lease
release, forced settlement, quota refund, cleanup/deletion, schema downgrade,
production restore, grant verification or provider send is included.

Final independent reads require exactly authorized deltas, private unchanged old
diagnostics, no new public access, all holds OFF, zero worker/target/publication/
attempt effects and recorded unresolved limits. Incomplete stop/capture/restore
is reported as incomplete. Stage A never authorizes Stage B/C, sustained intake,
renewal/permission change, a cost/egress guarantee or source acceptance.
