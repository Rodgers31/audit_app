# Durable Meta privacy ownership and callbacks (#488)

2026-10-08. Worktree: `/Users/roger/.codex/worktrees/social-privacy-durable/audit_app`.
Branch: `codex/social-privacy-durable`. Verified review base:
`bd46832156cb921173fea32d9d9698d696a676dc` (`origin/main` fetched at launch).
The finished draft PR and exact pushed commit are recorded in this chat's final
handoff and attached PR. This file describes the committed implementation;
#488 remains open. The requested scope brief did not exist on main or the
primary checkout at launch, so this session created it without editing shared
roadmap or other sessions' briefs.

## Delivered behavior and authority

`MetaProvider.discover_with_ownership` executes the existing bounded discovery,
`debug_token` app/USER/PAGE/ASID checks, Page-token `me` identity check, and
linked Instagram inspection. Its server-only `InspectedDiscovery` port supplies
`OwnershipRecorder`; generic grant dictionaries and the previous declared-match
helper cannot populate this index. Server injection is a trusted boundary:
a constructed dataclass is not external provider authentication. Tests use the
actual provider implementation with explicit HTTPX MockTransport responses;
these fixtures are not live Meta receipts.

`social_privacy_ownership` records the exact configured app, versioned keyed
ASID digest, flow, parent/Page credential UUID and version, account and Page
references. Pending-flow generation time comes from the database when inspected
ownership is persisted; credential generations use credential creation time,
not OAuth start time. Reconnect creates new credential UUIDs and retains every
old mapping. Cipher rewrap copies the prior app-bound ownership into the new
credential version; cross-app rotation rolls back. No encrypted-grant scan,
subject backfill, raw subject column or declaration-based legacy upgrade exists.
The app/version/subject/generation and credential indexes are exercised with
actual PostgreSQL query plans and lookups.

Lookup is explicitly partial. Misses, unindexed legacy data, missing digest-key
versions, conflicting credential ownership, reference overflow, changed
credential versions and uncertain timestamp ordering have separate unresolved
resolutions. Finding some indexed data does not prove all associated data was
found. Existing legacy account/credential/pending-flow records remain unindexed
until a separately authorized inspected reconnect or reviewed bounded recovery.
Raw ASIDs remain only in existing encrypted server material and ephemeral
inspection/MAC results. Digests, fingerprints, ciphertext and private ownership
references remain sensitive; audit events expose only receipt UUID, kind,
resolution and affected count.

## Durable identity, replay and ordering decisions

Receipts and exact payload variants are private immutable database records.
Each receipt has a UUID, database receipt time, original encoded-payload
fingerprint, canonical event key, optional issuance/expiry, frozen affected
references, state and audit-event FK. Exact payload fingerprints include the
configured app namespace. Canonical event identity binds app, kind, keyed
subject digest and the two optional timestamps, ignoring JSON order/whitespace,
canonical padding and an optional matching explicit app ID. Each accepted
encoding variant links to the same receipt. Provider signatures are verified
before any receipt lookup or mutation.

Database uniqueness enforces exact variants, canonical events and ownership
references. All receipt insertion and inspected ownership/reconnect/rotation
operations take the existing controls lock; accounts then lock in UUID order,
then credentials. Missing controls use the existing advisory-lock bootstrap.
The transaction commits before acknowledgment. A failed insert/commit rolls
back both receipt and revocation; another connection/restart can retry.

At most 64 distinct encodings are accepted for one canonical event. A new
encoding beyond that ceiling returns `PRIVACY_VARIANT_LIMIT` (503) before
acknowledgment; previously persisted exact variants still replay. At most 500
eligible ownership references are frozen. The issuance cutoff is applied in SQL
before that limit. Missing keys or overflow never trigger partial destructive
inference. The exact-request index permits a previously accepted retry to find
its receipt even if an old digest key is unavailable; replaying a deletion
confirmation still requires its credential-cipher key.

An unseen event with issuance excludes generations created after that issuance.
For expiry without issuance, expiry supplies the authenticated upper time bound.
Second-resolution timestamps cannot order a microsecond-resolution generation
inside the same second: those rows remain untouched and the receipt explicitly
reports `ownership_timestamp_ambiguous`, or
`indexed_partial_timestamp_ambiguous` if older proven references exist. A future
issuance more than five minutes beyond the database clock is rejected; the
limit is a local guard, not a Meta freshness promise. Old/expired signed requests
are not silently rejected as invalid; they may concern retained older data.

