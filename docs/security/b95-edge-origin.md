# Edge and origin defense proposal — 26 October 2026

Related: [809](https://github.com/Rodgers31/audit_app/issues/809),
[767](https://github.com/Rodgers31/audit_app/issues/767),
[699](https://github.com/Rodgers31/audit_app/issues/699).
Source baseline: `6fdce855950e94cb30c43dfdcd8307885795b3cf`, tree
`90724835b5e36a99677314a39f5078e52944d76c` (merged PR816).

## Decision and evidence limits

Preserve the current registrar → Vercel frontend and public Render API topology.
Keep existing automatic Vercel DDoS mitigation, backend admission, authentication,
signed requests and the existing $1 team pausing exception. No new zone, proxy,
resource, credential, metered feature or activation is proposed for immediate use.
This adds a reviewable inventory and bounded dummy fixtures, not an installed WAF.
No application defect is repaired; there is no claimed product RED→GREEN fix.

The coordinator's retained B94 account readback reports Cloudflare Domains empty,
R2 private/no custom domain/r2.dev disabled, and Vercel Firewall active/System
Mitigations Active/custom rules 0/Bot Protection inactive. Those are retained
observations, **not fresh account verification by this author**. Fresh public DNS
read here returned `dns1.registrar-servers.com`, `dns2.registrar-servers.com` and
www CNAME `1a43f65714264e77.vercel-dns-017.com`. DNS supports the topology but
does not prove effective firewall rules, all aliases, origin routing or billing.
Chrome is reserved; no live endpoint/availability/exploit probe was performed.

## Request paths and effective boundaries

Paths below are source traces at the pinned baseline. Deployment-specific targets
must be read back; do not treat environment variable defaults as installed values.

| Caller and route | Effective layer and application contract | Bypass/qualification boundary |
|---|---|---|
| Browser → www/apex or project aliases → Next pages, static files, images | Vercel automatic DDoS then Next/middleware; apex redirect in `frontend/vercel.json:8`; session middleware in `frontend/middleware.ts:4` | Default Vercel/project aliases must be included in any project rule. Image optimization and successful traffic can incur ordinary usage. No geo/UA blanket block proposed. |
| Browser → `/api/v1/*` on frontend | Vercel → build-time external Next rewrite (`frontend/next.config.js:73`) → Render → required resource/rate middleware → route auth | Rewrite is not proof all browser API traffic takes this route. Vercel rules end at this entry point. |
| Browser API client and server-side fetch → configured API base | `frontend/lib/api/base.ts:4` uses public URL in browser; server can use INTERNAL_API_URL; Axios appends `/api/v1` (`frontend/lib/api/axios.ts:21`) → Render guards | Direct API requests can bypass Vercel entirely. Inspect baked browser URL, rewrite destination and server override separately. CORS restricts browser reads, not curl/abuse/origin reachability. |
| Direct public `audit-app-4pwa.onrender.com` → any API/admin route | Render public web-service ingress → one worker/socket-peer budget + aggregate/resource bounds → public route or JWT/role authorization | Existing default origin remains reachable per retained topology. Its current platform filtering is not measured here. Adding a custom domain alone does not remove direct entry. |
| Browser auth/recovery and `/api/auth/reset-password`; `/auth/callback`, `/reset-password` | Vercel → Next route / Supabase PKCE/session logic | FastAPI guard never wraps these Next handlers. Body/admission and recovery collector repairs belong to frontend lane/809/767. Do not challenge this entire flow. |
| Legacy Meta/platform callback on Next | Vercel first collectors → existing callback containment/session completion | Existing connection hold stays. Scrubbing later cannot erase first-collector query retention (767). No real code/state may be used for qualification. |
| Direct Meta launch POST and callback GET `/api/v1/social/oauth/meta/{launch,callback}` | Render → guards → exact target check, bounded fields, per-flow state/cookie, encrypted staging; exchange needs admin session (`backend/social/connections/direct_api.py:50`, `direct_callback.py`) | Hold remains. Exact target uses `request.url`; with forwarding disabled a proxy may expose HTTP scheme. Real TLS termination/Host/scheme and first collectors require validation before this flow can activate. Do not fix this by trusting arbitrary headers. |
| Meta privacy deletion/deauthorization POST and deletion status GET | Configured ingress → Render guards → signed-form privacy handler (`backend/social/privacy/api.py:10`, `:73`); status has opaque code, private headers | No interactive challenge; preserve raw form bytes. Source router registration/configuration must be read back. Status capabilities and callback queries must not enter new logs/caches. No rate exemption based on provider UA/Origin. |
| Platform webhook POST `/api/v1/social/platform-events/{provider}` and Threads verification GET `/api/v1/social/platform-events/threads` | Configured ingress → Render guards → signature/receipt handling for POST; verify-token and numeric challenge for GET (`backend/social/platform_events.py:328`) | Feature/config admission remains held; trace exact registered provider path before future rollout. Preserve signed raw bytes and legitimate GET verification; no global bypass for a header named signature. |
| GitHub freshness/cache job | Workflow first HMAC POST to direct `/api/v1/system/cache/invalidate`, then HMAC POST to www `/api/revalidate` (`.github/workflows/seed.yml:1142`, `:1164`, `:1179`) | Backend checks raw HMAC and 300s timestamp skew (`backend/routers/cache_invalidation.py:39`); Next verifies raw HMAC (`frontend/app/api/revalidate/route.ts:23`). A header's presence is not authentication. No browser challenge, GitHub IP bypass or new dispatch. |
| Health probes GET/HEAD `/health`, `/health/live`, `/health/ready` | Render/uptime monitoring → exact cheap-health exception (`backend/middleware/request_resources.py:34`) → health handlers (`backend/main.py:2282`) | These exact method/path pairs bypass rate admission. `/health/detailed`, suffixes and POST do not. Do not expand exception to all health-like names or loopback/forwarded IPs. Cheap does not mean edge-DDoS proof. |
| Pipeline monitoring GET `/api/v1/system/pipeline-health/v2` and legacy `/api/v1/system/pipeline-health` | Render guards → v2 has `_status_require_admin` (`backend/main.py:2572`); legacy decorator/handler has no auth dependency and caches for30s (`:2584`) | Both remain subject to coarse admission; neither is cheap-health exempt. Read actual external monitor URL/method before any host/rule change. Public legacy health is not, by itself, a confirmed disclosure finding. |
| Possible Prometheus scrape `/metrics` | `backend/monitoring/instrumentation.py:353` defines `setup_prometheus`; source search finds no backend caller | Helper existence does not establish a mounted route. Installed route/ENABLE_METRICS state and authorized scraper remain needs-validation; no fabricated metric access rule or IP allowlist. |
| Browser analytics/Speed Insights and backend Sentry export | Separate outbound collector path: root layout mounts Analytics/SpeedInsights (`frontend/app/layout.tsx:123`); Sentry requires explicit opt-in (`backend/monitoring/startup.py:15`) and filters in `instrumentation.py:273` | WAF is not query redaction. Current collector settings and callback/recovery omissions remain needs-validation; no new drain, exporter or paid Observability enabled. |
| Browser → Supabase auth/data; backend/worker → providers, DB and private R2 | Separate service authorization/storage boundaries, outside frontend WAF; R2 CORS is not an origin firewall | R2 existence does not put Cloudflare WAF in front of www or Render. Publishing/uploads/native/supervision and callback activation remain OFF/held. No provider or storage operation executed here. |

## Identity contract and bounded local proof

`backend/social_worker_supervisor.py:16` pins one worker and
`--forwarded-allow-ips ''`; Docker's alternate command pins
`--no-proxy-headers` (`backend/Dockerfile:42`). The rate middleware takes
`request.client.host` or the shared `unknown` bucket, never X-Forwarded-For,
Forwarded, X-Real-IP, CF-Connecting-IP, Host, Origin, UA or a signature header
(`backend/middleware/security.py:82`). Loopback is not rate-exempt.

`install_security` sets 600/peer and 900/process per 60s (`security.py:266`);
resource defaults include 8 in-flight/4 body consumers and 32MiB body/query
32KiB/header 32KiB (`request_resources.py:16`). These are application budgets,
not transport connection limits. Do not lower global body size without preserving
legitimate social documents and signed provider envelopes. Single process state
resets on worker recycle/restart and is not an end-user/distributed quota. Shared
Render/Vercel proxy peers can consume one coarse bucket; peer cardinality and
fairness cannot be inferred from a dummy loopback request.

`b95-edge-origin-contract.py` exercises the actual middleware with inert principals:
forged forwarding/Origin/UA headers, loopback, missing peer, distinct peers sharing
aggregate budget, provider-like paths, exact health exception and fresh middleware
instance reset (no actual OS process restart exercised).
Its real TCP Uvicorn check contrasts trusted-proxy `''` with deliberately unsafe
`'*'`: the latter accepts changing XFF identities. This is a negative control,
**not an exploit of installed production**. Unittest checks still execute under
Python `-O`. Existing `test_proxy_admission_chain.py` additionally parses the actual
Gunicorn command under hostile GUNICORN_CMD_ARGS. The fixture uses tiny 2/3
budgets, not a production load/capacity benchmark; dummy provider paths do not
execute provider signature or callback handlers.

Run only in an OS-enforced sandbox: no external network/credentials/socket mounts;
empty allowlisted environment, UID65534, read-only source/toolchain/root; private
loopback, scratch tmpfs512MiB, memory768MiB, 1CPU, pids192, files256, file64MiB,
CPU120s, wall160s. Use the trusted coordinator-derived wrapper outside the repo
with cached image/toolchain; never execute this fixture directly on the host.
Exact commands, image digest, file hashes and outputs belong in the author handoff.

## Smallest no-extra-cost design and optional draft

Recommended setting delta: **none** until effective readbacks and coordinator
release finish. Preserve Vercel DDoS/System Mitigations, existing backend guards,
one-worker/no-forwarded identity and existing budget pause. No broad bypass,
provider IP allowlist, geographic restriction, Bot activation or universal challenge.

`b95-edge-origin-settings.json` is explicitly disabled and is **not provider API or
Terraform syntax**. It pins one optional Vercel dashboard proposal: exact path is
`/api/revalidate` OR `/api/auth/reset-password`, AND method is neither POST nor
OPTIONS → log first; only after qualification consider deny. It adds no rate-limit
feature or persistent action. All project hosts, no Host/header-derived identity,
no bypass rule. It only rejects unsupported methods; it cannot bound expensive
valid POSTs, direct Render traffic, payload size or callback privacy. Frontend
owner must confirm HEAD/OPTIONS/slash normalization and intended methods first.
Do not copy into `vercel.json` or publish it as part of merging these docs.

Legitimate exceptions are narrow **non-matches**, not trusted identities: this
optional rule does not match GET callbacks, privacy/webhook paths, ordinary API,
health, assets or public pages; matching POST and OPTIONS pass this rule and still
face all existing authentication and system mitigations. Valid GitHub POSTs must
continue reaching HMAC verification. A caller can forge Origin/UA/headers and still
receives no global bypass. A future emergency Attack Mode needs its own bounded
approval because automated clients may not solve its challenge.

## Included features and cost evidence

Official pages retrieved 26 October 2026; recheck before applying. No dollar saving
or unbounded cost immunity is claimed; current account usage/entitlements are not
re-measured. This is a limited topology proposal, not a metric-backed
vercel-optimize performance audit; no Observability Plus collection or purchase.

| Option | Current official evidence | Decision/caveat |
|---|---|---|
| Existing Vercel automatic DDoS | [DDoS mitigation](https://vercel.com/docs/vercel-firewall/ddos-mitigation): all deployments/plans; blocked attack traffic not charged | Retain. Detection is not a guarantee every abusive request is blocked. |
| Vercel custom rule | [WAF limits](https://vercel.com/docs/vercel-firewall/vercel-waf): Pro up to40 custom rules; [current pricing](https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing) says included controls free and WAF-mitigated deny/challenge/rate-limit traffic has no CDN/FDT charges | Optional disabled draft fits retained zero-rules state. Passed challenges/allowed traffic incur ordinary usage; log-only traffic still reaches app. Current page supersedes older search excerpt claiming blocked custom rules incur ER/FDT. |
| WAF rate limit / managed rules | [Pricing](https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing): rate limiting displayed $0.50/million allowed; OWASP $0.80/million inspected +$0.20/GB | Exclude metered features entirely; regional prices/allowances must not be read as a zero-cost commitment. |
| Vercel budget pause | [Spend Management](https://vercel.com/docs/spend-management): team/billing-cycle control; pausing must be enabled separately from alerts | Existing $1 exception preserved; no higher threshold or new webhook. It affects team projects and availability, not Render/R2/Supabase; do not promise exact all-service billing cap. |
| Cloudflare Free WAF/DDoS | [WAF availability](https://developers.cloudflare.com/waf/): Free managed subset and one rate-limit rule; [custom rules](https://developers.cloudflare.com/waf/custom-rules/); [proxy status](https://developers.cloudflare.com/dns/proxy-status/) | No zone/proxy in current retained web path. Do not infer protection from R2. [Vercel proxy cautions](https://vercel.com/docs/security/reverse-proxy) describe reduced visibility/identity and usage risks. No zone/Worker/Tunnel or nameserver change. |
| Render custom/default domains | [Custom domains](https://render.com/docs/custom-domains): Hobby2/Pro15/Scale25 included; additional $0.25/domain/month; TLS automatic; default subdomain can be disabled only with a custom domain | Account domain allocation unverified. Even within allowance, new DNS/domain is outside scope and custom domain remains publicly reachable. |
| Private R2 | [Public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/), [pricing](https://developers.cloudflare.com/r2/pricing/): Standard storage $0.015/GB-month, ClassA $4.50/million, ClassB $0.36/million; internet egress free | Zero egress does not mean zero operation/storage cost. Preserve private bucket/no r2.dev/no custom domain and existing exact-origin CORS; no upload or new worker. |

## Direct-origin alternatives and why none is applied

1. **Keep public Render with current guards (recommended now).** Supports direct
   browser/API, signed GitHub calls and existing callbacks/health. Remaining public
   bandwidth/connection and shared-peer limitations stay visible under809.
2. **Custom API domain + disable onrender.** Removes one hostname, not public origin
   access: an attacker can call the custom domain. Changes baked URLs, CORS, OAuth
   exact redirects/cookies, privacy status/return URLs, GitHub variables, monitoring
   and health routing. Requires allocation/DNS/certificate/callback validation;
   cannot be sold as an edge-only boundary or undertaken in this author lane.
3. **Force all API through Next with origin authentication.** Needs a separately
   authenticated proxy→API boundary and removal of public browser dependence.
   Host/Origin/Referer/XFF/UA alone cannot implement that boundary; a new shared
   secret/header or access control is outside scope. Direct provider ingress needs
   a separate signed path and health exception; callback query collector issue767
   prevents routing all callbacks through Vercel as a shortcut. Proxy transfer and
   invocations can also add usage.
4. **Private Render service / IP restrictions / Cloudflare-only origin.** Existing
   Vercel and provider callers need a verified route and authenticated boundary.
   Render [web services](https://render.com/docs/web-services) distinguishes public
   services from private services. No new service/Tunnel/static-egress purchase,
   credential or shared vendor CIDR trust is authorized. A vendor proxy IP range
   alone does not authenticate this application's traffic.

## Pending readbacks, before/after plan and rollback

After the coordinator releases Chrome, use only its existing profile and exact
project/account. Read without saving: Vercel production+alias hostname list,
effective firewall version/rules/bypass/persistent actions/Bot state, included
feature prices, existing team pause threshold/action, Preview tracking and repo+
personal automatic-review controls; Render service start command/instance count,
custom/default host policy, health path and collector/drain configuration. Capture
only non-secret target hosts and flags, never environment values wholesale. Read
baked public API/rewrite/SSR target; registered OAuth/privacy/webhook/monitor URLs,
TLS→ASGI scheme and actual socket peer require coordinator-approved matched inert
observations. No real provider credentials/query codes or log exports.

Before optional rule activation, record previous firewall version, exact resolved
conditions/action and pending changes; stop if any metered/add-on dialog, unrelated
pending setting or missing entitlement appears. Observe ten minutes passively in
Log first using aggregate counts and path/method/status only. New Log records must
not collect sensitive bodies/queries. No synthetic live traffic is authorized here.
Coordinator may separately approve a tiny inert method matrix; preserve originals
for callbacks, privacy/webhooks and signed GitHub calls using local fixtures first.

For an approved deny transition, inspect immediately and at10minutes: ordinary
pages/API success, valid POST/OPTIONS outcomes, callback/health failures, new deny
counts and ordinary usage. Abort on any legitimate client refusal, health regression,
unexpected redirect/challenge, sensitive-query logging or billing prompt/change.
Rollback: existing project → Firewall → View Audit Log → select recorded previous
version → Restore → Restore Configuration, then read back exact conditions/state.
Alternatively disable only the named rule and publish after reviewing the complete
pending diff. Reverting a docs commit does **not** roll back live firewall state.
No DNS/Render setting is changed by this proposal, so none needs unwinding here.

809 remains OPEN: local trust checks do not qualify deployed peers, collector
privacy, sustained capacity, all route workloads, costs or provider acceptance.
767 and699 remain separate. No new duplicate issue, no merge/deploy/admission,
dispatch/cancel/schedule change, publishing/upload/native activation or live
security/billing/access/DNS mutation is part of this document.
