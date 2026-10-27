# Next request bounds and recovery privacy

Scope: #809 and the ordinary-auth extension of #767/#488. Base is merged PR816,
`6fdce855950e94cb30c43dfdcd8307885795b3cf`. This is source/local qualification;
no deployed vulnerability, credential theft or PKCE bypass is claimed.

## Request contract

`/api/revalidate` still verifies lowercase hex HMAC-SHA256 over the exact raw
body bytes with a timing-safe comparison and uses the shared path manifest.
Missing/ill-shaped signatures are rejected before reading. Both POST routes
read at most 8192 bytes, counting actual streamed bytes independently of
Content-Length; overflow is 413. Malformed UTF-8/JSON, null, scalars and arrays
are refused as objects. Revalidation allows at most 64 string entries, each
256 characters, and calls each distinct allowed path once. Unknown string
paths remain in `rejected`, as the existing workflow expects. No manifest or
workflow changes are required.

Body reading has a five-second deadline. Cooperative boundaries check monotonic
elapsed time as well as the abort timer, and more than sixteen consecutive
zero-byte chunks are refused as a no-progress stream. Revalidation has a five-second total
application deadline and a ten-second platform `maxDuration`. Reset has a
15-second total application deadline and a 20-second `maxDuration`; the same
abort signal reaches every Supabase fetch and its response-body reader. Auth
responses are capped at 128 KiB. Caller abort is 408; whole-request deadline is
504; saturation is 503, without a queue. Synchronous JS cannot be preempted by a
timer; bounded body/list sizes limit that work. A provider may have completed a
password update before a connection times out: there is no automatic retry or
claim that abort reverses a remote effect.

Admission allows four revalidation and eight reset operations in one warm JS
instance. Reset also refuses a simultaneous same-code hash with 409. Only
active hashes are held, at most eight; no password, raw code, identity registry
or durable replay state is retained. Ownership stays with actual SDK work
until it settles, even if response timeout happens first. A dependency ignoring
abort can occupy its bounded slot until runtime termination. Replicas,
restarts and separate serverless bundles have independent state: these are
**not distributed quotas**, durable idempotency or DDoS/cost guarantees. PKCE's
provider-side one-use code remains the cross-instance replay boundary.

Reset accepts JSON and an exact same-origin Origin header, an HttpOnly
recovery cookie, and a password of at least eight characters and at most 1024
UTF-8 bytes. A JSON `code` cannot substitute for the cookie. The server keeps
one sequential exchange/updateUser; no browser update or auto-refresh timer is
introduced. Only successful exchange+update delivers new session cookies.
Update failure attempts signout, reports generic text and delivers only SDK
cookie deletions. A cleanup warning contains no provider error or credential.

## Recovery and browser collectors

`/auth/callback?code=…&next=/reset-password` sets a host-only Secure/HttpOnly,
SameSite=Lax `auditgava-recovery` cookie, Path `/api/auth/reset-password`,
Max-Age 300, then redirects to `/reset-password` without the code. Stale
Supabase session-cookie chunks are deleted; the PKCE verifier is preserved.
Malformed/duplicate/overlong callback code is refused. Other valid email-link
flows retain their exchange-and-relative-redirect behavior.

The reset form submits only `{password}`. The API clears the recovery cookie
when an exchange is attempted, on success or failure. The synchronous form
submission ref remains in place. Middleware handles old `/reset-password`
`recovery`/`code` query links before rendering, stages a single bounded value,
and redirects without any original query. It skips session refresh only for
these public auth handlers, reset page and HMAC webhook. Other account/admin
protection remains. Secure cookies require HTTPS (or a browser's supported
localhost exception) in local browser qualification.

Root Analytics and SpeedInsights now pass through a shared client boundary:
private auth/callback paths never mount them, and `beforeSend` suppresses
sensitive URLs for collectors previously loaded on public SPA pages. Navigation
trail storage similarly excludes those paths and sensitive query/fragment keys.
Public-page analytics/trail behavior remains covered by positive controls.
These controls do not isolate against same-origin XSS or a collector with
access to request/response headers. No real credential is used by the fixtures.

The initial callback **still arrives in the hosting URL**. HttpOnly moves the
code into a necessary cookie/response-header surface; it is not encryption or
first-collector redaction. Vercel/edge/security/log/drain/trace/cookie collectors
and browser/referrer/history/network behavior require their own acceptance.
#767's existing social direct/query-free transport remains unchanged, dormant
and held. Read `docs/admin/batch86/callback_privacy-handoff.md` alongside fresh
#767 comments; its later merged/deployed off-state evidence supersedes that
document's original undeployed status. No backend callback change is needed.

