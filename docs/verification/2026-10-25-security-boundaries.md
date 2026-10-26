# Security boundary repairs: 789, 809, 810

This change narrows the observed auth-project privileges, bounds API work in
the existing single-instance serving topology, and explicitly audits the Meta
launch capability. Publishing, uploads, native processing and supervision are
not activated by it. The seeding/worker database profile is preserved.

## Auth project

`supabase/migrations/20261026_browser_privilege_minimization.sql` is a separate
auth-project operation, not an Alembic revision. The reviewed live catalog had
RLS enabled on `profiles`, `watchlist_items` and `data_alerts`, but browser roles
also held table-wide privileges that RLS does not constrain. The migration
removes TRUNCATE, REFERENCES, TRIGGER and MAINTAIN, including column REFERENCES,
while preserving the existing RLS-governed row CRUD privileges. It changes no
records, role memberships, RLS policies, ownership or function bodies.

MAINTAIN requires PostgreSQL 17 or later. The verified auth project reported
`server_version_num=170006` during the 26 October read-only preflight. Require
a fresh version check before installation; the PostgreSQL 17 fixture alone
does not establish a hosted target's version. Earlier versions are outside
this migration's supported contract.

Browser/PUBLIC execution is removed from the six existing internal trigger and
audit helpers. Existing owner, service-role and audit-reader grants remain.
Missing audit helpers on an auth-only project are not created. Unexpected
ownership, disabled user-table RLS or retained inherited authority aborts the
transaction.

Future postgres-created functions lose the built-in global PUBLIC EXECUTE
default; a per-schema REVOKE cannot remove that global default in PostgreSQL.
Explicit browser function/sequence defaults in public are removed as well.
Existing unrelated functions, sequences and managed Supabase creator/schema
defaults are preserved. New intentional browser RPCs need explicit grants.
This is a scoped application-owner policy, not certification of every managed
schema or future object created by another role.

The earlier profile-authorization trigger and restrictive newsletter policy
remain in place. Tests replay their real SQL and verify ordinary profile and
watchlist operations, cross-user profile restrictions, authorization-role
denial, private subscribers, audit capture and the audit-reader identity call.
PostgreSQL TRUNCATE controls demonstrate the excess database authority; they
do not assert that PostgREST exposes arbitrary SQL operations.

## API work and identity

The server pins one worker and disables forwarded-client rewriting. The
limiter uses the ASGI socket peer without loopback/missing-peer exemptions or
client-supplied forwarding-header authority. On Render, users may share a
proxy peer. The serving profile admits at most 600 requests per peer and 900
per process window of 60 seconds. These distinct ceilings can bind before the
ordinary 1,000-request worker recycle; the earlier equal 1,200 ceilings could
not. They are coarse admission choices, not measured throughput guarantees or
end-user fairness. A shared proxy's users still share its peer quota. The
aggregate gate checks room before allocating peer state and debits only after
peer admission, so rejected traffic from one peer cannot spend another peer's
process share. Restarts and recycling reset these counters.

Startup additionally requires `WEB_CONCURRENCY` unset or exactly `1`, even if
command-line flags would override a stale environment value. This conservative
configuration check is intentional. The current Render preflight resolved
`WEB_CONCURRENCY=1`; verify it again before deployment.

The ingress guard caps eight in-flight non-health requests, 32 MiB raw body
per request and 32 MiB aggregate buffered body, 32 KiB query/header bytes and
100 headers. Body-bearing requests occupy at most four of the eight slots,
reserving capacity for ordinary reads. Declared/chunked GET/HEAD/OPTIONS bodies
also use that share. It rejects ambiguous framing, compressed bodies and over-budget
input before application decoding, preserves signed bytes, and releases
capacity on errors/cancellation. The JSON ceiling accommodates the existing
largest legal social-document contract; object bytes use private storage.
Before JSON decoding, a quote/escape-aware scan also caps 2,048 containers,
64 levels of nesting and 16,384 structural separators, including requests
without a content type. UTF-16/32 JSON is refused; UTF-8 BOM handling cannot
bypass the same geometry limits. This bounds tiny-container expansion without
rewriting the signed/request bytes.
Scans above 64 KiB use one dedicated physical worker with no queued scans;
smaller scans stay bounded inline. A cancelled/timed-out request retains its
body and admission accounting until that worker actually finishes. Shutdown
joins it. This keeps other reads responsive during the scan; the GIL and the
framework's subsequent JSON decoding remain separate limits.
Existing lower callback/webhook/media limits remain. Body reads have a
10-second deadline; downstream work has a cooperative 30-second deadline.