With neither timestamp, the first request freezes the currently indexed set.
Every equivalent timeless event of that app/subject/kind reuses it forever,
including after reconnect. A later genuinely new timeless deauthorization
cannot be distinguished from replay and cannot automatically affect a later
generation. This ambiguity requires operational resolution before enablement;
no receipt expansion or automatic replay reset exists. A callback arriving
while provider HTTP is in progress also prevents a late inspected save when
its durable receipt postdates the flow start. A newly started flow after an
old receipt is allowed to establish a new generation.

## Revocation, status and retention seam

Both kinds quarantine only positively mapped current credential generations
and block mapped pending selection, preserving encrypted pending material.
Deauthorization permits active leases instead of the interactive busy rejection.
It disables account publishing, marks mapped grants revoked and advances their
versions without clearing lease tokens/targets or changing delivery states.
Existing credential admission fences subsequent mutations. Credentials already
loaded for an external operation cannot be recalled: accepted or uncertain
remote writes are never reported cancelled. Intents, checkpoints, provider
receipts, operation IDs, immutable revisions and audit history survive. No
resend, remote DELETE, credential purge or publication cancellation is added.

Data-deletion acknowledgment returns the random 256-bit alphanumeric capability
and status URL required by the verified protocol. Its confirmation is encrypted
using the separately injected existing cipher and has an indexed lookup hash.
Exact retries return the same code/URL. The public status requires possession
of that capability, exposes no receipt UUID/subject/count/coverage, gives a
human-readable pending-review explanation and explicitly sets
`deletion_completed:false`. Unknown, malformed and duplicate lookups return the
same 404 class. Body streaming, form fields, query length and verifier inputs
are bounded; response/error headers prevent caching and referrer disclosure.

`inventory_for_review` is a private bounded seam over frozen references. It
counts grant/pending envelopes, accounts and attributed delivery evidence, with
an immutable pending decision (`deletion_authorized:false`,
`deletion_completed:false`). Legacy ownership, media attribution, backups,
subprocessors and legal retention basis remain unknown. No retention policy,
legal exception, deletion executor, completion transition or public policy is
approved. A future approved erasure process must reconcile the immutable schema
through a reviewed migration; immutability itself supplies no right to retain.

## Protocol and explicit runtime construction

