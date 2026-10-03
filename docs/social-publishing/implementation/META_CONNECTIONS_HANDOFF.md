# Meta connections implementation handoff (#483)

Code and fake-provider tests only. No live flow, account permission change, app setup, post, deployment, production environment or database change occurred. Runtime connection availability defaults OFF. New publishing adapters remain absent, new accounts remain publishing-disabled, and automatic/global publishing controls are not enabled by this feature.

## Frozen HTTP and browser boundary

Base `/api/v1/admin/social`; all routes reuse existing `require_admin` and `SocialRoute` private/no-store structured errors. Every mutation requires a UUID `Idempotency-Key`. Mutations additionally require `AdminUser.session_id` populated from the existing **verified** Supabase claims. A client header/body/unverified JWT cannot establish binding.

| Method | Suffix | Request/result |
|---|---|---|
| GET | `/connections/meta/status` | `ConnectionStatus`; performs a schema read, then reports explicit configuration blockers |
| POST | `/connections/meta/start` | `StartCommand {redirect_uri,reconnect_account_id?,reason}` → `StartedFlow {flow_id,authorize_url,expires_at}` |
| POST | `/connections/meta/complete` | `CompleteCommand {code,state,redirect_uri}` → `DiscoveredFlow {flow_id,expires_at,granted_scopes,choices}` |
| GET | `/connections/meta/flows/{id}` | Same non-secret `DiscoveredFlow`, session-bound |
| POST | `/connections/meta/flows/{id}/select` | `SelectCommand {page_id,instagram_id?,reason}` → exact original-contract Account DTOs |
| GET | `/accounts/{id}/health` | `AccountHealth`; compact metadata only, no ciphertext SELECT |
| POST | `/accounts/{id}/disconnect` | `{expected_credential_id,expected_credential_version,reason}` → health; local disable of every account sharing this Page grant |
| POST | `/accounts/{id}/rotate-key` | Same ID/version command; rotates the parent User and all related Page bundles under the same key ring |

`AccountHealth` carries safe account/credential UUIDs, external ID, API product/method/kind, credential/key versions, Page access/data expiry, separate parent User access/data expiry and parent reconnect requirement, granted/missing scopes, checked/last-success timestamps, reconnect/publishing flags, `renewal_strategy=facebook_login_reconnect`, and `provider_revocation_confirmed=false`. The exact schema lives in `backend/social/connections/contracts.py`.

The frontend opens Meta in a popup and leaves the authenticated Accounts page as the opener. The registered callback is exactly `https://<approved-admin-host>/admin/social/accounts/callback`; query/fragment/credential URLs and alternate callback paths are rejected. Its standalone route-handler HTML has no app shell, analytics, external scripts or resources; it immediately removes the query with `history.replaceState`, then sends only short-lived code/state to the exact same origin. The opener validates origin, source window and its active random state before using the existing authenticated Axios client to relay the code. Permanent tokens never enter the browser contract, URL or storage. Supabase session UUID binding survives access-token refresh and rejects a different login session. State is random, hash-persisted, session-bound, ten-minute, consumed durably before provider HTTP, and never replayed after uncertain exchange failure. Receipts persist safe metadata rather than codes/state/authorization URLs or tokens.

## Exact parent-owned integration hooks

1. Keep the shared `http_boundary.py` and verified `AdminUser.session_id` changes in parent commit `8a5ed880c2b8b28f3639d41bd5341b79937bb911`. This worktree cherry-pick is `03e091a`; do **not** duplicate it when integrating feature commits. Feature modules import `..http_boundary`, never `..api`, avoiding router aggregation cycles. The local selection Account DTO has the frozen safe fields.
2. In `backend/social/api.py`, after declaring existing routes, import `from .connections.api import router as connections_router` and `router.include_router(connections_router)` (feature router already has the full prefix). Alternatively register it once beside the existing social router. Keep import/registration fatal rather than a soft catch.
3. Register `backend/social/connections/models.py` alongside the existing social model import in model/Alembic metadata loading. These models inherit the same Base through `..models`. Add `ForeignKey('social_credentials.id', name='fk_social_account_credential')` to existing `SocialAccount.credential_id`; this workstream intentionally did not edit that shared model.
4. In `frontend/lib/supabase/middleware.ts`, immediately after obtaining `pathname`, add:

```ts
if (pathname === '/admin/social/accounts/callback') {
  return NextResponse.next({ request });
}
```

