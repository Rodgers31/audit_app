# Remaining endpoint resource contracts: 809 / 774

Based on merged PR816, `6fdce855950e94cb30c43dfdcd8307885795b3cf`.
This is a local qualification and code change. Deployment, hosted audit-reader
identity, Chrome field performance and edge acceptance remain separate.

## Whole financial registers

`GET /api/v1/debt/loans` and `/api/v1/debt/instruments` keep their existing
whole-register response shapes. Their consumers calculate and display complete
register summaries; an unannounced first page would change financial meaning.
The database query transfers at most 2,049 rows, ordered with an ID tie-breaker.
At most 2,048 rows may be published; a larger register returns retryable 503,
no-store, without partial records or totals. The bond count includes withheld
rows so publication-gate processing cannot evade the bound. These ceilings are
explicit conservative admission choices, not a measured host-capacity claim.

The successful complete response must also fit 2 MiB of conservatively counted
ASCII-escaped JSON. Exceeding this budget refuses the entire response. The byte
check runs before sending/caching, after qualification and construction; it is
not a database JSON-column transfer ceiling. Large stored provenance, receipt
and source metadata remain governed by the existing statement/request budgets,
not a universal storage-size claim. Loans project only the fields their existing
financial and qualification readers consume. Bond queries omit unused row JSON
and prefetch selected source fields, preserving the same publication decisions,
withholding disclosure, complete ladder and explicit non-stock meaning.

`GET /api/v1/entities` retains its list shape, page size 1–100 and 1-based pages.
It refuses offsets above 10,000 with 422 before query execution, removes the
unused whole-population COUNT, and adds an ID ordering tie-breaker. Database
failure returns 503/no-store rather than a successful empty population. This is
not a cursor API or a bound on every enrichment query in the application.

## Concurrent cache misses

The generic main cache decorator coalesces identical misses in one serving event
loop, including its generation marker. Across loops it bounds eight active
fills total and eight followers per fill, refusing excess work with 503 and no
submission queue. It does not claim distributed coalescing. The leader executes
in the caller's task, so cancellation cannot detach work using its request-owned
session. Leader failure/cancellation fails followers and releases admission for
a retry; a cancelled follower leaves its leader running. Followers receive
copied results. Existing cache TTL, transient-absence, invalidation-generation
and serialized-memory bounds remain in force. Cached hits require no fill slot.

## Regional observation providers

Both sustainability branches first build detached response data in a synchronous
FastAPI dependency that owns and closes its request session before returning.
The snapshot builder leaves externally borrowed sessions' transactions unchanged.
The endpoint then sends only the peer observation calculation to one physical
worker. It receives no DB session. Identical calls coalesce; different
calls or requests arriving after cancellation while physical work remains are
refused with retryable 503. Cancelling a caller does not free the physical slot.
Application shutdown joins the worker; a new lifespan creates a fresh worker.
The financial DB work runs in that synchronous dependency, with the existing
bounded pool and SQL deadlines. These changes do not qualify all blocking work on the API loop.

The two fixed World Bank/IMF URL constructors use streamed HTTP with environment
proxies disabled, no redirects and identity encoding only. Each body is capped
at 1 MiB before JSON decoding, UTF-8 only. Missing/false Content-Length cannot
bypass the streamed cap. Connect/read/write/pool inactivity waits are at most
one second; one monotonic eight-second deadline spans the three provider reads.
Every raw transport chunk is checked without HTTPX fixed-size rebuffering. A
read chunk may consume its remaining inactivity wait before the next deadline
check; DNS/native scheduling is not preempted by a Python deadline. One physical
slot still prevents an unbounded queue if such work stalls. HTTPX's read timeout
is per chunk, so it alone was not a whole-response time budget.

Failures keep existing reasoned provider/cell absence, never substitute a new
measure or a future-year observation, and are not stored as successful peer
observations. Live government-provider behavior is unqualified by synthetic data.

## Restricted audit reader and public health

The separate `ADMIN_AUDIT_DATABASE_URL` engine retains REPEATABLE READ and the
unchanged durable storage/role/incarnation admission. Its pool is now one slot,
no overflow, 0.5-second checkout and three-second connect timeout. It reuses the
existing bounded transaction-local statement/lock and ping implementation, with
five-second/one-second maxima or stricter server/request budgets. This helper's
new optional isolation argument leaves the existing request and audit-write
profiles unchanged. No session timeout SET or writer-session SET ROLE is added.
A local restricted principal proves denied writes, real pool exhaustion, reuse,
stricter server limits and rollback reset. Hosted URL/ACL/pooler configuration
requires coordinator qualification; it was not accessed or changed here.

A detailed-health database failure reports degraded/unhealthy with a fixed
connectivity message. A synthetic driver failure carrying an internal hostname,
database and SQL text previously reached the public response verbatim. The
fixture proves that disclosure mechanism; it does not prove live secret exposure.

## Validation and limits

Regression fixtures are under `backend/tests/test_endpoint_resource_contracts.py`,
`test_peer_transport_bounds.py` and `test_audit_reader_resource_postgres.py`.
They include alive controls, cancellation interleavings, a fake monotonic trickle
clock, a private loopback HTTP server, SQL projection/transfer inspection and
actual PostgreSQL. They run under the retained trusted no-network, non-root,
read-only source/toolchain sandbox with scratch-only writes and explicit cgroup,
file/process/CPU/wall limits. Normal and optimized Python receipts and frozen
source hashes are retained in the author handoff. PostgreSQL prerequisites
missing from another environment are skips, never evidence of execution.

No ingress/role/SQL protection is removed. No migrations, production grants,
configuration, deployment, source generation, callback activation, publishing,
uploads, hosted Actions, bot-review request or paid service is part of this work.
Issues 809 and 774 remain open for wider source/hosted/capacity/field acceptance.
Other whole-register consumers (for example `/debt/national` and civic figures)
are not certified by these two complete-register endpoint fixtures.

References: [HTTPX timeout semantics](https://www.python-httpx.org/advanced/timeouts/),
[streaming and redirects](https://www.python-httpx.org/quickstart/), and
[SQLAlchemy pool checkout/reset](https://docs.sqlalchemy.org/en/20/core/pooling.html).
