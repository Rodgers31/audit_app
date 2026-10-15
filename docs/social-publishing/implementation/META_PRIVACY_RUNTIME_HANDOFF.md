# Meta privacy runtime assembly (#488)

The existing API now has an explicit, default-off startup entry point for the
signed data-deletion callback, separately opted-in app-removal callback, and
indexed connection ownership. This supplies
runtime assembly; it does not certify the app, enable OAuth, connect accounts,
install publishing adapters, start a worker, or complete deletion.

`main.py` calls `configure_meta_privacy(app, SessionLocal)`. Missing or `false`
`META_PRIVACY_ENABLED` leaves ingress and app state absent. Enabling
`META_DEAUTHORIZATION_ENABLED` without privacy assembly refuses startup. Enabling
`META_CONNECTIONS_ENABLED` requires both privacy and app-removal assembly. All
three flags accept exactly `true` or `false`; absent flags default to `false`.
Privacy can remain enabled while new OAuth
connections are disabled, including after a rollback of connection enablement.

Enabled configuration requires these explicitly supplied server-only values:

| Name | Meaning |
| --- | --- |
| `META_PRIVACY_ENABLED` | Explicit callback/index opt-in |
| `META_DEAUTHORIZATION_ENABLED` | Separate app-removal HTTP opt-in; defaults off, including when privacy is enabled |
| `META_APP_ID`, `META_APP_SECRET` | Same exact app identity as the connection configuration |
| `META_PRIVACY_STATUS_URL` | HTTPS URL ending exactly in `/api/v1/social/privacy/meta/data-deletion/status` |
| `SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION`, `SOCIAL_CREDENTIAL_KEYS` | Existing versioned credential envelope keyring |
| `META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION`, `META_PRIVACY_SUBJECT_KEYS` | Separate versioned subject lookup keyring |

Key maps are bounded JSON objects with unique version names and canonical
URL-safe base64 encodings of 32-byte keys. Up to 64 envelope and 16 subject keys
are accepted. Key material must not overlap between the two purposes. Invalid
enabled configuration fails before app mutation and uses a generic error without
retaining decoder exception context. No keys are generated or backed up here.
Custody, complete inventory, independent restore, rotation and retirement still
need deployed operator evidence.

The existing callback performs signed validation and commits a durable request
before acknowledgement. Retrying after reconstructing the runtime returns the
same confirmation receipt. Public status remains `pending_review` with
`deletion_completed: false`. No deletion executor or legal retention decision is
supplied by this change.

The separately opted-in `/api/v1/social/privacy/meta/deauthorization` route
accepts a bounded POST form containing only `signed_request`. It uses the same
signature validation and existing durable revocation service, then returns an
empty HTTP 200 only after commit. It exposes no internal receipt or deletion
status. This wire acknowledgment is a provisional engineering contract: local
tests do not establish Meta acceptance. Verify a separately authorized real app
removal event before accepting new OAuth connections. Leave this opt-in off
until that check is prepared; do not claim that disconnect completes deletion.

Privacy response headers are applied outside the global middleware, including
errors, rate-limit rejection and unmatched private routes. Application audit
logging redacts queries and private path suffixes. A Uvicorn access filter
redacts the same namespace even when callbacks are disabled; it preserves the
actual method/status in supported Uvicorn records. Unexpected access formats
produce a generic warning and omit the unsafe record rather than reflect it.
This protects application-process logs only. CDN, Render proxy, Vercel ingress,
browser callback and actual external tracing exporters need separate receipts.

Before production enablement: verify the exact registered app/login product,
redirect, scopes/access mode and Page tasks; approve the public privacy and
deletion handling; verify real keys and restore; verify schema and effective DB
roles; and verify ingress/exporter redaction. Deploy code with flags off first,
record exact source/configuration and rollback, then deliberately enable only
the verified slice. No new paid resource is required by this assembly.

Validation includes actual `main.app` import/HTTP execution in isolated processes
with outbound sockets forbidden, malformed configuration controls, the existing
Sentry startup capture checks, and durable SQLite callback/replay/status through
the configured installer. These are local checks, not live Meta acceptance or
production PostgreSQL role acceptance. The missing route was observed as a real
404 before assembly; a real middleware response then exposed the weaker
referrer policy before the outer header fix. Review found and reproduced
disabled-route query and unmatched-private-path logging leaks before their
regressions were fixed.