The callback itself grants nothing and contains no account identities/tokens; authenticated completion is authoritative. Without this hook the existing expired-session/non-admin redirect clones and forwards the code/state query to the public homepage and its analytics. Add the middleware regression before enabling any flow. Operational ingress/CDN/Next access logging must redact callback queries; this code task does not change deployment logging.
5. In the social Workspace Accounts view, replace the unavailable OAuth message/button with a link to `/admin/social/accounts` (`Manage Meta connections`). The new page/components reuse the approved forest/cream/gold CSS and existing admin shell. No shared composer/hook or navigation file was edited here.
6. Keep `/accounts` DTOs unchanged. For the low-cost SQL boundary, replace ORM hydration in `SocialService.accounts` with the following safe projection, then pass each row mapping through `SimpleNamespace` to existing `capability_for` and DTO construction:

```python
select(SocialAccount.id, SocialAccount.platform, SocialAccount.display_name,
       SocialAccount.handle, SocialAccount.profile_url,
       SocialAccount.connection_state, SocialAccount.publishing_enabled,
       SocialAccount.capability_snapshot).order_by(
           SocialAccount.display_name, SocialAccount.id).limit(100)
```

`capability_for` only reads `platform` and `capability_snapshot`. Do not join credentials or add credential material to the frozen Account DTO.
7. Declare direct `cryptography>=46.0.5` in parent requirements; existing read-only Python 3.13 runtime has that version. No dependency installation occurred.
8. Expose the bounded `ConnectionService.expire_flows(limit<=100)` to explicitly configured maintenance when operating the flow. It purges encrypted nonterminal flow grants after expiry without provider HTTP. It has no automatic startup/scheduler side effect in this batch. Do not retire an old encryption key until retained credentials and nonterminal flows using it have been re-encrypted or expired/purged.

## Provider evidence and runtime gates

Direct current official Facebook Login/manual/token/Page/Instagram/permissions documentation reads were reattempted 2026-10-03 and returned 429 or unavailable; indexed developer-domain searches did not yield those pages. The blueprint's dated current official Meta research remains the app-review/access-mode reference. Successfully rechecked the maintained Meta-owned [IGUser SDK fields](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/iguser.py) and [Page SDK fields](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/page.py). They confirm `Page.instagram_business_account → IGUser` and the supported `id,username,name` identity fields. The selected Facebook Login route does not request the unsupported Instagram Login `account_type` field. Professional eligibility is the actual Page-linked professional IGUser relationship, required grants and Page content tasks, with its proof recorded inside the encrypted pending grant.

The explicitly configured `access_mode` is `owned_standard` or `advanced`, and `META_APP_CONFIGURATION_VALIDATED=true` represents an operator-verified registered redirect/access setup. Owned Standard Access is supported; no blanket business verification, advertising permission or invented review-reference string is required. Do not claim this declared manifest is provider proof. Actual Meta access/app-role/app-review requirements and endpoint behavior still need the separately authorized owned-account validation before enabling configuration. App-role access does not mean arbitrary third-party accounts can authorize.

Only the fixed versioned Graph host is requested. Page and permission discovery are bounded to 100 assets/20 pages; pagination only supplies bounded `after` cursors to the fixed endpoint, never follows token-bearing `paging.next`. Responses stream within 1 MB with identity encoding, bounded chunks/time and explicit client timeouts. Derived Page token identity is independently read with that token. Token inspection proves matching app/user/type, validity, actual access/data expiry, actual granted and asset-specific scopes. The requested scopes are `pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish`; no ads scopes are requested. Partial grants produce disabled choices; arbitrary/mismatched/unsupported selection is rejected.

Facebook User and Page bundles remain distinct. A user token's roughly 60-day expiry never becomes an invented timed expiry for a derived Page token. No generic refresh token or automatic refresh is implemented for Facebook Login; expired/revoked grants require reconnect. Rotation/reconnect/disconnect respect active publication leases and credential refresh leases. Mutation ordering is durable controls (creating/locking the absent singleton with shared advisory key 6384952001), then account UUID order, then credential UUID order. Account/credential ID and version are checked under those locks. No row lock or SQL transaction spans provider HTTP. Local disconnect reports provider revocation unconfirmed; removal at Meta is a separate operation. Deauthorization/data-deletion callbacks and publishing adapters are outside this connection-code slice and must be reviewed before operational enablement.

Fernet envelopes are bound to UUID/provider/purpose, use a stable versioned key ring, fail closed when keys are absent/malformed, and reject swapped/tampered envelopes. HTTPX's Graph URL logging is redacted before handlers receive it. No raw provider exception/payload, code/state, headers or grant material is sent to logs or audit details.

## Additive migration specification (parent is sole owner)

Apply these table/index definitions after the existing social foundation/media migration, add the existing account credential FK, and enable RLS on both new tables with **no browser-role policies**, revoking all table privileges from `anon`/`authenticated` when those roles exist. Preserve API/worker role access. Do not add a competing head or any operational rows. Before downgrade, reject while durable account/credential/flow history exists; this feature history must not disappear silently.

