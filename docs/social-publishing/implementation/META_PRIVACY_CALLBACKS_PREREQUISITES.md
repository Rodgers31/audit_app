# Meta privacy callback prerequisites (#488)

Prepared on 2026-10-08 against main
`f5239ed63e146650bee2d0fb1cec9b23616eb648`. This slice supplies two offline
helpers. It installs no callback, route, ownership index, database receipt,
retention policy or runtime configuration. #488 remains open until those
operational requirements have actual evidence.

## Implemented API and trust boundaries

`social.connections.signed_requests.verify_signed_request(value, *, app_secret,
expected_app_id)` verifies HMAC-SHA256 using the supplied app secret and the
**original encoded payload segment**. The signature comparison uses
`hmac.compare_digest`; JSON interpretation happens after a successful MAC.
The result is an immutable `VerifiedSignedRequest` with the configured app ID,
app-scoped user ID, encoded-payload fingerprint and optional timestamps.

The helper accepts canonical padded or unpadded base64url, a 32-byte signature,
an object with explicit `algorithm` and `user_id`, and optional `app_id`,
`issued_at` and `expires`. It rejects duplicate object keys, other fields,
noncanonical encodings, a different algorithm, mismatched explicit app ID,
malformed identities and timestamps. Application ceilings are 8,192 ASCII
request bytes, 4,096 decoded payload bytes, 64 decimal digits per positive
identity, 256 visible ASCII secret characters, and a timestamp ceiling of
253402300799. These are local acceptance rules, not advertised Meta limits.
Present timestamps must be positive integers, excluding booleans; an expiry
before issuance is rejected. The helper does not compare timestamps with the
clock, establish freshness, prevent replay or authenticate the caller's
secret-to-app configuration. A payload without `app_id` belongs to the
explicitly supplied configuration namespace.

Verification failures produce only `SignedRequestError`, code
`SIGNED_REQUEST_INVALID`, without retaining the decoder exception. Sensitive
result fields are omitted from representations. Fields remain available to
the server caller: do not serialize this result into public responses, logs or
delivery checkpoints. The fingerprint is a deterministic digest of the
configured app namespace and exact encoded payload; it is sensitive internal
metadata, not an anonymous user identifier or an idempotency guarantee.
Equivalent JSON or padding variants can have different fingerprints.

`social.connections.ownership.bind_declared_ownership(request, declaration, *,
expected_app_id, expected_credential_id, expected_credential_version)` compares
the typed request with an immutable `DeclaredCredentialOwnership`. It requires
exact app ID and app-scoped subject equality, a non-nil credential UUID and the
same positive credential version (bounded to signed 64-bit range). It returns
`DeclaredOwnershipBinding(status="declared_match", ...)` only for an exact,
well-shaped declaration. Missing, legacy, untyped or mismatched inputs return
`status="unverified"` without a credential reference. Both results explicitly
retain `provider_verification_performed=False`.

The ownership helper rechecks shapes but does not establish where its inputs
came from. Constructing matching typed objects can produce a declared match;
this is never authorization to delete data or dispatch work. A future caller
must supply a declaration derived from authenticated provider inspection and
bind it to the locked current credential version. Neither helper consults
environment variables, files, databases or providers, scans encrypted grants,
upgrades a legacy connection or changes publishing eligibility.

## Official protocol evidence

