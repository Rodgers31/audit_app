# Meta credential recovery operator runbook

This runbook prepares #488 acceptance. No production key rotation, re-encryption,
deployment change, OAuth or publishing is authorized by its existence.
Use [the scope handoff](META_OPERATIONAL_READINESS_HANDOFF.md) for gate states.

## Minimum recoverable material and custody

Preserve an authenticated secret-store export containing every still-referenced
credential-envelope key version, its stable label and the selected active
version. Recovery format is the four-field v1 JSON contract documented in the
handoff; `keys` is the exact Fernet string map compatible with
`SOCIAL_CREDENTIAL_KEYS`, and `active_version` corresponds to
`SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION`. Keep nonsecret metadata separately:
app/product namespace, store/revision, backup capture time, owner/custodian,
access grants, integrity receipt, database snapshot/revision and version counts.
A hash alone cannot prove the right keys restore grants.

Store exports on an approved encrypted restricted recovery volume/secret store,
separate from database backups and source control. Restrict read/export to named
recovery operators with recorded break-glass access; runtime gets only required
decrypt/encrypt material; browser/CI/public telemetry gets none. Prove an
independent off-host restoration and loss-of-primary-store scenario. Never paste
keys/tokens/codes/subjects/connection strings into chat, commands/history, logs,
Git files or receipts. The helper's encoded bytes are secret material and must
not be printed. Use injected in-memory values or private operator-controlled
files only under separately approved access. This session used inert keys only.

## Version inventory and restoration order

1. Capture approved host/build/app identity and database snapshot. Keep runtime
   dispatch/connections gated while restoring; do not obtain consent or mutate
   Meta. Restore into an isolated approved clone before any live activation.
2. Inventory key versions and counts in `social_credentials` including revoked
   and unreferenced rows. Inventory `social_oauth_flows.key_version` with
   non-null verifier/pending-grant fields, all retained backups/WAL/DR snapshots,
   and older copies eligible for restoration. Counts must reconcile; do not
   assume only connected accounts hold ciphertext. Record missing/legacy
   ownership separately; do not scan grants to invent callback ownership.
3. Restore the complete versioned ring first, then the corresponding database
   and object/receipt data. Authenticate export custody/identity privately.
   `read_keyring_backup` rejects unsafe file shapes but does not authenticate
   who supplied keys or decrypt the export at rest. Load no implicit dotenv.
4. Build independent original/restored `RecoveryKeyring` values. In the clone,
   supply at least one `RecoveryProbe(owner_uuid, purpose, key_version, bytes)`
   for every retained version/purpose and reconcile full inventory counts.
   Call `verify_restoration`: exact owner is credential UUID for
   `facebook_user`/`facebook_page`, flow UUID for `oauth_start`/`oauth_pending`;
   provider/schema/purpose/owner are authenticated **inside the Fernet
   envelope**, not a separate Fernet AAD argument. A match proves these
   envelopes decrypt; missing coverage keeps acceptance incomplete. Keep
   bundles/subjects/rows private. Record counts, versions and failure codes only.
5. Reconstruct fresh cipher/process instances from independently read restored
   material. Exercise old envelopes, new encryption and malformed/wrong/missing
   key, unrelated owner/purpose and modified ciphertext controls. Prove failed
   persist followed by restart uses the prior authoritative copy; no success
   receipt on failed persistence. Include real store durability/permissions
   receipts beyond the local export's fsync.
6. Reapply approved deletion/retention decisions before opening clone/live reads
   or dispatch. Restore must not resurrect deleted subjects as active. Unknown
   retention approval or unproven digest lookup continuity is a blocking gate.

## Rotation, rollback and retirement constraints

An active-version change selects the key for **new writes**; it does not
re-encrypt existing rows. Add/backup the candidate version alongside old keys,
prove restoration, then authorize configuration activation separately. Keep old
keys present while any credentials, flow ciphertext or recoverable historical
backup uses them. This tooling performs no production row updates.

The existing account rotate-key service locks controls, affected accounts and
related credentials, checks current ID/version/leases, rotates parent User and
related Page grants, and persists in one command transaction. It does not rotate
all orphan/revoked credentials or pending flow ciphertext. A full retirement
requires a separately reviewed bounded inventory/migration plan including those
rows/copies, with no locks held across provider HTTP. Busy/in-flight/uncertain
publication evidence must remain reconcilable; never force a rotation or resend.