The API-only pool has five connections, no overflow, a two-second checkout
wait and a three-second connect timeout. PostgreSQL transaction-local work
is capped at five seconds per statement and one second per lock wait, or a
stricter existing/remaining request budget. The committed-reader transaction
declaration remains first. Request context propagates into the coalesced
pipeline-health worker. Direct startup, seeding and worker sessions retain
their existing profile. Top loans now transfers only the admitted page while
counting available rows separately; negative/oversized page limits refuse.

HTTP audit writes use a separate one-connection pool with a 0.5-second checkout
wait, two-second statement cap and 0.5-second lock cap. They do not inherit the
request deadline or compete for its five connections. Existing recorder
failure policy remains best-effort; this does not promise an audit commit
when the database itself is unavailable. Request pool exhaustion maps to a
retryable 503 with no-store and Retry-After, including legacy HTTP exception
wrappers. Extra non-database requests can still use the remaining HTTP slots.

Stale connections are checked before reuse in an isolated short read-only
transaction with LOCAL timeouts and rollback, leaving the connection idle
before the application's reader declaration. No persistent/session GUC is
used across Supabase transaction-pooler boundaries. Request timeout setup is
once per transaction, repeated only for settings changes or a tightening final
deadline; each ordinary statement still checks the elapsed request budget.
Transaction cleanup can roll back an aborted savepoint even after a deadline
expires, without a timeout-setup query running ahead of the rollback. The
next ordinary statement must reinstall/check its remaining bounds.

Required guard import/construction/registration failures stop startup. Optional
Redis failure has bounded waits and a visible local fallback, without creating
a new Redis service. Ordinary Redis network failures keep its existing bounded
fallback. A hard cache-constructor failure uses one shared process TTL store,
bounded to 1,024 entries/16 MiB serialized payloads/3 MiB per entry, with fresh
decoded reads and the existing generation/invalidation and transient-failure
TTL policy. Local process counters reset on restart and do not certify
multi-instance limits. Header/connection handling before ASGI, non-preemptible
blocking Python work, external edge policy and distributed denial-of-service
resistance remain separate boundaries. These changes do not promise immunity
to service exhaustion.

Disabling proxy rewriting also leaves the socket's HTTP scheme unchanged
behind TLS termination. The dormant direct Meta callback's external-origin
contract still requires deployment qualification under issue 767; a synthetic
HTTPS fixture does not qualify that collector boundary or authorize activation.

## Meta launch

Only `POST /api/v1/social/oauth/meta/launch` receives the capability-specific
write-audit classification. Mounted negative controls require refusal before
persistence/provider work for disabled configuration, missing/invalid origin,
query, content type, fields and nonce. Real lifecycle controls cover one-use
consumption, replay, session ownership, callback completion and idempotency.
The exception does not exempt other social writes from caller verification.

## Validation and release

The local qualification uses an owned non-root container with no external
network, read-only source/toolchain, an empty allowlist environment, private
scratch writes and explicit CPU, memory, process, file and wall-time ceilings.
PostgreSQL cases use a co-located disposable PostgreSQL 17 instance. Test
processes receive no production credentials or Docker socket. Cached package
versions match the serving FastAPI/Starlette/JWT/SQLAlchemy interfaces; the
SQLAlchemy wheel uses its pure-Python path, so native-extension performance
and production load capacity are not inferred from these unit tests.

The privilege tests require the explicitly owned `B91_PG_URL`; callback
concurrency tests require the separately guarded `B86_767_TEST_DATABASE_URL`.
An unset fixture variable is a skip, not PostgreSQL acceptance. Executed
baseline failures and candidate passes, source hashes and two independent
review reports are retained with the coordinator's B91 evidence.

Before deployment: complete review, refresh all PR feedback, verify cost
controls, preserve feature-off state, and require the accepted source/schema.
Install the exact reviewed SQL only on the verified auth project with bounded
lock/statement waits, then read back effective privileges, unchanged policy and
function definitions, ordinary admin access and feature-off state. Do not
re-grant browser authority or remove the earlier role/privacy guards during an
application rollback. Operational acceptance remains pending until those live
checks pass; a green local suite is not a production installation receipt.