The current [Meta data deletion callback documentation](https://developers.facebook.com/documentation/development/create-an-app/app-dashboard/data-deletion-callback)
(updated 2025-11-07; read 2026-10-08) describes a configured HTTPS callback
receiving a POST `signed_request` containing an app-scoped `user_id`. Its
example verifies HMAC-SHA256 with the app secret over the original base64url
payload. The callback initiates deletion and returns JSON containing a status
`url` and an alphanumeric `confirmation_code`; the status must explain progress
or a legitimate refusal. App-scoped IDs must not be treated as Page-scoped IDs.
The document does not turn signature validity into freshness, duplicate
handling or completed deletion.

The current [manual Facebook Login documentation](https://developers.facebook.com/documentation/facebook-login/guides/advanced/manual-flow#deauth-callback)
(updated 2026-06-30; read 2026-10-08) says removal can occur without an app
interaction and describes configuring a deauthorization callback. The visible
current section did not specify the exact HTTP method, signing payload or
acknowledgment contract. Those details remain an implementation gate; the data
deletion response must not be assumed to be the deauthorization response.

The [official archived PHP SDK parser](https://raw.githubusercontent.com/facebookarchive/php-graph-sdk/5.x/src/Facebook/SignedRequest.php)
corroborates the encoded-payload HMAC and constant-time comparison. Its
repository was archived in 2022; it is historical parser evidence, not a
current deauthorization endpoint contract. Documentation fetches through the
web reader returned HTTP 429 during research; public browser-rendered Meta
documentation was readable. No authenticated provider request was made.

[Meta Platform Terms](https://developers.facebook.com/terms/dfc_platform_terms/)
(updated 2026-02-03; read 2026-10-08), sections 3.d and 4, require prompt
requested deletion and an accessible privacy policy with deletion instructions.
Retention required by law or regulation needs supporting evidence. These
terms do not grant a blanket exception for immutable delivery or audit history.
The legal retention decision and inventory are unresolved; preserving evidence
in this prerequisite does not settle that decision.

## Remaining callback and ownership work

A full callback needs an indexed, durable ownership mapping populated from
provider inspection: exact app ID and a versioned keyed digest of the
app-scoped subject, associated parent/Page credential UUIDs and versions, and
pending-flow references. The digest key needs its own backup and rotation
plan; pseudonymous records still require privacy treatment. Callback lookup
must not decrypt or scan every grant. Existing encrypted grant bundles alone
do not establish complete indexed ownership. Legacy or unknown subjects need
an explicit ownership resolution path; they must not be reported as having no
matching data without proven coverage.

A minimal durable request record needs a request UUID, app and callback kind,
an exact request fingerprint, subject lookup reference, database receipt time,
optional provider issuance time, state and a frozen set of affected credential,
account and pending-flow references. A data deletion receipt also needs a
random alphanumeric confirmation code stored securely, a lookup hash and a
status response. Exact retries must return the original receipt rather than
apply an old request to a later reconnection. Payload variants need a deliberate
deduplication policy; this helper's fingerprint alone does not provide it.
Audit events should refer to the request UUID, kind and affected counts without
raw requests, signatures, tokens, subjects or status URLs.

Deauthorization must block new publishing and revoke only the mapped grants
under the existing control/account/credential locking order. It must handle an
active lease, unlike the interactive disconnect busy response. In-flight or
uncertain targets retain their intents, checkpoints and remote receipts; a
callback cannot undo an already accepted provider operation or justify a
resend. Unknown ownership stays unresolved without destructive action.
Authenticated recovery reads and locally blocked future mutations need an
explicit policy when the provider has revoked the token.

Data deletion remains pending retention review until an inventory covers
Platform Data in grants, pending OAuth flows, account metadata, media, delivery
evidence, backups and subprocessors. Disconnect is not completed deletion.
The public status and privacy policy must reflect the approved deletion and
lawful retention decision. Preserve immutable evidence while that policy is
resolved; do not silently rewrite historical receipts or claim that the
append-only schema supplies legal permission to retain them.

Deployment acceptance still needs a real app identity, configured callback
URLs, protocol/acknowledgment evidence, ingress and log redaction checks,
receipt authorization, replay and concurrency tests, indexed ownership
coverage, and exercised encryption/digest key backup restoration and rotation.
Callback ingress must remain usable when new OAuth connections are disabled.
No app, bucket or worker has been provisioned or enabled by this slice.

## Executed checks

From `backend/`, using the configured Python environment:

```sh
PYTHONPATH=. python -B -m pytest --confcutdir=tests/social -p no:cacheprovider \
  tests/social/test_connections_signed_requests.py \
  tests/social/test_connections_ownership.py -q --tb=short
```

The authored suite passed **207 tests**. Positive fixtures cover the documented
minimal and optional-field payloads, original encoded HMAC bytes, both canonical
padding forms and exact declared ownership. Hostile cases cover malformed and
oversized input, noncanonical pad bits, signature size, duplicate/nested JSON
keys, scalars and non-finite values, unsupported fields/algorithms, strict
identity and timestamp types, mismatched app/subject/UUID/version, missing
typed declarations and forged incomplete objects. Separate checks exercise
MAC-before-JSON ordering, immutable results, sanitized exception context and
representations, and operation with network/file/environment entry points
disabled. Independent review executed 33 additional cases and found that forged
exact-type UUID objects with invalid internal values could return a declared
match. Four retained regressions were executed red before the fix for negative,
out-of-range, string and Boolean internal integers; the helper now requires an
actual integer strictly between zero and `2**128`. The combined authored and
independent suite then passed **240 tests**. This finding conferred no provider
authority, but violated the declared shape check and is now rejected.
One pre-existing SQLAlchemy `declarative_base` deprecation warning was emitted.
No live callback or provider behavior was tested.
