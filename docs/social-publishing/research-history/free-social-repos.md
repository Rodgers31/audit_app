> **Historical record — 2026-10-03.** Preserved from the earlier task artifact. Read the [current engineering blueprint](../ENGINEERING_BLUEPRINT.md) and [low-cost amendment](../LOW_COST_OPERATING_PROFILE.md) before implementation. Earlier paid-provider preferences and preliminary TikTok conclusions may be superseded. Source text is retained; local links were made portable. Private browser screenshots are not copied into the repository.

# Free social publishing options for AuditGava

Read-only research, checked 3 October 2026. No installation, live publishing test, account change, application edit, or PR change was performed. Source coverage does not prove a platform will grant AuditGava API access.

## Recommendation

Build AuditGava's own approval, evidence, scheduling and delivery ledger in the existing Python/FastAPI/Postgres backend. Use small replaceable native API adapters, optionally backed by a proven free library. This best matches the requirement for the custom admin already proposed and avoids a paid publishing subscription or a second full social-management application. We still maintain the platform connections, permissions, token handling and API-version changes.

Social SDK is a free MIT-licensed option for some adapters, not the demonstrated best universal choice. It needs a Node service in this Python architecture, has no direct Facebook adapter and does not cover the inspected TikTok Business route. It does not remove our own workflow work. The inspected public release is `@opencoredev/social-sdk@0.5.0` (24 September 2026); main has additional changes through 29 September. [SDK release](https://github.com/opencoredev/social-sdk/releases/tag/%40opencoredev%2Fsocial-sdk%400.5.0), [SDK source and license](https://github.com/opencoredev/social-sdk).

If we want a complete existing free publishing engine instead of implementing adapters, **Postiz self-hosted is the strongest alternative examined**. Treat it as a separate service behind FastAPI, rather than copying its providers into AuditGava. It has much wider native source coverage, including Facebook and TikTok Business, but adds considerable operations and licensing considerations. This is an assessment from documentation and source, not a live integration comparison.

## Source-confirmed comparison

| Option inspected | Facebook Pages | Instagram | Threads | TikTok | X | Fit for AuditGava |
|---|---|---|---|---|---|---|
| Postiz `v2.25.0` | Direct provider | Facebook-linked and standalone providers | Direct provider | Standard and Business providers | Direct provider | Strong free self-hosted engine, separate service required |
| Mixpost Lite `2.6.0` | Direct provider | Missing in Lite | Missing in Lite | Missing in Lite | Direct provider | Does not meet the free all-five requirement |
| Official Meta Python Business SDK `26.0.2` | Generated feed/photo/video/Reels methods | Generated media creation/publishing and insights methods | No Threads publishing methods in inspected source | None | None | Useful narrower free Python component; supplement with direct APIs |
| Social SDK `0.5.0` / pinned main | No direct adapter | Direct adapter | Direct adapter | Standard route; Business route gap | Direct adapter | Optional TypeScript component, not mandatory foundation |

## Postiz self-hosted

- Latest release inspected: **v2.25.0**, published 2 October 2026, source tree `8e42f09cb45c3b6be16656c2d23a372d5eb21053`. Current repository activity continues 3 October. Frequent fixes show maintenance; they do not establish production correctness. [Release](https://github.com/gitroomhq/postiz-app/releases/tag/v2.25.0).
- Provider registration actually instantiates Facebook, Instagram, Instagram standalone, Threads, TikTok, TikTok Business and X adapters. [Registry](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/libraries/nestjs-libraries/src/integrations/integration.manager.ts#L40).
- Facebook source implements Page discovery and feed/photos/video publishing. Threads source creates containers, publishes, refreshes tokens and reads insights. These are working implementations to examine, not just names in a README. [Facebook implementation](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/libraries/nestjs-libraries/src/integrations/social/facebook.provider.ts), [Threads implementation](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/libraries/nestjs-libraries/src/integrations/social/threads.provider.ts).
- TikTok Business source calls `business-api.tiktok.com/open_api/v1.3` for OAuth/token refresh, photo/video publishing and status checks. It returns a pending result after acceptance so workflows poll instead of holding a blocking upload call. This makes it materially more relevant than a standard TikTok-only adapter. It still requires eligible Business API app access and verified HTTPS media hosting. [Business provider](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/libraries/nestjs-libraries/src/integrations/social/tiktok.business.provider.ts#L665).
- FastAPI can call its HTTP API using a server-only API key. Source includes account connection, integration listing, upload, post creation and delivery/history-related endpoints. No need to import the Postiz application into the browser or Python process. [API controller](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/apps/backend/src/public-api/routes/v1/public.integrations.controller.ts), [HTTP API](https://docs.postiz.com/public-api/introduction).
- The publishing API is not a paid-only self-host feature: authorization source bypasses subscription limits when Stripe billing is unconfigured. Self-host documentation explicitly distinguishes the subscription-free deployment from Cloud. [Authorization source](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/apps/backend/src/services/auth/permissions/permissions.service.ts#L50), [Cloud versus self-host](https://docs.postiz.com/cloud/overview).
- Operational footprint: Node/Nest/Next application, its database, Redis and Temporal. Docs list a small-use floor of 2 vCPU/2 GB and recommend 4 vCPU/8 GB; official Compose includes the supporting services. We would operate and back up a second application's state. [Requirements](https://docs.postiz.com/self-host/installation/system-requirements), [Compose source](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/docker-compose.yaml).
- The license is **AGPL-3.0**, not MIT. Preserve license notices and assess obligations before modifying or copying its code; a service boundary is preferable to indiscriminate source reuse. [Exact license](https://github.com/gitroomhq/postiz-app/blob/v2.25.0/LICENSE).
- Core self-hosted publishing is free software; optional services are not automatically free. Its embedded Polotno design editor requires a production commercial license, and AI/media generators require their own credentials and potentially costs. We can omit those and use AuditGava's own deterministic graphics. [Polotno requirement](https://docs.postiz.com/self-host/configuration/polotno), [Self-host feature distinction](https://docs.postiz.com/cloud/overview).
- Its approval feature is preview/comment review, not an enforced approval state. AuditGava still needs its own revision-bound approval gate and should submit only approved deliveries. Keep scheduling in AuditGava until due time if our kill switch must prevent handing future work to another scheduler. [Approval limits](https://docs.postiz.com/general/approvals).

## Mixpost Lite

Latest inspected release **2.6.0**, 16 March 2026; MIT-licensed Laravel/PHP package. The free registry contains precisely `twitter`, `facebook_page`, `mastodon`, and the package requires PHP 8.2/Laravel/Horizon. It adds another language/runtime without solving all required platforms. [Release](https://github.com/inovector/mixpost/releases/tag/2.6.0), [Provider registry](https://github.com/inovector/mixpost/blob/2.6.0/src/SocialProviderManager.php#L26), [Manifest and license declaration](https://github.com/inovector/mixpost/blob/2.6.0/composer.json).

Official pricing lists Instagram, Threads and TikTok, plus API/webhooks/approval and advanced automation, under paid Pro/Enterprise. A self-hosted product can still have paid feature gates; Lite does not satisfy this request without extensive new implementation. [Official feature tiers](https://mixpost.app/pricing).

## Official Meta Python Business SDK

Latest inspected release **26.0.2**, 21 September 2026. Its generated Page object has `create_feed`, `create_photo`, `create_video`, `create_video_reel` and insights endpoints. IGUser has `create_media`, `create_media_publish`, insights and content-publishing-limit reads. This is useful directly inside a Python publishing adapter. [Release](https://github.com/facebook/facebook-python-business-sdk/releases/tag/26.0.2), [Page source](https://github.com/facebook/facebook-python-business-sdk/blob/26.0.2/facebook_business/adobjects/page.py#L2222), [Instagram source](https://github.com/facebook/facebook-python-business-sdk/blob/26.0.2/facebook_business/adobjects/iguser.py#L932).

The present ThreadsUser object only defines profile fields: it is not a Threads publishing adapter. We would call Threads' native API separately. This SDK also does not supply TikTok/X publishing, an admin queue, approval policy, durable scheduling or a production credential vault. [ThreadsUser source](https://github.com/facebook/facebook-python-business-sdk/blob/26.0.2/facebook_business/adobjects/threadsuser.py).

The exact license is a custom **royalty-free license for use with Facebook web services/APIs**, with notice preservation and platform-policy conditions; do not describe it as MIT. Do not follow the README's legacy permission examples without checking current platform documentation. [License](https://github.com/facebook/facebook-python-business-sdk/blob/26.0.2/LICENSE).

## What free means

We can avoid a publishing-service subscription, but hosting/storage/maintenance remain ours. None of these repositories grants platform approvals, bypasses rate limits or removes social API fees. X currently uses paid usage/credits, with writes and URL-bearing posts charged differently. For a strict zero-X-API-cost plan, generate a ready-to-publish X draft and let an admin post it in the native app. [X official pricing](https://docs.x.com/x-api/getting-started/pricing).

## Integration models in plain language

1. **Recommended custom Python route:** AuditGava admin → FastAPI approval and queue → worker → Facebook/Instagram adapter (optional official Python SDK), Threads adapter, eligible TikTok Business adapter, X adapter if funded → platform receipts. We build the product workflow; free libraries merely save endpoint code.
2. **Optional supplied SDK route:** same AuditGava workflow → private Node publishing service importing the pinned npm package → supported native APIs, plus our Facebook and TikTok Business implementations. No managed paid provider is inherently required, but SDK holes still need filling.
3. **Ready-made engine route:** same AuditGava workflow → our self-hosted Postiz HTTP API → platform APIs. We host Postiz and register the platform apps; its own scheduler/delivery behavior must be validated and reconciled into our ledger. The SDK is not needed just to call Postiz from Python.

Choose route 1 for a cohesive, small AuditGava implementation; route 3 if saving initial adapter work outweighs operating another service. Do not call the supplied SDK the best option without controlled connection/publishing tests. Start by proving Facebook + Instagram + Threads API access, investigate TikTok Business eligibility, and leave X/manual export available when zero spending is required.
