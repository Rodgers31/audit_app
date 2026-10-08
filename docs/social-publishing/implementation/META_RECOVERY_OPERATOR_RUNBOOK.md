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

The privacy owner must add independent original/restored digest instances with
inert subjects: same app/subject/version yields the exact persisted lookup and
frozen receipt/affected-set references after restart; unrelated app/subject/key
fails; active rotation still finds old mappings/retries; new mappings survive
restart; missing/wrong/corrupt versions cause unresolved ownership rather than
false “no data”; failed persist cannot activate an unbacked version; retiring
either old or new key with retained rows blocks. Then repeat against an approved
restored clone with real namespace/version coverage and deletion ledger
reapplication. This runbook does not implement that privacy code or certify it.

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
