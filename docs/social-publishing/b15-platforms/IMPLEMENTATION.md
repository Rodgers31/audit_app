# Batch15 platform implementation candidate

This increment implements default-off Threads, X and TikTok Accounts API delivery in the existing immutable publication pipeline. It is local tested code, not deployment, granted access or live acceptance. Related roadmap issues: #476 and #545; native worker/media-read integration: #700. Parent operational acceptance remains open.

## Reachable surfaces

| Surface | Implemented behavior | Acceptance boundary |
| --- | --- | --- |
| Threads | Separate OAuth; encrypted credentials/rotation; v1.0 quota, container children/parent, processing, publish and retained own-post readback; signed eligible event hints | Authenticated retrieval/permalink cannot establish public visibility. Results remain Processing/unknown; lost identity remains unknown without resend. |
| X | OAuth2 + PKCE; actual user identity; versioned weighted text/URL/emoji counter; chunked upload/status/metadata; create/readback; bounded original-intent recovery | Every request requires verified access and positive operation-bound durable budget. No media request without a reviewed tariff ceiling. No live API requests or credits used. |
| TikTok | Genuine API for Business Accounts API v1.3 console auth/token rotation, current settings, exact account-bound privacy/disclosure/consent, direct/draft delivery and task status | Product/terms/property verification required. Draft inbox is Manual action, never Published. Future delivery requires separate unattended-workflow permission. |
| Provider events | Bounded exact raw-body signatures, semantic durable deduplication, account binding and status-only nudges; active rate holds preserved | Events never infer publication or permit resend. Provider subscriptions remain external gates. |
| Retention | Audited, idempotent admin `POST /api/v1/admin/social/platform-events/prune`, bounded1000, processed/unmatched hints older30days | Pending obligations retained; no worker DELETE grant or automatic scheduler added. |
| UI | Separate connection cards and popup callback; expiry/renew/disconnect; current TikTok choices; weighted X and conservative Threads counters | Default-off/unapproved connection buttons disabled. No default privacy/consent. Effective content/options edits clear all TikTok confirmations. |

Every provider mutation has its own durable intent and receipt. Checkpoints bind account, product and approved payload hash. Material loading rechecks the committed intent, credential version/expiry, current lease and account identity. Ambiguous charges remain reserved; no automatic refund, second mutation, fabricated absence proof or forced owner clearing is introduced. Valid provider Retry-After deltas/dates are never shortened; missing timing does not authorize an automatic rate retry.

X uses conservative account reservations: ordinary create15000microUSD; URL-bearing create200000; exact post+author read15000; bounded own-post lookup35000. Recovery scans at most five complete own posts and one expanded author in the original dispatch window, requiring unique exact text/media/account/time/public-author proof. An incomplete page, multiple match or empty response stays unknown. A not-yet-closed lookup window retains reconciling/reconcile, bounded301seconds, without sending HTTP early; even that admitted read intent conservatively retains its reservation.

## Explicit composition

`SOCIAL_PLATFORM_POLICY` is strict duplicate-free JSON keyed only by `threads`, `x`, `tiktok`. Missing policy creates no providers, keyring or clients. An inert example is:

```json
{"threads":{},"x":{},"tiktok":{}}
```

Each provider policy defaults all booleans false. The typed fields in `backend/social/platform_runtime.py` distinguish connections, adapter, access, operational gates, media uploads, TikTok unattended workflow and event subscription approval. Configuration cannot grant provider access. Enabled connections require explicit `<PLATFORM>_CLIENT_ID`, `_CLIENT_SECRET`, `_REDIRECT_URIS`, `SOCIAL_CREDENTIAL_KEYS` and `SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION`. TikTok requires the actual static console authorization URL containing the exact registered `redirect_uri`, approved scopes, and slash-terminated verified HTTPS origin/path prefixes. Production callback is `/admin/social/accounts/platform-callback` (TikTok trailing slash); register the exact deployment URI externally before enabling anything.

X connections additionally require both a positive configured connection budget and an existing approved `social_platform_connection_budgets` row keyed by SHA256(`x:` + clientID). Every identity read reserves10000microUSD before HTTP. Account publishing budgets are separate rows in `social_platform_budgets`; neither ledger is created/enabled by OAuth, startup or this migration. After an operator changes a ledger, refresh account health/capabilities before considering publication. No operator budget authorization or credentials were supplied in this task.

The existing FastAPI lifespan installs connection/event config and a combined native registry. The worker adds explicit `--native-platforms`; native runs still require a separately verified dedicated role and the existing global ownership contract. Optional role verification/installation takes `platforms=True`, or the explicit role-admin CLI `--native-platforms`. Default Meta-only calls keep the accepted role matrix. Optional workers receive only credential reads/lock authority, budget reserve/version updates and event processing updates; OAuth/app-read-budget tables and retention deletion remain denied. No live role installation was performed.

**Issue700 integration dependency:** current native startup still requires an enabled media runtime. Local tests use injected inert media objects; that does not establish worker media reads with HTTP uploads OFF. The worker/media lanes own that composition correction. Do not enable uploads to bypass this gate.

## Shared integration changes

- Additive migration `a703b15a0001`, predecessor `a545b14a0001`: OAuth flows, platform credentials, account budgets, app connection budgets, event inbox. Five tables have RLS and no PUBLIC/anon/authenticated grants. Destructive downgrade refuses retained rows. No production migration/grants ran.
- Coordinator must serialize the candidate predecessor after other Batch15 migrations and replay the combined chain. This isolated candidate's full Alembic chain was replayed from an empty owned PostgreSQL database.
- Shared contracts add optional TikTok options/inspected FPS, omitted when absent to preserve old document/payload hashes, and explicit bounded `still_reconciling` result.
- Narrow shared service/validation changes revalidate selected capabilities and X budgets and separately gate TikTok schedule/reschedule/resume/retry. Worker admission also rechecks the future-workflow gate before mutation.
- Shared native composition/material/runner/repository/CLI/role files register real adapters, load fenced credentials, reserve paid intents and process status hints. Supervisor/global ownership algorithms are unchanged.
- Shared media signer adds a distinct bounded1860-second provider-fetch method; browser previews remain300seconds. Material reads preserve8MB image limits and100MB inspected MP4 limit. Real video intake/render qualification remains a media/rendering-lane integration dependency; sanitized adapter video contracts are tested.
- Frontend shared API types/decoder, composer, preview, accounts and middleware receive only platform wiring; package manifests/locks are unchanged. No new hosted design service, install or build was used.

## Remaining original requirements and live gates

This increment cannot be called all phases6–8 complete: actual provider access, app/scopes/terms approval, registered callbacks, stable key custody/recovery inventory, budgets, TikTok origin and unattended workflow acceptance, subscriptions, deployed integration and real public availability remain unexercised. Threads public proof is unresolved in the inspected authenticated contract; audited manual reconciliation is a recovery-lane integration dependency. Threads lost-publish identity remains unknown rather than a fabricated match. New native reply/topic, edit/delete and analytics operations are not advertised; those are unsupported or belong to separate roadmap increments. This lane does not implement generation, rendering/analytics, media retention or worker supervision work owned by peers.

Final exact-source test/review receipts, retained failures, baseline limitations and resource cleanup are in checkout `HANDOFF.md`. Historical subtask logs/receipts and generators are explicitly superseded in `EVIDENCE_STATUS.md`; do not replay those producers or use their old pass flags as current acceptance.
