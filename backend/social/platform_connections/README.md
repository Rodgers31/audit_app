# Provider account connections

This namespace persists official Threads v1.0, X v2 and TikTok Accounts API
v1.3 authorization through the existing social account and command receipt
interfaces. It does not publish or upload. Native adapters and server composition
are separate.

The admin router is `platform_connections.api.router`, under
`/api/v1/admin/social/platform-connections/{provider}`. Composition reads only
`app.state.social_platform_connections_config`, a mapping to explicit
`ConnectionConfig` values; missing configuration remains disabled. Existing
verified Supabase administrator sessions bind start, complete and confirmation.

Authorization state is ten minutes, one use, actor/session/callback bound and
consumed durably before HTTP. X S256 PKCE verifiers and pending grants use
`CredentialCipher` owner-bound envelopes with distinct
`platform:<provider>:start|pending|credential` purposes. The existing cipher's
envelope provider label remains `meta`; the namespaced purpose is checked during
every decrypt. Tokens never enter command receipt responses or audit metadata.

The existing `social_accounts.credential_id` remains null for these accounts
because that foreign key addresses the Meta-only credential table. Resolve
`PlatformCredential` by `account_id`; pass its identity/version to `material`
inside the durable worker's existing fenced admission. New accounts and
reconnections persist `publishing_enabled=false`. Registered adapters supply the
exact capability snapshot; missing adapters retain closed capabilities. X
publishing budgets remain a separate account-scoped ledger.

X requires verified app access, positive explicit connection configuration and
an existing enabled/verified `social_platform_connection_budgets` row keyed by
SHA256(`x:` + client ID). No path creates or enables that row. A fresh short
transaction reserves 10,000 micro-USD before each `/2/users/me` request, the
inspected $0.010 user-read price. Token endpoints require real positive remaining
budget but reserve zero. Reservation storage is checked before I/O. Unknown
responses keep the reservation; there is no assumption about billing
deduplication. This is conservative spending admission, not a provider bill.

Threads validates the app-scoped identity, token type, scopes, token validity,
application ID and separate data-access expiry through official token debugging.
Refresh requires a valid long-lived token at least 24 hours old. X and TikTok can
renew an expired access token using a valid refresh grant; returned rotated
credentials replace the prior encrypted grant under version comparison.
Refresh ownership commits before HTTP. An uncertain result retains its claim;
there is no force-clear or automatic replay. Operator reconciliation of such a
claim remains an explicit integration/operational gate.
Local key rotation uses the same expected credential ID/version and command
receipt checks, re-encrypts under the active key, and advances the version without
provider calls. It refuses retained refresh ownership and publication leases.

TikTok additionally requires a genuine approved `TikTokOAuthConfig`, exact
provider-console authorization URL, matching app/callback values and explicit
approved required scopes. A Business account switch does not satisfy these
conditions. Token exchange uses `tt_user` endpoints. Token evidence provides
`open_id`; it does not establish a nickname or username, so confirmation shows
`TikTok account <open_id>` with null handle/profile URL. Creator-settings reads
finish the material transaction before HTTP and revalidate credential version
after it. The response includes account-bound settings hash and checked time for
the caller to freeze explicit privacy/disclosure choices. This does not establish
eligibility for an unapproved workflow or a verified media origin.

Migration `a703b15a0001` adds OAuth flows, provider credentials, account budgets
and connection-read budgets from accepted base `a545b14a0001`. Public/browser
roles receive no grants and RLS is enabled. Coordinator integration must serialize
the migration predecessor with other lanes and replay the complete chain. No
live migration, grant, credential, OAuth connection, post or upload was exercised
by the implementation fixtures. Key recovery/privacy inventory for these new
encrypted tables must be integrated with the recovery lane before live activation.

## Official contracts inspected 2026-10-16

- [Threads authorization](https://developers.facebook.com/documentation/threads/get-started/get-access-tokens-and-permissions), page updated 2026-08-12, read in Chrome.
- [Threads long-lived tokens](https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens), page updated 2025-03-27, read in Chrome; includes private profiles and the 24-hour refresh rule.
- [Threads debug reference](https://developers.facebook.com/documentation/threads/reference/debug), page updated 2026-08-18, read in Chrome.
- [Threads user fields](https://developers.facebook.com/documentation/threads/reference/user), page updated 2025-12-16, read in Chrome; own profile fields establish no public/private visibility signal.
- [X OAuth2/PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code).
- [X current pricing](https://docs.x.com/x-api/getting-started/pricing), user-read price $0.010; console/contract rates remain activation gates.
- TikTok exact token helpers and reviewed source records are in `adapters/tiktok_oauth.py` and the TikTok adapter lane documentation.

Fixture tests live in `backend/tests/social/test_platform_connections.py`.
They exercise HTTPX MockTransport only and isolated SQLite, including durable
receipt restart, hostile sessions/redirects, provider grant rejection, zero
budget refusal, conservative unknown reservations, reservation suppression/value
alteration, refresh rotation and concurrent disconnect during creator reads.
Independent Spec/Standards review and full PostgreSQL migration replay are owned
by the parent implementation lane; this README does not claim either passed.

`connections-verification.json` and its old recorder are historical provenance,
not supported acceptance tools. Do not execute
`backend/tests/social/platform_connections_verify.py` to refresh them. Follow
[the append-only evidence status](../../../docs/social-publishing/b15-platforms/EVIDENCE_STATUS.md)
and [the final verification flow](../../../docs/social-publishing/b15-platforms/VERIFICATION.md):
use a fresh run directory, explicit inert environment, source hashes before/after,
raw logs, JUnit/structured results and independently read-back receipts. Preserve
prior failed and superseded artifacts.

Observed red regressions during implementation, before correction:

- `pytest -q tests/social/test_platform_connections.py -k debug_token` returned
  `2 failed, 23 deselected`; wrong-application and revoked Threads fixture grants
  produced `Failed: DID NOT RAISE <class 'social.service.SocialError'>`. The
  corrected provider inspects the official app-scoped debug-token evidence.
- `pytest -q tests/social/test_platform_connections.py -k after_access_token_expiry`
  returned `1 failed, 29 deselected`; the valid X refresh grant hit
  `social.service.SocialError: CREDENTIAL_UNAVAILABLE` because access expiry was
  incorrectly required for renewal. The corrected path checks refresh validity
  separately while keeping Threads' unexpired long-lived requirement.

These are summaries transcribed from the observed tool output retained in the
implementation chat, not independently rerunnable historical receipts: the
pre-fix source was superseded and its hash was not captured. The current tests
and provenance-bound rerun demonstrate the corrected behavior.
