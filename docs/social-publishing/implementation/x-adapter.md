# X API v2 candidate implementation

Contract inspected **2026-10-16**; adapter identity `x-v2-2026-10-16`, API path
version `2`. This is tested code against sanitized HTTP fixtures. It is not
deployed, live accepted, or permission to enable spending, posting or uploads.

## Official contract inputs

- [OAuth 2.0 PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code)
  establishes the user authorization flow and granular scopes. Connection
  persistence and PKCE flow ownership remain in the shared connection layer.
- [Create posts](https://docs.x.com/x-api/posts/create-post) and
  [v2 chunked uploads](https://docs.x.com/x-api/media/quickstart/media-upload-chunked)
  establish the separate initialize, append, finalize and status endpoints.
- [Own-post timeline](https://docs.x.com/x-api/users/get-posts) supplies one bounded
  recovery page after a lost create acknowledgement. Both the inspected HTML
  and OpenAPI 2.171 name its field selector `post.fields`; the route itself
  remains `/2/users/{id}/tweets`. `max_results=5` is the documented minimum.
- [Character counting](https://docs.x.com/fundamentals/counting-characters) and
  [twitter-text v3 configuration](https://github.com/twitter/twitter-text/blob/master/config/v3.json)
  establish NFC, weighted ranges, emoji handling and the 23-character URL length.
- [Pricing](https://docs.x.com/x-api/getting-started/pricing) establishes the
  inspected request/resource prices. No credits, developer plans or payment
  methods were acquired or changed.
- [Official OpenAPI](https://docs.x.com/openapi.json), upstream `info.version`
  **2.171**, is captured as selected paths and their schema closure in
  [`contracts/x-v2-2026-10-16.json`](contracts/x-v2-2026-10-16.json). The original
  full response SHA-256 is
  `e5e1b75cea8eba9bd1945d08b01f386f75f5134b253b1559be3a4156569d67c2`.
  This snapshot confirms `metadata.alt_text.text`, its 1000-character maximum,
  OAuth `media.write`, numeric remote IDs and supported request structures.
  Documentation version pinning does not freeze a remote provider's behavior.

## Dispatch and recovery

`XAdapter` implements the existing durable worker ports. Each plan names exactly
one provider request boundary and its immutable input checkpoint. Upload IDs,
media keys, chunk cursor, earliest expiry, processing state, selected asset index,
post ID and target content hash survive serialization and adapter reconstruction.
No publisher-owned database transaction or private retry queue is introduced.

The default `XAdapterConfig()` disables the adapter and uploads. Every admitted
`execute` and `reconcile_operation` also requires verified application access,
matching account identity, current server-only user credentials/scopes, positive
remaining budget and an operation-ID-bound reservation covering that request.
Read operations cannot inherit the original write's reservation. The legacy
unbound `reconcile` method refuses HTTP requests; the worker uses the explicit
`reconcile_operation` hook with its newly committed read intent.

Post creation reserves 15,000 microUSD, or 200,000 microUSD when a URL appears in
the rendered text, including links typed directly in text. Public readback
reserves a conservative 15,000 microUSD: one post at 5,000 plus one expanded author
at 10,000, whose `protected: false` proves public-account visibility. The adapter
does not assume owned-read discounts or daily billing deduplication. Media
metadata reserves 5,000 microUSD. Upload/status pricing has no assumed zero:
`media_request_cost_microusd=None` makes those endpoints unavailable until a
reviewed positive ceiling is supplied. Fixture tests supply a clearly synthetic
5,000 microUSD ceiling; it is not a claim about the provider's upload tariff.
The shared durable budget ledger, not an adapter-local counter, reserves and
settles costs under its own account/operation fences.

Lost/malformed mutation responses retain all known remote references and an
uncertain phase. They never authorize another publish or upload. Reconciliation
prefers one exact known post ID and verifies author identity, rendered text, expanded
URL entities, attachment media keys and public author visibility; withheld content
does not satisfy public confirmation. X-added attachment URL suffixes are removed
only for the exact post with the matching selected media keys.

When the returned post ID was lost, a single own-post lookup reserves a worst-case
35,000 microUSD for up to five posts plus one expanded author. It requires the
original publish operation UUID, affirmative public/mutation intent, aware dispatch
timestamp and a durable request fingerprint matching this exact payload and
original checkpoint. For media, every selected media key must already be retained.
The request covers dispatch minus five seconds through dispatch plus five minutes;
before that entire window has elapsed it returns an explicit pending-window
reason/next-action time and performs no HTTP request. The adapter never truncates
the window to the current time. Resuming that pending read is the worker's decision.

One complete bounded page with exactly one strong text/media/account/time/public
visibility match can confirm the existing post, save its ID and preserve the
matching criteria/window/original-operation evidence. Pagination, inconsistent
counts, duplicate identities, missing or invalid timestamps, partial provider
errors, multiple matches and incomplete original intent remain unknown. No empty
page, 404, permission failure or duplicate-content response establishes definitive
absence. Unknown outcomes retain the original charge reservation. Recovery never
sends a second mutation or automatically retries the original publication.

## Deliberate application limits and remaining gates

- Text, one photo, two to four photos, and one MP4 have fixture-tested operation
  chains. JPEG/PNG cap: 5,000,000 bytes. MP4 cap: 8,000,000 bytes and 0.5–60 seconds.
  These are application limits, not universal X account entitlements.
- MP4 delivery additionally needs the shared inspected-media access implementation
  to admit that verified video. The current native media port accepts only static
  JPEG/PNG objects; MP4 live acceptance therefore remains unavailable.
- NFC and twitter-text v3 weights use the original generated official twemoji
  UTF-16 regex, vendored with its MIT license and immutable source commit in
  `backend/social/adapters/x_vendor/SOURCE.json`. Unknown newer emoji sequences
  retain individual code-point weights rather than speculative grouping.
- Exact URL counting admits explicit ASCII HTTP(S) URLs. Bare domains, credential
  URLs and non-ASCII/IDN URL strings require correction and return a validation
  issue. This narrower application subset avoids claiming full twitter-text URL
  extraction compatibility. Billing detection conservatively recognizes URL-like
  text even outside that admitted subset.
- Animated GIFs, external subtitle tracks, replies/self-threads, edits, delete,
  analytics and arbitrary provider options are not advertised by this slice.
  Captions require a separately accepted media contract; unsupported disclosures
  fail validation instead of disappearing.
- Genuine developer access, user grants, billing/access evidence, reviewed upload
  cost ceilings, live public visibility, real upload acceptance and provider
  eligibility remain external gates. Nothing in fixture success supplies them.

## Verification scope

`backend/tests/social/test_x_adapter.py` uses `httpx.MockTransport` throughout.
It executes restart-after-each-checkpoint text/photo/carousel/MP4 flows, multipart
multi-chunk reconstruction, every-boundary zero-budget refusal, expired/wrong
credentials, stale reservation IDs, target-only definite retries, malformed and
lost responses, no-absence inference, public visibility and t.co/media readback.
It also executes lost-create recovery through one bounded own-post page, rejects
partial/ambiguous pages and dispatch mismatches, and proves exact-ID versus bounded
lookup reservations of 15,000 versus 35,000 microUSD.
These fixtures exercise adapter request construction and interpretation; the
shared worker/budget/connection integration tests provide their own evidence.