Rollback to the old active version is safe only with **both** key versions still
available: new-version rows cannot decrypt using an old-only ring. Retire an old
key only after zero references across the accepted recovery horizon, verified
new-version restore, reviewed retention/disposal and explicit retirement
approval. Destruction of a key or ciphertext is a consequential separate action;
it is not an automatic legal-deletion exemption or completion receipt.

## Separate subject-digest proof required from privacy scope

Credential Fernet keys protect reversible envelopes. Privacy subject-digest
keys support indexed app-scoped ownership lookup and must have a distinct
purpose/namespace, version inventory, access policy and backup lifecycle.
Never reuse/import the envelope export as a digest keyset. This helper reports
`digest_keys_verified:false` on every result.

`social.privacy.recovery.verify_subject_restoration` now supplies a bounded,
explicit in-memory proof for up to 100 supplied ownership records. Build two
independent `SubjectDigester` instances from separately obtained primary and
restored digest keys. Supply `SubjectRecoveryProbe(record_id, app_id, subject,
digest_version, stored_digest)` from an approved snapshot; subjects and keys
remain private. Both computations must match the stored digest, not merely
each other. Wrong or missing referenced keys, changed app/subject values,
duplicate record IDs and an active-version mismatch refuse. A supplied version
must select a key that reproduces the stored digest. The digest algorithm does
not authenticate the version label: two labels with identical key bytes produce
the same digest. Record IDs and labels must therefore come from the separately
reconciled snapshot; this helper does not authenticate that metadata. Distinct
rows may share a subject.
The result contains counts and version labels only and explicitly leaves
database coverage, backup custody and production authorization unverified.
This helper reads no database or secret store, writes nothing, and is not
automatically invoked by the app or worker.

The privacy owner must still demonstrate complete restored inventory coverage
and frozen receipt/affected-set references after restart; active rotation must
find old mappings/retries, and new mappings must survive restart. Missing,
wrong or corrupt versions must cause unresolved ownership rather than false
“no data”; failed persistence must not activate an unbacked version; retiring
either old or new key with retained rows must block. Repeat against an approved
restored clone with real namespace/version coverage and deletion ledger
reapplication. The helper does not implement the rotation/retirement workflow
or certify those broader operating gates. Existing credential-envelope results
continue to report `digest_keys_verified:false`; the separate scoped proof
does not silently upgrade them to complete recovery acceptance.

## Ingress verification checklist with safe synthetic probes

Before a separately approved deployed probe, obtain exact HTTPS host/build,
registered callback path, CDN/WAF/proxy/Next/API/monitoring exporter names and
private log receipt locations. Do not guess hostnames. Probe only that approved
path with uniquely identifiable inert markers in `code`, `state`, `access_token`,
`error`, `error_reason`, `error_description` and percent-encoded/duplicate forms.
Use no real credentials, valid signed requests or OAuth state. Record time,
status, build and benign correlation ID without storing a token-bearing URL.
These are GET reachability/redaction probes, not an OAuth flow or social write.
Failure-path probes that force errors belong in an approved staging clone.

Inspect each earliest collection point and downstream copy: CDN request URI,
WAF sampled event, reverse proxy `$request_uri`/access/error logs, Next hosting
request/redirect logs, API access logs, APM spans, Sentry events/transactions/
breadcrumbs/frame locals, log drains/archives/support exports and analytics.
Prove marker removal **before export/persistence**, including rejected/404/500,
redirect and transport failure paths. Use a harmless route/path correlation
positive control so an empty capture cannot pass. Ensure callback responses have
no external resources/referrer leakage and public redirects do not propagate
queries. The browser's history.replaceState cannot scrub an earlier access log.

