# TikTok Accounts API candidate contract

Inspected 16 October 2026. This is a local implementation candidate, not granted provider access, a deployed feature, or live acceptance. The human's publishing/upload controls remain off. No TikTok API account, grant, token, URL-property verification, paid resource, post, draft upload or webhook subscription was created.

## Product and source boundary

The implemented product is `tiktok_accounts_api`, pinned to API for Business **v1.3**. It is not the consumer Content Posting API. Standard Direct Post is unsuitable for the blueprint's internal owned-account utility; its current guidelines explicitly exclude that use. A consumer account change, a `video.publish` string, or the presence of platform literals cannot establish Accounts API access. `TikTokAdapterConfig` and account approval evidence must explicitly admit the genuine approved product. Every new configuration flag defaults false. Source documentation does not prove that AuditGava has approval or no-cost commercial terms.

Official primary sources, inspected through a dedicated Chrome documentation tab (closed after inspection):

- [Accounts API overview](https://business-api.tiktok.com/portal/docs/accounts-api-overview/v1.3)
- [Accounts authorization](https://business-api.tiktok.com/portal/docs/accounts-api-authorization/v1.3)
- [Accounts authentication and rotation](https://business-api.tiktok.com/portal/docs/accounts-api-authentication/v1.3)
- [Owned-account video publication](https://business-api.tiktok.com/portal/docs/publish-a-public-video-post-to-an-owned-account/v1.3)
- [Owned-account photo publication](https://business-api.tiktok.com/portal/docs/publish-a-photo-post-to-an-owned-account/v1.3)
- [Current account privacy settings](https://business-api.tiktok.com/portal/docs/get-the-post-privacy-settings-of-a-tiktok-account/v1.3)
- [Asynchronous publishing status](https://business-api.tiktok.com/portal/docs/get-the-publishing-status-of-a-tiktok-post/v1.3)
- [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines) (page identifies its latest update as 4 August 2026)

## Implemented HTTP contracts

All API paths below are relative to `https://business-api.tiktok.com/open_api/v1.3/`. Every HTTP boundary uses one bounded request, without redirects or automatic wire retries. Tokens are in `Access-Token`, never persisted in delivery checkpoints. Duplicate JSON keys, oversized or malformed responses, unexpected compression, redirects and server uncertainty cannot prove rejection of a mutation. Raw provider prose, URLs and exception messages do not enter error receipts.

| Purpose | Method/path | Verified inputs/outputs |
| --- | --- | --- |
| Exchange | POST `tt_user/oauth2/token/` | `client_id`, `client_secret`, `grant_type=authorization_code`, `auth_code`, exact `redirect_uri`; validate returned `open_id`, Bearer type, scopes, access/refresh tokens and returned expiries |
| Rotation | POST `tt_user/oauth2/refresh_token/` | `client_id`, `client_secret`, `grant_type=refresh_token`, `refresh_token`; reject changed `open_id`, retain returned refresh token and actual remaining expiry |
| Current choices | GET `business/video/settings/` | `business_id=open_id`; normalize account privacy options, interaction restrictions and maximum video duration |
| Video | POST `business/video/publish/` | Bound `business_id`, verified `video_url`, explicit `post_info`; persist returned task `share_id` |
| Photos | POST `business/photo/publish/` | Bound `business_id`, up to 35 verified `photo_images`, explicit `post_info`; persist returned task `share_id` |
| Status | GET `business/publish/status/` | Exact `business_id` and `publish_id=share_id`; only nonempty valid `post_ids` with completed status establish public availability |

The OAuth helper requires the actual static authorization URL configured in TikTok's application console to contain the exact registered redirect_uri. It adds opaque state and `disable_auto_auth=1`; it does not invent product scopes or a client authorization URL. The account-holder redirect contract requires HTTPS, a trailing slash, no port, query or fragment. The durable connection service owns single-use state consumption, encryption, refresh leases and credential-version compare-and-swap. A helper's successful token response is not durable credential acceptance. The refresh endpoint's exact current request table/example omits `redirect_uri`, despite generic overview wording covering token security; the implementation follows that table and makes this distinction explicit.

## Durable publication behavior

`TikTokAccountsAdapter` implements the existing `capabilities`, `validate`, `validate_mutation_admission`, `next_operation`, `execute`, and `reconcile` ports. It introduces no publisher state store or in-memory retry queue. Every checkpoint is bound to account UUID, external account ID, immutable content hash, workflow mode and schema version.

The operation chain is current-settings read → public-capable `publish` for direct mode or nonpublic `upload` for draft mode → task status reads. Creator choices are frozen in `tiktok_options` and participate in the authorized payload hash. The preflight settings must match the reviewed account-bound settings hash. The dispatch preflight remains valid for five minutes. Older authorized creator choices are accepted only after a fresh provider settings read produces the exact same account-bound hash; future-dated review timestamps are rejected. This permits delayed worker dispatch without treating stale settings as current, while changed settings require re-review. Approved unattended workflow permission remains an external product gate.

Direct video is a public owned-account endpoint, so the creator must explicitly select public privacy. Photo privacy is sent explicitly; the current application payload contract also requires public direct results. Comments, Duet and Stitch default disabled. Commercial disclosure defaults off and requires at least one explicit brand selection when enabled. Branded content requires policy consent and cannot be private. Upload consent and Music Usage Confirmation are mandatory before media URLs are obtained. The approved token must have `video.publish` for direct mode or `video.upload` for draft mode. Photo Duet/Stitch and undocumented photo AI disclosure are refused. Separate accessibility metadata is refused rather than silently discarded; baked-in video captions remain possible.

The media provider port must return the exact inspected asset ID/hash and at least a 30-minute URL lifetime. Every returned URL must match a provider-verified HTTPS origin/path prefix held in ephemeral server material. Suffix hosts, path escapes, credentials, nonstandard ports and unverified properties are refused. Only exact host and slash-terminated path-prefix matching is used. Redirect following is disabled; provider-origin acceptance itself remains a live gate.

Inspected video limits include 3–600 seconds (further restricted by current account settings), the conservative 100 MB application ceiling (provider maximum 1 GB), dimensions at least 360 pixels, allowed container MIME types and actual inspected 23–60 FPS. Photo limits include JPEG/WebP, the conservative 8 MB application ceiling (provider maximum 20 MB), at most 35 images and documented dimensions. Captions/title use UTF-16 code-unit counting, with the rendered hashtags included. The lane's shared worker must enforce six submissions/minute and 15/day across direct and draft durable attempts under the account lock; adapter capability limits alone are not quota enforcement.

## Status and recovery semantics

- URL download and completed processing without public IDs remain processing. Post IDs can lag completion by three minutes; polling observes that interval.
- Completed status with nonempty valid public `post_ids` confirms public visibility. No username permalink is fabricated.
- Inbox delivery is `visibility_state=manual_action`, with `MANUAL_ACTION_REQUIRED`. It retains `share_id`, stops automatic delivery and requires completion in TikTok. It is not Published.
- A known task reporting failed is retained as a failed task. It does not establish permission to resubmit the original intent automatically.
- A lost acknowledgement before durable `share_id` remains unknown. Caption matching and a second upload cannot recover that identity. No absence proof is fabricated.
- Reconciliation queries only the exact stored task under the bound account token. It refuses status and recovery when configured product/access gates are off, and still requires valid unexpired credentials and immutable identity. It never sends new media.
- Twenty bounded status checks lead to unresolved verification; ownership/history is retained. No infinite poll or forced clearing is added.

## Verification and limits

The adapter, HTTP/OAuth helpers and integrated pipeline were revised after the original subtask runs. The old fixed-path capture producers and their77/28-test receipts are **SUPERSEDED for current acceptance** and must not be replayed to overwrite that history. See [EVIDENCE_STATUS.md](EVIDENCE_STATUS.md), [IMPLEMENTATION.md](IMPLEMENTATION.md), and the final exact-source records linked from checkout HANDOFF.md. Earlier test counts remain historical only.

Signed Threads/TikTok event verification, durable deduplication, bounded status-only consumption and audited retention are now integrated by the parent. Genuine subscription/product acceptance remains external. Default-off recovery, exact OAuth callback validation and uncapped Retry-After date/delta handling are covered by retained observed-red regressions followed by final normal/optimized tests. TikTok future-delivery permission is separately gated at admin and worker mutation boundaries; no deployment or actual workflow approval was inferred.

The delayed-choice regression is preserved in `tiktok-delayed-red.txt`: the initial candidate incorrectly rejected an authorized three-hour-old choice even when fresh current settings matched exactly. The corrected fixture passes, while a stale five-minute dispatch checkpoint and a future review timestamp still refuse mutation. `platforms-pg-first-red.txt` preserves the initial native URL-lifetime integration failure plus an incorrect fixture assumption that authenticated Threads readback established public visibility. Current Threads expectations retain unknown visibility; they do not manufacture public proof. Other intermediate outputs are historical fixture-development runs, not current acceptance evidence.
