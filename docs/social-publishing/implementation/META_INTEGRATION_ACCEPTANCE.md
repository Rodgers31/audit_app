# Meta connection integration and review receipts

This connects the reviewed editorial API to the new account-connection code. It does not enable OAuth, change a real account, provision an app, apply a production migration or add a publishing adapter.

## Integrated boundaries

- Existing `social.api.router` remains the app entry point. An empty aggregate mounts the full-prefix editorial and connection routers exactly once. Feature modules import `http_boundary` rather than the parent router, preserving both top-level and `backend.*` launch modes without circular imports.
- Package initialization registers domain and connection models on the existing application's Base before exposing `SOCIAL_TABLES`. Test fixtures use this authoritative table set once.
- `c96d13e2f411` follows `f38c61a9d203`, creates encrypted credential/OAuth-flow tables, adds the account credential foreign key, enables RLS and revokes PUBLIC/browser-role table privileges. An empty-schema downgrade is tested; recorded connection history blocks downgrade. No operational rows or secrets are seeded.
- Accounts list SQL projects only the eight existing safe UI fields. Health metadata excludes ciphertext. Credential/token material remains server-side.
- Verified Supabase claims populate optional `AdminUser.session_id`; the existing JWT verification and admin authorization remain authoritative. Old callers keep the default `None`.
- The exact standalone callback path bypasses the normal admin-page redirect so its OAuth query is scrubbed by the callback response rather than copied to public-page analytics. Every other admin path retains protection; completing a flow requires the authenticated server API. Raw ingress/CDN access-log redaction remains an operational prerequisite.
- The social Workspace links to the connected-account screen. Original composer, worker and approval contracts remain in force; accounts report publishing disabled and no real adapter.

## Executed independent review

The stale-credential regression was run against the original connection code: a version-1 Disconnect action succeeded after reconnect replaced the grant with a different version-1 credential. Requiring both credential UUID and version under the global/account/credential locks fixes the identity ambiguity. The feature tests cover the reconnect/disconnect race on disposable PostgreSQL.

The callback middleware regression failed for both missing and expired cookies before the exact-path exception, then all five cases passed after it. Normal admin and misleading callback-prefix paths still redirect unauthenticated visitors.

Actual migration tests verify RLS, PUBLIC privilege removal, the account foreign key, fake discovery/explicit selection through the real DDL, safe list projections and refusal to discard recorded history. Import tests load the feature first in both supported launch modes and inspect the complete table set and public route paths.

A socket-denied full `main` import mounts the connection and editorial endpoints without entering application lifespan. This is an import/registration smoke test, not a deployed OAuth or provider validation.

The final combined social suite passed **266 backend tests** on disposable loopback PostgreSQL and **278 frontend tests across 16 suites**. TypeScript and scoped ESLint passed. The Meta migration is the single Alembic head. Hosted Actions remain disabled by the existing workflow; no CI policy was changed. These checks do not prove live provider access or deployed callback behavior.

## Operational gates

Before live enablement: stable secret-key provisioning/rotation and backup, exact registered callback/origin, validated Meta app access and selected Page tasks/grants, ingress/tracing/logging redaction, data-deletion/deauthorization handling, reviewed deployment role/migration plan, and a separately authorized owned-account validation. Browser profile linking is not API authorization. Threads still needs its separate API connection.

Provider-expired parent User grants and derived Page grants have separate metadata. Page tokens remain revocable; no invented permanent refresh token is exposed. Local Disconnect disables shared destinations but does not claim provider permissions were removed.
