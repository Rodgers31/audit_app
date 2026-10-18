# Threads record-existing authority — contract v1

Decision TH-PUBLIC-001 (2026-10-18), implementing #724 and Blueprint §17.2/§18 recovery: use independently audited human authority. No provider automatic-public-proof claim is made. The adapter's authenticated lookup remains Processing/unknown. A successful callback, remote ID, permalink, private profile or administrator checkbox alone is insufficient.

An authorized administrator may propose a record-existing public outcome only after a fresh browser context with **no Threads/Meta login, cookies or session** displays the exact full post publicly. The observation must identify the numeric platform account and numeric remote post (each 1–64 digits, matching the canonical adapter contract; cross-checked against the retained owned-post receipt or independently retained identity evidence), exact permalink, full composed caption including link/hashtags, and ordered SHA256 identities of all approved media. A second distinct authenticated administrator must independently repeat the anonymous inspection and compare the immutable approved revision/payload, including original media bytes, with a separate capture and custody record. If account identity, bytes, full content, or anonymous visibility cannot be established, stop: no proposal/admission is justified. Authenticated own-post lookup is identity evidence only.

This is a deliberate human trust boundary, not machine verification of pixels or truth: both administrators are accountable for the asserted observations. The server validates exact binding and independent admission, not the contents of off-system captures. Misrepresentation by two authorized administrators is outside this authority model. This procedure must not be automated by copying fields from the context response. No URLs or custody records are fetched by this command, and it cannot upload or post. Do not include credentials, logged-in captures, tokens or personal browsing material in requests.

Retain each capture packet in existing approved operator evidence custody (no new storage service): a UUID custody reference, SHA256 of the retained capture packet, capture timestamp, anonymous-browser conditions, owner/remote identity basis, full post and exact media comparison evidence. The API stores the bounded provenance and observations in append-only social audit events. Operators must retain packet bytes for the publication's audit retention period and keep the UUID resolvable in that custody inventory. These hashes bind a human-supplied packet; they are not independent provider signatures. Do not admit a packet whose custody/bytes cannot be checked by the second reviewer. Both captures must be different, separately retained records. Capture hashes and custody references cannot be reused in another proposal or admission. No new credentials, provider grants or policy activation are required by this implementation.

## Operator API

All routes are under `/api/v1/admin/social`, require existing admin authorization, and return private/no-store responses. Every POST requires a fresh UUID `Idempotency-Key`; reusing a key with identical input returns the original receipt, changed input conflicts. Keep the key on an ambiguous HTTP response and retry that exact request before doing anything else. A committed response lost during transport is recovered through the durable receipt. Never send another Threads post to resolve an unknown outcome.

1. `GET /targets/{id}/public-proof` returns publication version, binding hash, exact approved revision/hash, account, payload hash, composed caption, ordered media hashes and known remote ID. This is reference material for comparison, not evidence of public availability.
2. `POST /targets/{id}/public-proof` proposes `{expected_publication_version, binding_hash, observation, reason}`. Response: `{proof_id, target_id, binding_hash, expires_at, state: "awaiting_independent_review"}`. No delivery state changes.
3. A different administrator invokes `POST /targets/{id}/record-existing` with `{expected_publication_version, proof_id, observation, reason}`. Response identifies the exact target/proof/remote and resulting publication version. Only this operation can record `published/public` with confirmation `threads_two_admin_public_v1`.

`observation` fields:

```json
{
  "method": "anonymous_browser",
  "visibility": "public",
  "observed_at": "2026-10-18T12:00:00Z",
  "capture_sha256": "<64 lowercase hex characters>",
  "custody_reference": "<UUID of the separately retained packet>",
  "external_account_id": "<exact numeric Threads owner ID>",
  "remote_id": "<exact numeric post ID>",
  "remote_url": "https://www.threads.com/@handle/post/shortcode",
  "text": "<exact composed approved caption>",
  "asset_sha256": [],
  "account_identity_basis": "<30–1000 characters describing independent identity evidence>",
  "review_notes": "<30–1000 characters describing anonymous observation and exact content/media comparison>"
}
```

Both observations must be within thirty minutes of database time (future times refuse). Proposal expiry is thirty minutes after the first observation, never renewed by submitting it later. Admission's capture must be independently fresh. Wrong shapes, explicit private/unknown observations, stale versions/bindings, different actors' missing proof, mismatched identities/content/media, repeated packets and contradictory remote identities refuse. A target with no public dispatch intent cannot be settled. Lease ownership, including expired-but-retained ownership, any account publication lease, and unfinished attempts refuse; complete ordinary worker recovery first. No new send or implicit lease takeover occurs.

The transaction locks controls → account → publication → target, consistent with worker admission. It revalidates immutable hashes, existing checkpoint identity, dispatch history and current state under those locks. Controls must already exist. The binding includes target operational state/checkpoint/remote references/lease epoch and publication version; worker progress after proposal requires a fresh proposal. Existing remote IDs cannot be replaced. Duplicate remote identity is checked across Threads accounts with the same numeric owner (including different API products); the existing remote uniqueness constraint remains in place. Both attempts and checkpoints survive admission. Audit, target settlement, version increment, exact-target hold release and command receipt commit together, with stored-row verification before commit. No schema or new roles/grants are introduced.

Cancellation, deadline expiry or global pause does not erase an existing external post. Record-existing may describe that past outcome; it never renews authorization for a new send. All unrelated account holds remain. This procedure's route authorization uses the existing admin role rather than adding granular roles. It has no browser product UI; its reviewable interface is the structured API and this custody procedure. Hosted/provider acceptance and authority delegation to real operators remain separate from inert fixture tests.