The current official [Meta data deletion documentation](https://developers.facebook.com/documentation/development/create-an-app/app-dashboard/data-deletion-callback)
(updated 2025-11-07) was read in the public browser on 2026-10-08. It describes
POST `signed_request`, app-scoped subject identity, HMAC over the encoded payload,
and JSON status URL/alphanumeric confirmation. The status must explain progress
or a legitimate refusal. Web-reader fetches returned 429; the browser was
readable. No authenticated provider interaction occurred.

The current official [manual Facebook Login deauthorization section](https://developers.facebook.com/documentation/facebook-login/guides/advanced/manual-flow#deauth-callback)
(updated 2026-06-30) describes configuring a callback on removal, but supplies
no exact HTTP method, signing payload or acknowledgment contract. Those three
items remain missing evidence. Only the internal deauthorization service is
delivered. No public deauthorization endpoint is mounted or inferred from the
data-deletion response.

`create_privacy_router` requires an injected service dependency;
`PrivacyRegistration` requires explicit config, subject digester, cipher and
session factory. `install_privacy` is never called by application startup and
mounts data-deletion/status routes only with explicit `enabled=True`. There is
no environment-based privacy key/config loader. OAuth enablement is independent:
the runtime connection hook records ownership if an explicit registration is
present, while callback services need no enabled OAuth configuration. Local HTTP
fixtures prove callback processing with OAuth disabled. All production enablement
and ingress remain absent.

## Readiness recovery interface and cross-scope needs

Readiness consumes `SubjectDigester(active_version, keys)`, where `keys` is an
explicit dictionary of version strings to distinct externally provisioned
32-byte key material. Digest keys are independent from app secrets and the
credential cipher. The private `digest(app_id, subject, version)` and
`candidates(app_id, subject)` interfaces support deterministic restoration
checks without logging outputs or raw subjects. Key-version names are bounded;
unknown versions raise a sanitized `SubjectKeyError`. No production key is
invented, generated, installed or requested here.

Rotate by injecting a new active version while retaining every historical
version used in ownership/receipt records. New inspections use the active
version; old rows are retained and callbacks search all supplied versions.
Do not retire an old key based solely on exact fingerprint replay: unobserved
variants/subjects and indexed coverage still require it. Restoring only the
credential cipher does not restore subject lookup; restoring only digest keys
does not restore deletion confirmations. The readiness session must test backup,
restore and rotation for both rings, bind them to the actual app, protect the
key stores and prohibit plaintext/digest/capability output. Any key retirement
or bounded ownership reinspection/reindex design remains separately reviewed.
`crypto.py` and readiness tooling are untouched.

## Executed verification and remaining gates

Scoped verification: **109 passed, zero skips**, including 42 retained independent
cases, 17 actual PostgreSQL cases and a real loopback HTTP callback/status smoke
with its own socket/server shutdown. Final full social verification: **1,548
passed, 135 skipped** (only the separately owned fixed-port PostgreSQL lanes were
skipped), with two existing SQLAlchemy warnings. Existing social tests are also exercised;
the fixed-port domain/worker/connection/integration lanes belong to coordinator
integration and are not redirected or weakened. The private database uses a
new per-test schema on owned loopback port 62238; its server is stopped after
verification. Migration `d8f4a619b203` follows `b73e19a4f602`, enables RLS/revokes
browser/PUBLIC access, adds immutable-history triggers and refuses downgrade
when privacy history or blocked flows exist. One-head/revision-chain tests pass.

The full social command runs from this worktree with `PYTHONPATH` set to its
absolute `backend` directory, `PYTHON_DOTENV_DISABLED=1`, and the explicitly
owned disposable URL in `SOCIAL_PRIVACY_TEST_DATABASE_URL`, using the existing
shared interpreter and `-m pytest -q backend/tests/social`. An invocation without
`PYTHONPATH` failed two existing subprocess import checks before application
code; the corrected invocation is the reported final result. No shared runtime
or test-lane guard was changed. Revision checks ran
`-m pytest -q backend/tests/test_alembic_has_one_head.py` (three passed; existing
SQLAlchemy and Alembic configuration warnings).

Observed-red retained regressions cover conflicting ownership, cross-app
rotation, accepted overflow identity, bounded lookup hiding eligible history,
flow-start versus credential creation, expiry-only delayed events, changed
versions falsely claiming blocked mutations and malformed inspected provider
results returning a generic attribute error. Each passed after repair. The
same-second PostgreSQL classification was independently challenged and then
verified with unchanged credentials. Unique constraints were also tested with
distinct primary keys so PK rejection could not masquerade as event uniqueness.
Forced PostgreSQL waits cover receipt insertion/rollback, callback vs selection,
reconnect vs exact replay, digest rotation plus equivalent payload, and active
admission rechecking. Restart controls preserve evidence and acknowledged codes.

Independent behavioral, Standards and Spec reviewers report no remaining
blocking findings after executed repairs. Python 3.9.6 parsed new/changed modules
and exercised the standalone digest interface; full app startup on 3.9 remains
unverified because its SQLAlchemy dependency is absent. The available shared
verification interpreter is Python 3.13.9; deployed Python 3.12 execution remains
a coordinator/deployment check. Two existing declarative-base warnings remain.
These are local fixture receipts, not hosted Actions or live Meta acceptance.
Findings here are already within #488's explicit replay/ownership requirements;
no duplicate tracker was opened and #488 remains open.

Next engineering/operator step: review this draft and integrate with readiness's
separately restored key rings; review inventory and approved erasure/retention
workflow; obtain exact deauthorization protocol evidence; obtain actual app,
HTTPS ingress/status URL, rate-limit and access/CDN/tracing redaction receipts;
review production migration/RLS/application roles; authorize and exercise owned
account inspection/reconnect plus callback/recovery acceptance. Status URLs
contain capabilities and must be redacted at every ingress and tracing layer.
No production migration, public route installation, OAuth/provider mutation,
policy publication, environment/hosting change or job enablement happened here.
No coding or review work is interrupted; those actual-world gates remain pending.