Current outbound Meta transport and SocialRoute logs pass local synthetic
checks. Current inbound Sentry filter/frame-local captures fail (#525);
upstream exporters have no receipt. Do not mark deployed ingress verified from
these local results. Preserve each gate as VERIFIED_BY_EXECUTION, DECLARED_ONLY,
MISSING or BLOCKED with exact time/role/build/receipt scope. Complete protocol
registration and public status reachability only with the privacy scope's actual
callback contract; no deletion completion or public-policy authority is supplied.

## Bounded independent inventory and continuity seam

`social.recovery_inventory.verify_inventory_continuity` is an explicitly called
operator function. It accepts ten **bytes** arguments, never a database session,
mutable mapping, callback, path, environment variable or secret-store client:

```python
result = verify_inventory_continuity(
    source_snapshot, restored_snapshot, independent_manifest, subject_proofs,
    primary_envelope_backup, independently_restored_envelope_backup,
    primary_digest_backup, independently_restored_digest_backup,
    candidate_envelope_backup, candidate_digest_backup,
)
```

Use only synthetic inputs until the separate extraction/access/restore authority
is established. Do not paste these byte values into a shell, source, chat or
receipt: snapshots contain encrypted grants and subject proofs contain private
subjects. The verifier has no runtime registration and performs no durable write.
Its fixed ordinary failure is `RECOVERY_INVENTORY_REFUSED`, raised without parser
or cryptographic exception context. `KeyboardInterrupt` and `SystemExit` propagate.

### Input contract and independent provenance

Both snapshots are UTF-8 JSON objects with exactly `schema_version: 1`,
`snapshot_id` (canonical nonzero UUID string), and `tables`. Each table below must
be present as a list, including empty lists. Include every row in the approved
recovery projection, even orphan, revoked, expired and unreferenced records.
Do not filter by connected account or by the active key. Column names in this
projection correspond to the models; it deliberately omits unrelated columns.

| Projection table | Exact row fields |
| --- | --- |
| `credentials` | `id`, `credential_kind`, `parent_credential_id`, `version`, `key_version`, `encrypted_bundle` |
| `flows` | `id`, `status`, `key_version`, `encrypted_verifier`, `encrypted_pending_grant` |
| `ownership` | `id`, `app_id`, `digest_version`, `subject_digest`, `reference_key`, `flow_id`, `credential_id`, `credential_version`, `account_id`, `page_id`, `generation_at` |
| `receipts` | `id`, `app_id`, `kind`, `digest_version`, `subject_digest`, `event_key`, `request_fingerprint`, `affected`, `state`, `resolution`, `audit_id`, `confirmation_hash`, `confirmation_key_version`, `encrypted_confirmation` |
| `variants` | `id`, `app_id`, `kind`, `fingerprint`, `receipt_id` |
| `accounts` | `id`, `credential_id` |
| `audits` | `id` |

Ciphertext fields are canonical standard base64 strings, or JSON `null` only
where the model allows absence. Nullable references use `null`; numeric versions
are positive signed 64-bit integers, never booleans. Timestamps are actual UTC
calendar instants written as `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`. `affected` is the
frozen list of exact `ownership_id`, `flow_id`, `credential_id`,
`credential_version`, `account_id`, `page_id` objects from the receipt. Historical
ownership generations may precede the current credential version. The verifier
preserves historical account bindings when a reconnect changes the account's
current credential, or that pointer is cleared. The historical credential,
account and flow must still exist; its version, canonical reference and frozen
callback affected set must reconcile with the manifest. A non-null current
account credential must independently reference a retained credential. The
verifier does not rewrite history to use the current grant. The verifier
checks references and subject identity across digest versions, and decrypts
`privacy_confirmation` with the receipt UUID, checking the resulting code against
its stored confirmation hash. Receipt variants and their canonical fingerprints
must remain present. No ledger row is treated as a deletion completion.

The independently reconciled manifest is a separate JSON object containing
exactly `schema_version: 1`, `snapshot_id`, `active_envelope_version`,
`active_digest_version`, and `records`. `records` has all seven table names,
each mapping **every** expected row UUID to its SHA-256 commitment. A commitment
is SHA-256 of ASCII JSON for the entire projection row, with sorted keys,
compact comma/colon separators, `ensure_ascii=True` and nonfinite values refused.
Row order is irrelevant; nested affected-list order is committed exactly.
Independently reconcile this manifest against the approved snapshot and its
nonsecret extraction/custodian receipts. Generating it from the same unchecked
input and calling it independent supplies no new evidence. The helper does not
create manifests or authenticate their issuers. IDs and version labels bind to
these commitments, including when distinct HMAC/Fernet labels alias equal key
bytes. Cryptographic success alone cannot authenticate a label.

`subject_proofs` is exactly `schema_version: 1`, `snapshot_id`, `records`; each
record is `{ "table": "ownership" | "receipts", "id": UUID, "subject": ASID }`.
It must cover every ownership and receipt row exactly once with independently
obtained private subjects. No raw subjects go in the snapshot or result.
App namespaces and stored digests come from the independently committed rows.

Envelope backups use the existing `meta_credential_envelopes` v1 contract.
Digest backups are separate JSON objects with exactly `schema_version: 1`,
`purpose: "meta_subject_digests"`, `active_version`, `keys`; `keys` maps labels
to lowercase hex strings encoding exactly 32 bytes. Never use envelope material
for digest keys. Primary/restored active labels must equal the manifest labels;
all their version labels and key bytes must match, including unused keys.
Candidate active labels may differ, but an existing label cannot acquire new
bytes, and every retained envelope/digest must still be readable. Fresh instances
are reconstructed for active encryption/digest canaries. Use the same independently
restored bytes as candidate inputs for a restoration-only drill. Different input
objects or matching hashes do not prove independence or custody.

Bounds apply at the function boundary: each snapshot is at most 2,000,000 bytes;
manifest and subject proofs each 256,000 bytes; each key backup 65,536 bytes;
1,000 total projection rows per snapshot; 128,000 decoded bytes per envelope;
500 affected references per receipt; 64 envelope versions and 16 digest versions.
Duplicates, extra/omitted fields, duplicate IDs/keys, nonfinite values, malformed
shapes and over-limit inputs refuse. Empty categories are valid, but a drill
requires at least one envelope and one subject-bearing record. An empty database
needs a separately designed empty-inventory attestation; it cannot pass vacuously.
Partitioning a larger inventory is not global acceptance: retain and independently
reconcile the complete partition census and references before designing support.

### Honest verdict and remaining restore drill

Success means `snapshot_coverage_verified: true` **only for this independently
manifested recovery projection**, plus execution of every supplied envelope and
subject lookup with primary, restored and candidate material. The result reports
row/envelope/subject counts and candidate labels; it contains no row IDs, grants,
subjects, keys or digests. `restart_scope` explicitly says
`fresh_instances_from_supplied_backup_bytes`; a fresh Python process synthetic
replay also exists in the test cohort. Neither proves real secret-store durability,
failed-write handling or deployed process continuity.

`database_coverage_verified`, `backup_custody_verified`, `production_authorized`,
`retirement_authorized`, `deletion_authorized` and `deletion_completed` remain
**false on every success**. PR679's supplied-subject helper retains its original
false coverage/custody/authorization flags. No wrapper promotes those results.

Before any separately approved operational acceptance:

- Authenticate a complete read-only extraction at an approved database snapshot,
  namespace/build/schema/role and recovery horizon. Reconcile projection row IDs,
  labels and counts independently, plus omitted columns and domain tables. This
  seam supplies no database extractor, transaction fence or production census.
- Restore actual independently held off-host backups under named custody and
  loss-of-primary-store conditions; authenticate labels and exported material.
  Test backup storage permissions, durability and restore failure. Local synthetic
  bytes and hashes supply neither identity nor custody.
- Reconcile **all** retained database backups, WAL, historical snapshots, object
  copies and the authoritative deletion ledger through the restore cutoff.
  Frozen privacy receipts in one snapshot cannot prove a later deletion ledger
  was reapplied. Resolve unindexed legacy ownership and media/subprocessor
  attribution; preserve unresolved quarantine and pending retention review.
- Execute actual failed-persist/restart and approved rotation/rollback drills on
  the intended isolated store/runtime. Preserve old and new versions until every
  accepted recovery copy is proven readable; candidate key absence refuses for
  referenced material. This helper does no re-encryption or persistence.
- Obtain approved retention/disposal policy and separate explicit key-retirement
  or deletion authority. A zero reference count in one snapshot is insufficient.
  No destructive retirement or deletion executor is provided here.
- Retain deployed ingress/exporter redaction, protocol registration, effective
  roles, owned-account identity and approved worker/media acceptance separately.
  Keep publishing, uploads, native delivery and retained writes OFF throughout
  this engineering slice. Chrome acceptance is unexecuted in this lane.


### Nullable account credential references (#688)

The inventory accounts projection includes unlinked accounts: credential_id may be null, matching SocialAccount's nullable foreign key. Nonnull values must remain canonical UUIDs present in the complete credential inventory; null does not remove the account row from its independent manifest commitment. The coordinator reproduced the null-reference refusal on the original PR source, then verified eight optional/dangling/malformed reference controls. The affected recovery cohort passes273 tests; the inventory cohort passes144 in optimized Python. Snapshot coverage continues to establish neither live database completeness, independent backup custody, nor production/deletion/retirement authority. This change performs no live restore or key operation.