```sql
CREATE TABLE social_credentials (
	id UUID NOT NULL,
	provider TEXT NOT NULL,
	credential_kind TEXT NOT NULL,
	parent_credential_id UUID,
	encrypted_bundle BYTEA NOT NULL,
	key_version TEXT NOT NULL,
	access_expires_at TIMESTAMP WITH TIME ZONE,
	refresh_expires_at TIMESTAMP WITH TIME ZONE,
	data_access_expires_at TIMESTAMP WITH TIME ZONE,
	version BIGINT DEFAULT '1' NOT NULL,
	refresh_lease_token UUID,
	refresh_lease_expires_at TIMESTAMP WITH TIME ZONE,
	last_refresh_at TIMESTAMP WITH TIME ZONE,
	revoked_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_social_credential_kind CHECK (provider = 'meta' AND credential_kind IN ('facebook_user','facebook_page')),
	CONSTRAINT ck_social_credential_parent CHECK ((credential_kind = 'facebook_user' AND parent_credential_id IS NULL) OR (credential_kind = 'facebook_page' AND parent_credential_id IS NOT NULL)),
	CONSTRAINT ck_social_credential_envelope CHECK (version > 0 AND length(encrypted_bundle) > 0 AND length(key_version) > 0),
	CONSTRAINT ck_social_credential_lease CHECK ((refresh_lease_token IS NULL) = (refresh_lease_expires_at IS NULL)),
	CONSTRAINT ck_social_meta_no_refresh CHECK (refresh_expires_at IS NULL),
	FOREIGN KEY(parent_credential_id) REFERENCES social_credentials (id)
);
CREATE INDEX ix_social_credential_access_expiry ON social_credentials (access_expires_at);
CREATE INDEX ix_social_credential_data_expiry ON social_credentials (data_access_expires_at);
CREATE INDEX ix_social_credential_parent ON social_credentials (parent_credential_id);
CREATE TABLE social_oauth_flows (
	id UUID NOT NULL,
	actor_id UUID NOT NULL,
	provider TEXT NOT NULL,
	state_hash VARCHAR(64) NOT NULL,
	binding_hash VARCHAR(64) NOT NULL,
	encrypted_verifier BYTEA,
	encrypted_pending_grant BYTEA,
	key_version TEXT NOT NULL,
	redirect_uri TEXT NOT NULL,
	return_path TEXT NOT NULL,
	reconnect_account_id UUID,
	status TEXT NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	consumed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_social_oauth_status CHECK (provider = 'meta' AND status IN ('initiated','exchanging','awaiting_selection','completed','failed','expired')),
	CONSTRAINT ck_social_oauth_hashes CHECK (length(state_hash) = 64 AND length(binding_hash) = 64),
	CONSTRAINT ck_social_oauth_return CHECK (return_path = '/admin/social/accounts'),
	CONSTRAINT ck_social_oauth_secrets CHECK ((status = 'initiated' AND consumed_at IS NULL AND encrypted_verifier IS NOT NULL AND encrypted_pending_grant IS NULL) OR (status = 'exchanging' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL) OR (status = 'awaiting_selection' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NOT NULL) OR (status IN ('completed','failed','expired') AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL)),
	UNIQUE (state_hash),
	FOREIGN KEY(reconnect_account_id) REFERENCES social_accounts (id)
);
CREATE INDEX ix_social_oauth_actor ON social_oauth_flows (actor_id, created_at);
CREATE INDEX ix_social_oauth_expiry ON social_oauth_flows (expires_at);
ALTER TABLE social_accounts ADD CONSTRAINT fk_social_account_credential
  FOREIGN KEY (credential_id) REFERENCES social_credentials(id);
ALTER TABLE social_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_oauth_flows ENABLE ROW LEVEL SECURITY;
```

## Executed checks

- 59 feature backend tests, including two real PostgreSQL race tests in fresh random schemas on the explicit disposable local fixture (loopback port 62124, `social_worker_test`), plus four parent shared-boundary/session tests: **63 passed**.
- Stale disconnect regression was executed red (`DID NOT RAISE`) before requiring exact credential UUID and version, then green after the fix.
- Fake HTTPX/provider tests execute replay, wrong actor/session, missing/expired/revoked/partial/asset-specific grants, redirect mismatch, duplicate/hostile pagination, exact Page token identity, malformed proofs/numeric expiry, streamed size limit, safe logs, and no publication endpoint calls.
- Seven frontend tests execute hostile DTOs, callback origin/source/state, standalone callback CSP/query scrub order, unavailable configuration, identity/health display, one-time completion, explicit Page selection and ungranted Instagram exclusion.
- TypeScript `tsc --noEmit --incremental false` passes against a temporary tracked-code snapshot of accepted main UI plus these owned new files; dependencies were a read-only symlink. No primary checkout source or processes were touched.
- The parent retains the real additive migration/RLS/complete-router integration gate. These results do not claim live Meta app/account authorization, real grants, deployed logging configuration or production migrations.
