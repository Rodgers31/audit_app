# Meta operational readiness: recovery and deployment evidence (#488)

Prepared 2026-10-08 in the isolated `meta-operational-readiness` worktree,
branch `codex/meta-operational-readiness`, fetched base
`bd46832156cb921173fea32d9d9698d696a676dc` (main with #513–#519).
Draft PR/commit: see this branch's attached PR and final handoff receipt.
Issue #488 stays open. The dirty primary checkout was not edited. No actual
secret material, production database, Meta account, OAuth flow or deployment
configuration was read or changed. The only exported keys are inert fixtures.

## Delivered behavior and recovery interface

`backend/social/connections/recovery.py` provides `RecoveryKeyring`,
`RecoveryProbe`, `parse_keyring(bytes)`, `encode_keyring(ring)`,
`write_keyring_backup(Path, ring)`, `read_keyring_backup(Path)` and
`verify_restoration(original, restored, probes)`. The last function constructs
independent cipher instances and decrypts supplied envelopes in each, comparing
clear bundles. Empty probes cannot pass. Its evidence covers only the supplied
owners/purposes/versions, never inventory completeness or production custody.

The backup is a bounded JSON object with exactly `schema_version:1`,
`purpose:"meta_credential_envelopes"`, `active_version` and `keys`. Keys map
stable version labels to Fernet's URL-safe base64 encoding of 32-byte keys.
At most 64 versions and 65,536 bytes are accepted. Active version must exist.
Duplicate JSON names, extra fields, bad keys and unsupported formats fail closed.
The direct keyring API enforces the same inventory/type boundary as parsing.
Exports are **plaintext key containers**: use only an approved encrypted private
volume or secret-store recovery workspace. This helper supplies no encryption,
secret manager, production inventory scan or environment loader. `repr` hides
keyrings, probe owners and ciphertext. Error messages have stable codes and do
not retain decoder exception context; exception collectors can still retain
caller/frame locals (see the BLOCKED Sentry gate below).

File reads use nonblocking/no-follow descriptors, bounded reads, owner checks,
private mode and single-link regular-file checks. Symlinks, pipes, directories,
shared-mode files, hardlinks and oversized files are refused. Exports use
exclusive creation and file/directory fsync, refuse overwrites, and attempt
removal on failure. A failed persist is never reported as authoritative; if
cleanup also fails, the leftover must remain unverified. Parent directories
must be operator-controlled. Same-user hostile processes, off-host replication,
storage encryption, integrity/authenticity and disaster recovery are separate
custody requirements. See [the operator runbook](META_RECOVERY_OPERATOR_RUNBOOK.md).

`PYTHON_DOTENV_DISABLED=1 PYTHONPATH=. python -B -m scripts.social_meta_recovery
--fixture-drill` from `backend/` performs actual local export/read/reconstruction,
old-envelope decryption after active-version rotation, re-encryption, retired-old
key positive control, fresh material decryption for all four service purposes,
and four failing controls on one representative purpose. CLI has no real-key
input and no environment defaults.
Default returns MISSING/exit 2; malformed arguments return BLOCKED/exit 2 without
reflecting them. Success is VERIFIED_BY_EXECUTION for **inert_fixture_only**,
with `production_authorized:false` and `digest_keys_verified:false`.

The cipher's public failure paths formerly raised inside decoder handlers:
`raise ... from None` hid but retained a UnicodeEncodeError containing malformed
key input or a KeyError containing the requested version. Two tests failed at
the recorded base, then passed after raising outside those handlers. Both
constructor/decrypt errors now drop that context. All service flow/credential
and native credential-loading callers use this shared cipher boundary; encrypt
and database failures are not newly certified as safe for frame-local capture.

## Current evidence matrix

VERIFIED_BY_EXECUTION means a specified operation actually ran in the stated
local scope. DECLARED_ONLY means code/readback/documentation establishes a
contract but authenticates no deployed configuration. MISSING means no exact
receipt is available. BLOCKED means an executed defect or pending approval
prevents accepting that gate. Every row needs its own eventual deployed receipt.

| Gate | Status | Precise provenance and limit |
| --- | --- | --- |
| Envelope backup/restore/rotation and exact owner/purpose binding | VERIFIED_BY_EXECUTION | `test_connections_recovery.py`, crypto recovery tests and fixture CLI; independent reconstructed instances and real temporary files; inert keys only |
| Failed export/commit then restart | VERIFIED_BY_EXECUTION | File write/open/file-fsync/directory-fsync faults; fresh read of prior backup; actual service parent/Page rotation with SQLite before_commit fault and new engine/session/cipher, plus successful durable rotation control |
| Real keyring custody, full version inventory and restored production clone | MISSING | No explicitly supplied secret-store backup, inventory or independently restored database receipt |
| Subject-digest key restoration/rotation | MISSING | Privacy session owns separate keys/index implementation; envelope drill cannot prove digest lookup continuity |
| Exact Meta app identity/product/app mode/registered HTTPS redirect/origin | MISSING | Public documentation read only; no authenticated App Dashboard/configuration readback, exact accepted host or build was supplied |
| Declared requested scopes and tasks | DECLARED_ONLY | `config.py:SCOPES`, provider discovery exact grant/task intersection; current official pages below; no app-specific proof |
| Owned business Standard Access vs reviewed wider access | DECLARED_ONLY | Current official App Review development table permits owned/managed business Standard Access without review; Advanced Access for multiple businesses needs review. No actual app role/access receipt |
| Selected Page/professional IG identity/reconnect/disconnect | MISSING | Separately authorized account validation remains unperformed; no OAuth/account changes occurred |
| Outbound Meta HTTPX and Sentry tracing protection | VERIFIED_BY_EXECUTION | Existing provider test's ordinary HTTPX unsafe control plus wrapped client; new success/HTTP/provider/parse/transport failure log captures, installed Sentry memory transactions, no external Sentry transport |
| Actual Next browser callback/middleware query scrub | VERIFIED_BY_EXECUTION | Six current-main callback-route/middleware Jest tests in disposable tracked snapshot using read-only dependencies; four actual GET/script VM cases for success, denial, encoded query and no opener. Browser-side behavior only |
| Application SocialRoute telemetry query/error/body scrubbing | VERIFIED_BY_EXECUTION | Actual FastAPI TestClient requests and social logger capture; static route operation, allowlisted fields; distinct from client/access logging |
| Inbound callback Sentry query/event/frame-local protection | BLOCKED | Actual memory transport captures retain synthetic code/token/error query markers; separate adversarial captures retain keys/raw backup/decrypted bundle in frame locals; #525. `send_default_pii:false` does not establish this gate; deployed Sentry wiring is unknown |
| CDN/proxy/Next/web access/WAF/tracing callback-query protection | MISSING | No deployed exporter/provider log readback; browser query removal happens after HTTP ingress |
| Current social migration/RLS/browser revocation | VERIFIED_BY_EXECUTION | New private PostgreSQL lane executes all four current migrations and browser-role denial controls; see role receipt below. This does not cover privacy session's new DDL |
| Exact deployed migration/API/worker roles, memberships/default grants/policies | MISSING | No production role names/read-only metadata receipt. Local synthetic owner and backend roles are tests, not intended-role identity proof |
| Retention policy and public notices/subprocessor agreements | BLOCKED | Inventory/decision seam below is pending. No approval/publication/legal-exemption determination exists |
| Runtime assembly/enablement | BLOCKED | Requires every real receipt plus explicit enablement; local evidence authorizes neither connections nor publishing |

## Current official Meta evidence, read 2026-10-08

The web reader returned HTTP 429/unavailable. The unauthenticated rendered
Meta-owned pages were readable in the in-app browser, with no login or app
configuration interaction. These are protocol/policy readbacks, not app receipts.

- [Manual Facebook Login](https://developers.facebook.com/documentation/facebook-login/guides/advanced/manual-flow), updated June 30, 2026: check the registered Valid OAuth redirect URIs under Facebook Login settings; returned code/state/error query values are sensitive; identity inspection and permission readback are server responsibilities.
- [Instagram Facebook Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login), updated March 3, 2025: professional Business/Creator identities; consumer accounts unavailable.
- [Instagram App Review](https://developers.facebook.com/documentation/instagram-platform/app-review), updated June 30, 2026: owned/managed-business Standard Access and multi-business Advanced Access are distinct. Its permission list spells `instagram_content_publishing`; the current publishing guide spells `instagram_content_publish`, matching code. Preserve this documentation discrepancy until exact dashboard/grant readback resolves it.
- [Instagram publishing requirements](https://developers.facebook.com/documentation/instagram-platform/content-publishing), updated June 30, 2026: Facebook Page access token, `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`; PPA may block a Page later. It labels the product Facebook Login for Business and conditionally lists ads permissions for Page roles granted through Business Manager. Current code requests no ads scopes. Exact installed product/role provenance must be reconciled; do not blindly add scopes or infer readiness.
- [Page posts](https://developers.facebook.com/documentation/pages-api/posts), updated April 17, 2026: Page token and content tasks; broad guide includes moderation/engagement/video permissions for operations beyond the narrow text/image scope. Code's `CREATE_CONTENT`/`MANAGE` eligibility and five scopes need app-specific least-privilege/grant confirmation, not adoption of the entire broader list.
- [Platform Terms](https://developers.facebook.com/terms/dfc_platform_terms/), updated February 3, 2026: sections 3.d (requested deletion/retention evidence), 4 (accessible policy), 5 (written service-provider/sub-service-provider controls), 6 (security) and 12.l (broad Platform Data definition). These grounds justify an inventory and review, not an audit-history exemption.

Bound the eventual read-only app receipt to: app ID; selected login product and
its installed settings; Graph version; exact redirect/origin and HTTPS host;
app mode, developer/tester/business asset role provenance; each requested and
actually available permission/access level; Page content tasks; Page/linked
professional IG identity; build/deployment/configuration revision; privacy and
callback URL registrations and unauthenticated reachability. Record a private
receipt locator, capture time, reader role and sanitized readback per field.
Unknown fields remain MISSING. Neither a flag set in config nor a document hash
authenticates app setup. Do not launch Login, approve review, add roles or scopes,
select/reconnect/disconnect accounts or mutate settings while gathering evidence.

## Role acceptance and local evidence

Current chain is `f38c61a9d203 -> c96d13e2f411 -> a42b86e1d310 -> b73e19a4f602`.
The credential/OAuth migration enables RLS and revokes all direct PUBLIC,
`anon` and `authenticated` table privileges where roles exist; it creates no
browser policies. Later media tables have the same private boundary. RLS is
not FORCE RLS: owners bypass it; a nonowner with CRUD and no suitable policy
cannot use the tables. Revoking a direct grant does not revoke inherited
membership grants. Production runtime access must therefore be proved with
actual effective roles/memberships and policy/ownership readback.

Local tests use a fresh uniquely named postgres:17 container, tmpfs database
and random private loopback port; never coordinator port 62124. They first
prove pre-migration browser SELECT works, execute current DDL against seeded
browser default grants, then check all 16 social tables and explicit browser
SELECT/INSERT/UPDATE/DELETE/TRUNCATE denial, owner positive access, nonowner RLS
behavior and inherited privilege controls. Containers stop/remove in finally.
Run this lane separately from fixed-port integration fixtures. The privacy
session owns its new migration and final new-policy role tests.

Before any separately authorized deployment, collect read-only exact role
metadata using the operator's approved connection: `current_user`,
`session_user`, Alembic revision, `pg_roles` login/superuser/BYPASSRLS flags,
`pg_auth_members`, table owner/RLS/FORCE flags, `pg_policies`, direct/effective
privileges, schema privileges, function SECURITY DEFINER/search_path and
`pg_default_acl`. Do not expose a connection string or result payload. Test the
matching role topology in a disposable clone. Confirm browser SELECT and writes
fail; intended API/worker operations work with only needed permissions; migration
DDL authority is separated; unrelated schema access is denied; future-table
defaults do not restore browser grants. An owner/service-role shortcut is a
privileged role decision needing explicit acceptance, never assumed least
privilege. No production migration/grant change was performed here.

## Platform Data, retention, backups and processors

This is a source-grounded inventory to review, not a policy or finding that
all listed data is necessarily Meta-derived. Classify provenance per field.
Actual stores, volumes, retention periods, processor identities/regions,
agreement receipts and backup lifetimes remain MISSING.

| Data/location in current contract | Purpose and copies to inventory | Pending disposition/decision |
| --- | --- | --- |
| Meta app secret and envelope keyring; server secret stores/exports | Authentication/decryption; encrypted-at-rest store, recovery custody, replicas | Approved access/custodians, rotation, export controls, restore/retirement evidence; never public/CI/Git |
| `social_credentials` User/Page bundles | Tokens, app-scoped subject, scopes/Page identity; database replicas/backups | Revoke/disable and approved token/data deletion timeline; disconnected/revoked rows still retain encrypted bundles |
| `social_oauth_flows` | Start nonce, pending grants/choices, hashes/actor/binding/redirect; backups | Existing ten-minute expiry and explicit purge hook do not prove scheduled purge or backup deletion |
| `social_accounts` | Page/IG IDs, names/handles/URLs, grants/capabilities/leases | Decide personal/Platform Data fields and history-link treatment, preserve uncertain delivery safety without claiming indefinite retention permission |
| Revisions/assets/revision references | User content, media, alt text, filename/metadata/evidence; private object store, inspection workspace, signed-fetch destinations | Separate user-uploaded material from provider-derived content; inventory historical references and deletion constraints; #490 owns storage acceptance |
| Publications/targets/attempts | Approved payload, checkpoints, provider IDs/URLs/receipts/error metadata | Field-level minimization, approved redaction or lawful retention with evidence; immutable schema alone supplies no exemption |
| Command receipts/audit events/worker metadata | Actor/route hashes, response metadata/reason/details and request IDs | Retention needed to prevent replay/reconcile; user-entered reasons may identify a subject; approval and implementable minimization needed |
| Future privacy ownership/receipts/status | Keyed subject digests, request/frozen affected-set references, confirmation lookup/status | Privacy session owns schema; pseudonyms/digests are not automatically anonymous; approved timelines and old-version lookup coverage required |
| Logs/traces/error reports, CDN/WAF/access exports, crash dumps | URLs, user input, raw payload/frame-local risks and synthetic probe traces | #525/upstream redaction evidence first; access limits/TTL, deletion propagation and export inventory |
| Backups/WAL/replicas/object versions/DR clones/local exports | Copies of every preceding class plus versions/digests/keys | Maximum expiration, deletion ledger/reapplication on restore, read restrictions and recovery-vs-erasure decision; key retirement is not automatically proof of deletion |
| Processor chain | Database/auth provider, private storage/CDN/host, monitoring, backup/secret stores and their subprocessors | Identify actual vendors, legal entity/region, data types/volume, written directions, subprocessor controls and cessation/deletion receipts. Repo references to Supabase/R2/Sentry do not establish deployed contracts |

Policy questions for the accountable owner/legal reviewer: which fields/copies
are Platform/Restricted Data; what user-request handling timeline and escalation
is approved; which limited fields have a documented legal/regulatory retention
requirement and for how long; how to minimize immutable history safely without
resending uncertain work; how backups expire and restored deletion decisions
reapply before reads/dispatch; which processors hold each copy and what written
controls apply; who approves policy revisions and how published status reflects
pending work or lawful refusal. No exemptions or durations have been decided.

**Consumable privacy seam:** `retention_policy_state=pending`,
`approved_policy_id=None`, `approved_policy_revision=None`,
`completed_deletion_authority=False`. Callback persistence may record a request
as pending policy review and independently disable mapped future publishing,
subject to its own implementation contract. It must not label deletion completed
from a signature, local disconnect, cipher recovery, an append-only constraint
or this inventory. Only a separately approved policy/version, complete affected
copy coverage and executed disposal/retention receipts can supply a future
approved seam. Record that in the privacy session brief, without cross-chat
messages or edits to that session's files.

## Verification and integration receipt

Final local execution on this branch: **107 retained readiness tests passed,
zero skips**, including 13 disposable PostgreSQL role tests and seven actual
Sentry memory events across two capture tests. Two existing SQLAlchemy
deprecation warnings remain. An additional **59 existing connection tests
passed** (crypto, provider, flows, accounts and API), with one existing
SQLAlchemy warning. The disposable frontend lane passed **six existing Jest
tests**; four separate actual callback GET/script VM controls also passed.
No owned PostgreSQL container remains.

The isolated recovery import/CLI test passed on Python 3.9.6 and 3.13.9. The
3.9 test executes the unchanged recovery/cipher modules and real error/JSON
helpers without ORM startup; it is not a full application compatibility claim.
The deployed Python 3.12 interpreter was unavailable and was not tested.
Hosted Actions were not enabled or used as a readiness receipt.

Independent Standards review: PASS, zero hard violations or actionable smells;
77 crypto/recovery/runtime/Sentry tests executed. Independent Spec review: PASS,
zero outstanding findings; 107 retained tests plus 40 direct binding/corruption
controls executed. Independent evidence replay: 77 recovery/runtime/Sentry
tests, seven memory events, real CLI status/exit controls and four actual
callback GET/script VM cases passed. The initial adversarial agent found the
three boundary defects below; its final turn ended before final replay. Both
the parent and the independent evidence reviewer subsequently replayed its
140 hostile refusals and four positive controls after fixes with no findings.
Final independent local recovery boundary verdict: PASS. This does not certify
the separately BLOCKED #525 telemetry gate.

Retained red-to-green regressions cover #524 (two observed-red base context
failures), #526 (oversized direct keyring and encoder/export shape bypass,
three observed-red DID NOT RAISE failures) and #527 (raw cleanup OSError
overriding refusal on read/write, two observed-red failures). #525 remains an
open out-of-scope integration defect. Existing #488 covers missing live
app/custody/upstream/roles/policy gates; no duplicate issues were opened for
those requirements. The final task receipt supplies the pushed commit and
attached draft PR; this document's contents are bound to that PR head.

Next engineering step: integrate #525's inbound event/transaction/breadcrumb
and frame-local exclusion/redaction with actual installed capture tests, then
re-run on the exact deployed host/log exporters. Next operator step: identify
approved app/host/build/secret store/role topology and private receipt locations,
perform read-only readbacks, obtain retention approval and separately authorize
restore-clone/account/deployment acceptance. Publishing/connection enablement
remains a distinct explicit decision after all real receipts.

## Coordinator verification and fixes — 2026-10-08

Copilot's restoration alias finding was valid and is tracked as #534. The same ring and separate rings sharing a keys mapping each produced an observed-red DID NOT RAISE in the retained review regressions. Verification now refuses both before constructing ciphers; independently parsed backups still pass. Parser, file reader and fixture drill produce fresh mappings; direct verification callers receive the same guard. A developer-specific path in this handoff was replaced with the worktree name.

The coordinator executed 110 readiness/recovery tests with zero skips, including the owned disposable PostgreSQL role lane, actual memory-only Sentry captures, failure/restart cases and three restoration review controls. Two existing SQLAlchemy warnings remain. Independent Spec review replayed alias refusals and the positive backup control. Passing telemetry tests continue to record the unresolved #525 behavior; no deployed log protection is certified. #524, #526, #527 and #534 are fixed in this PR; #488 stays open.
