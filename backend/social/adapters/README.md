# Native Meta adapters: source and verification receipt

Issue [#491](https://github.com/Rodgers31/audit_app/issues/491), researched and
tested on 2026-10-08. These modules implement the explicitly injected adapter
boundary for `facebook_pages` and `instagram_graph_facebook_login`. Importing
them registers nothing. Both `enabled` and `operational_gates_verified` must be
explicit `True` values; an async HTTP transport is mandatory. The API and worker
retain their default unavailable-provider behavior.

Registration also requires a persisted native capability snapshot from a
provider-verified connection or reconnect. Injecting the registry cannot upgrade
a legacy unsupported account or relax its recorded publishing, cost, scope or
format limits. Changed admission capabilities require provider verification
before approval and worker dispatch can use them.

## Supported content and source evidence

Graph version is pinned to `v26.0`. Meta's current
[official SDK configuration](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/apiconfig.py)
reports API `v26.0` and SDK `v26.0.2`; this supports the pin, not a claim that
every publishing feature has passed app/account acceptance.

| Product | Implemented content | Admission limits |
| --- | --- | --- |
| `facebook_pages` | Text/link feed post; one inspected static JPEG or PNG attached to a feed post | Application ceilings: 20,000 message characters, 50 separate hashtags, 8,000,000 image bytes, 2,000 alt-text characters. A message or link is required. |
| `instagram_graph_facebook_login` | One inspected static JPEG, caption and alt text | 2,200 full-caption characters, 30 hashtags, 20 mentions, 1,000 alt-text characters, 8,000,000 bytes. Application width range 320–1440; ratio 4:5 through 1.91:1 inclusive. |

Facebook's [Page feed reference](https://developers.facebook.com/docs/graph-api/reference/v26.0/page/feed)
requires a Page token, the `CREATE_CONTENT` task, `pages_manage_posts`,
`pages_read_engagement` and `pages_show_list`. It documents message/link input
and attached media. Its bounded, ranked feed omits some posts, so an empty feed
cannot prove a publication never occurred. The
[Photo reference](https://developers.facebook.com/docs/graph-api/reference/photo/)
documents file attachment or URL input, `published=false`, `alt_text_custom`,
and returned photo/post identities; it limits static images to less than 10 MB.
Our byte and text ceilings are stricter application policy. The
[Page Posts guide](https://developers.facebook.com/documentation/pages-api/posts)
was marked updated April 17, 2026 when read.

The [Instagram media endpoint](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media)
was marked updated September 28, 2026. It documents JPEG, an 8 MB ceiling,
the ratio/caption/hashtag/mention/alt-text limits above, and up/down scaling
outside widths 320–1440. This implementation rejects widths outside that range
instead of relying on provider scaling. Meta specifies sRGB; conversion of other
color spaces is provider behavior. Containers expire after 24 hours, with a
400-container limit in a rolling 24-hour window. The adapter does not normalize
media, support extended JPEG variants, or accept video, Reels, stories, carousels,
disclosures or caption assets.

The [content publishing guide](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
(updated June 30, 2026 when read) requires a professional account linked to a
Page for Facebook Login, describes Page-token calls on `graph.facebook.com`,
and sets 100 API publications in a rolling 24-hour window. This slice requires
`instagram_basic`, `instagram_content_publish`, `pages_read_engagement` and
`pages_show_list`. Quota reads are separate durable poll intents before container
creation and before publication. A lower valid provider quota is honored; missing
configuration uses the documented 100-post ceiling. Container processing is read
at most five times, with a minute between pending reads.

## Durable operations and positive verification

Each `execute` step makes at most one provider call. Facebook image publishing
persists the unpublished photo identity and optional photo-post identity before
the separate feed mutation. Instagram persists the container identity, checks
processing and quota, then persists the final media identity before its readback.
Checkpoints bind adapter/schema, account identity, exact provider identity and
immutable payload hash. Their typed whitelist contains phases, counters and
remote IDs; credentials, media fetch URLs and raw provider responses are absent.

Facebook public confirmation requires a read of the exact retained post ID,
matching Page owner, published/nonhidden state, `EVERYONE` privacy, authorized
message/link, and the uploaded photo attachment where applicable. Its permalink
must bind the exact Page and post in a supported canonical form. Unknown URL
shapes remain unconfirmed. Instagram confirmation requires the retained final
media ID, matching owner, `IMAGE`/`FEED`, authorized caption, and a provider
permalink bound to the returned shortcode. These reads verify provider ownership
and publication evidence; they do not establish a provider-side hash of image
bytes. The server material port binds the exact inspected source bytes instead.

Mutation timeouts, server errors, invalid/conflicting responses and missing
identities become uncertain. They never authorize another mutation through
these adapters. Definitive structured provider rejections can be classified
retry-safe within worker budgets; the HTTP transport has no automatic retries.
Response JSON, IDs, errors, size and compression are bounded and validated.
Only sanitized error classifications escape the transport.

The [IG container reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-container)
(updated July 23, 2024 when read) exposes `id` and processing status, with no
edge mapping a container to a final published media ID. `FINISHED` means ready
to publish; `PUBLISHED` without a retained final ID remains uncertain. Even
`FINISHED`, `ERROR` or `EXPIRED` after an uncertain publish does not supply the
complete absence proof this worker requires. List scans and matching captions
are not used for identity recovery. Unknown uploads/containers/posts need
operator reconciliation. The implementation makes no exactly-once claim.

## Access limitations and operational gates

The research used public, unauthenticated official Meta documentation and
[Meta's maintained SDK source](https://github.com/facebook/facebook-python-business-sdk/tree/main/facebook_business/adobjects).
The web text fetcher returned inaccessible/429 results for several documentation
URLs; public in-app browser accessibility text supplied the endpoint details
above. No account, OAuth, provider mutation, storage or billing call was made.
The SDK corroborates request fields and response models; it cannot verify app
permissions, roles, public visibility or real account behavior.

Meta's token wording is inconsistent: the publishing guide and
[official Meta Postman Facebook-Login collection](https://www.postman.com/meta/instagram/folder/9cgqucg/instagram-api-with-facebook-login)
use Page tokens, while the media/container reference tables include User-token
wording. Business Manager role guidance also differs: the guide mentions both
`ads_management` and `ads_read`, while the endpoint says one of them for that
conditional situation. This implementation follows the agreed Page-token
material contract and does not broaden granted scopes automatically. Conditional
role/scopes, Page Publishing Authorization, Page two-factor requirements, app
review/access mode and real endpoint behavior require operational acceptance.

The guide disallows MPO/JPS JPEG extensions. Existing inspected-media DTOs have
no JPEG-subtype or color-space attestation. The decoder rejects recognized MPO
and animated formats, but a JPEG-shaped JPS may be indistinguishable in this
slice. Ordinary static JPEG/sRGB acceptance must therefore be established by
the operational gate; advertised JPEG support is not a claim that all JPEG
variants are accepted. Real signed-fetch reachability, MIME handling, exact
storage checksum/size, permissions and public readback also remain acceptance
gates. Provider fetch access is freshly minted server-side with at least 120
seconds remaining, bound to asset/hash, and never persisted by an adapter.

## Executed verification

Observed result: 96 native adapter tests passed; the native, worker-policy and
existing connection-provider selection together passed 130 tests. The two
SQLAlchemy deprecation warnings are pre-existing.

The fake provider retains remote state across reconstructed adapter instances.
Tests execute successful Facebook text/image and Instagram JPEG baselines,
restart at every step, accepted mutations followed by lost responses, lost
database checkpoints, positive reconciliation, quota/format/expiry failures,
strict identity and payload fencing, public-proof tampering, hostile JSON and
bounded streams. Foreign-Page and substring permalink regressions were observed
failing before the fix. Malformed material and response regressions were also
observed failing before their fixes. HTTP logs/hooks and material reprs are
checked for fixture secret leakage. These are injected HTTP tests, not live
provider acceptance or PostgreSQL durability tests; root integration owns the
database/worker checks.

Run from `backend`, with the backend directory on `PYTHONPATH` for the existing
provider tracing test's repository-root subprocess:

```sh
python -B -m pytest -p no:cacheprovider tests/social/test_native_meta_adapters.py tests/social/test_worker_policy.py tests/social/test_connections_provider.py -q
```
