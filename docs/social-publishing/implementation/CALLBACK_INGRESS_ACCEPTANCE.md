# Callback ingress privacy hold

Issue #767 remains an acceptance blocker. The accepted Vercel deployment retained
inert OAuth callback query values in platform Request Logs, before the callback
HTML scrubbed the browser URL. Application middleware, CSP, no-referrer headers,
Sentry redaction and downstream drain filters cannot establish that earlier
platform copies are absent. Vercel support case CSE_01sQKuYrKfWxU7hc is awaiting a
human answer as of the 2026-10-22 UTC check.

The server now defaults to an enforced OAuth hold. Exact registered callbacks
also require a separate, exact ingress qualification. Without it:

- Meta, Threads, X and TikTok start and complete commands refuse with
  `CALLBACK_INGRESS_UNVERIFIED` before command receipts, state consumption,
  durable writes or provider calls. A previously successful command receipt does
  not bypass this hold.
- Direct provider authorization/exchange entry points repeat the check. No new
  connection authorization URL is issued.
- Connection status is unavailable and the account panels explain the hold.
  Existing local account details, discovered-identity confirmation, disconnect,
  credential recovery/rotation and eligible grant renewal retain their existing
  authentication, permission, concurrency, privacy and budget checks. The hold
  itself does not grant a provider request or bypass any other blocker.
- The server can start with otherwise valid existing configuration. Publishing,
  uploads, native processing and worker supervision remain independently gated.

## Qualification inputs

`META_VERIFIED_CALLBACK_INGRESS_URIS`, `THREADS_VERIFIED_CALLBACK_INGRESS_URIS`,
`X_VERIFIED_CALLBACK_INGRESS_URIS` and `TIKTOK_VERIFIED_CALLBACK_INGRESS_URIS` are
server-only JSON arrays of exact HTTPS callback URLs (at most 16). Absent,
malformed, duplicate, invalid, stale, partial or extra entries leave OAuth held.
The qualified set must equal the registered redirect set. No host/path aliases,
query strings, fragments, wildcards or trailing-slash normalization are inferred.
The existing product-specific redirect rules still apply.

These inputs are **operator attestations, not log-redaction controls**. Do not add
the current Vercel callback URLs just to enable the UI. No production
qualification input has been set as part of this repair. Synthetic test fixture
attestations establish only the local admission contract.

Before setting any production qualification, retain reviewed evidence for the
exact provider flow, callback URL and hosting/logging configuration:

1. A supported pre-ingestion omission/redaction mechanism, or a reviewed callback
   design using the existing resources whose earliest collectors are proven safe.
   Do not assume form_post/fragment support or infer safety from a missing log UI.
2. Bounded synthetic success, denial, encoded, duplicate-query and failure cases
   correlated with positive request markers at every relevant collector/exporter.
   Empty logs alone cannot pass. Use no real authorization codes or tokens.
3. State/PKCE, administrator-session binding, exact redirect/origin checks,
   authenticated completion and failure behavior remain intact.
4. Reconcile provider log copies, retention, drains and access with Roger. A new
   grant, logging reduction, paid resource or destructive log purge needs its own
   authorization. Revoke the attestation before changing its qualified boundary;
   an exact URL alone does not bind a future hosting/configuration change.

An already-issued authorization URL or manually constructed callback can still
reach the host and its upstream collectors. The application hold prevents new
app-issued flows and refuses exchanges; it cannot erase historical logs or stop
arbitrary incoming GETs. Keep real reconnect/provider acceptance paused while
#767 is unresolved. Existing connected accounts remain usable within their other
gates. The original infrastructure plan is not fully accepted until this gate
and the other recorded production acceptance criteria pass.