## Primary framework/provider sources, checked 26 October 2026

- [Next 15 Route Handlers](https://nextjs.org/docs/15/app/api-reference/file-conventions/route): Web Request/Response handlers; request bodies are read explicitly. Pages Router body-parser options are not an App Route Handler cap.
- [Vercel Function limits](https://vercel.com/docs/functions/limitations): the documented function payload maximum is 4.5 MB. Platform buffering and rejection precede our code; an 8 KiB streamed handler bound does not bound every upstream buffer.
- [Vercel function duration](https://vercel.com/docs/functions/configuring-functions/duration): source `maxDuration` is a platform ceiling, separate from cooperative application cancellation. Actual deployed plan/runtime limits remain an operator check.
- [Supabase PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow): exchange requires the verifier and a short-lived one-use code. This design preserves that proof and delays the exchange until form submission.
- [Vercel runtime logs](https://vercel.com/docs/logs/runtime): original request search parameters remain a first-collector concern. Existing #767 matched synthetic evidence and the human support response remain the operational gate.

## Local verification and limits

Regressions execute real handlers/Next Request and Response objects. An owned
HTTP server exercises the actual cached `@supabase/ssr` exchange, user PUT,
logout 204, forged PKCE, caller abort and whole-request deadline, using inert
values only. These are provider protocol fixtures, not real Supabase acceptance.
No database change or PostgreSQL claim is involved in this frontend-only scope.

All execution is inside Docker with no external network, read-only staged
source/toolchains, empty allowlisted environment, unprivileged UID, no sockets
or credentials, one CPU, 1 GiB RAM, 96 PIDs, 256 file descriptors, 16 MiB file
limit, 90 CPU seconds and 110 wall seconds. Only a private 256 MiB scratch
filesystem is writable; HTTP is private namespace loopback. Source hashes,
commands, image identity and outputs are in the author's private receipt bundle.
Cached Jest 29 drives the cached current Next 15.5.28/React 19/Supabase packages
using a trusted TypeScript transformer; the Darwin-only native Next compiler
is not run in Linux. A type check is separate from a production Next build.
Initial toolchain/setup failures and a 512 MiB Node heap failure are retained,
not counted as negative security controls. No hosted Actions or bot review.

## Exact coordinated Chrome qualification plan (pending)

1. Coordinate exclusive Chrome use with the release owner. Use the existing
   Chrome profile/tab and an owned HTTPS/localhost fixture only; no real code,
   account, provider call, production probe or new browser profile. Start the
   fixture inside the same network-none bounded sandbox. A trusted outer
   loopback-only relay can forward Chrome fixture traffic into its private
   namespace; do not give the target host networking, a Docker socket or
   outbound access. Keep credential/environment mounts absent.
2. Use inert marker `INERT_RECOVERY_<run-id>` and an inert PKCE verifier. Load
   actual callback handler with `next=/reset-password` and staged stale cookie
   chunks. Verify the first request deliberately contains the marker, then the
   Location and final page URL do not. Confirm Secure/HttpOnly/path/expiry,
   session chunk deletion and untouched verifier; document.cookie/HTML/RSC,
   sessionStorage/navigation trail and public asset referrers must not contain
   the marker. Match the fixture's positive method/status/correlation record.
3. Verify initial private-page loads mount neither collector. Load a public
   page first (positive collector stub hit), navigate to reset with inert query,
   then verify both retained beforeSend hooks reject private/sensitive events.
   Include back/forward and hard reload. Fake collectors are local only;
   external Vercel Analytics/SpeedInsights endpoints must be intercepted/off.
4. Submit a matching inert password twice rapidly; actual local HTTP stub
   observes one token exchange and one user PUT. Verify auto-login/session
   response, clear recovery cookie, refresh and home navigation. Exercise
   invalid/expired/absent cookie, forged verifier, duplicate query, old recovery
   URL, update failure, slow/cancelled body and provider, 413/409/503/504 paths.
   Preserve failed/skipped cases and never log password or a real credential.
5. Browser results certify only that local fixture. A separate operator must
   inventory every deployed first/downstream collector and actual hostname,
   protocol, cookie/header/log handling and provider configuration. Unknown or
   retaining collectors leave #767/#488 open. Do not activate social callbacks,
   consent, publishing, uploads, native/worker supervision or production probes.

Rollback is a normal source revert and coordinated deployment, with no schema,
workflow, dependency, provider or flag rollback. An in-flight five-minute cookie
will expire; old query URLs are handled by the new middleware. Reverting restores
the old query-carrying form contract, so privacy acceptance must be re-evaluated.
