# Request boundary completion — 3 November 2026

This change closes two reproduced request-boundary defects and strengthens the
startup test probes for #809. It does not complete the broader operating or
foreground performance acceptance in #809, #774 or #611.

## Corrected behavior

An ASGI handler can finish an `await` immediately, without giving asyncio's
scheduled timeout callback a turn. Previously it could start HTTP200 or finish
a successful body after the absolute request deadline. The resource middleware
now checks elapsed time before every downstream send. Before response start it
returns HTTP504/no-store; after start it raises the existing transport timeout,
without sending a second response start or completing the late body. This does
not preempt non-yielding Python work or retract bytes already sent.

The optional Redis counter previously renewed its expiry on every admitted
check. With two calls per60seconds, requests at0/31/62/93seconds produced
200/200/429/429 even though the local rolling budget allowed each request. A
transactional `SET key 0 NX EX period` followed by `INCR` now creates a finite
window without extending its expiry. The reply must contain exactly a True/None
SET result and a positive integer counter; booleans are not counters. The
existing local peer/process budgets and visible bounded-memory degradation
still apply. See the Redis [SET](https://redis.io/docs/latest/commands/set/) and
[INCR](https://redis.io/docs/latest/commands/incr/) contracts. A real Redis server,
its ACLs and a distributed quota were not qualified by the contract double.

Required security registration already fails closed. Its subprocess tests now
verify all four required middleware layers, preserve the parent's optimization
mode, and use explicit checks that survive Python `-O`. Mutation controls require
the specific missing-layer or invalid-rate-sequence diagnostic, so an unrelated
startup failure cannot satisfy them.

## Executed validation

The source-bound private handoff retains exact commands, raw output, JUnit,
case identities, image/entry/producer hashes, failures and independent reviews.
All results below use cached Linuxx86_64/Python3.12.16 under ARM-host emulation,
with all81 serving distribution versions checked and the separate existing
test-only overlay. This is local patched-source evidence.

| Selection | Normal | Optimized |
| --- | --- | --- |
| Request, limiter, startup, pool-policy and cold-cache controls |108passed|97+11passed, disjoint selections covering the same108identities|
| Real isolated-loopback Uvicorn/Gunicorn forwarding contract |2passed|2passed|
| Independent Standards adversaries |25passed|25passed|
| Independent Spec deadline adversaries |8passed|8passed|

Each completed selection has zero failures/skips. Independent selections overlap
behaviorally and are not added to the product count. The first full optimized
attempt reached its120-second wall limit without JUnit; it remains failed and
is not counted. Splitting the unchanged selection completed the actual cases
under the same limits. The initial independent Redis encoder-order fixture
failure and the evidence-reader repairs remain separately attributed.

The final runner validates actual readbacks: network isolation with only owned
loopback, read-only source/toolchain/root, IPC disabled,512MiB/no extra swap,
0.5CPU,64tasks,16MiB scratch,2MiB files/output streams,45CPU seconds per process
and120wall seconds per container. It verifies nonempty unique executed identities,
typed metadata, JUnit identity equality, reviewed entry hashes and owned-container
closure. Twelve malformed-frame controls plus an output-bound control refuse
per mode. No production flood or external fault injection was performed.

## Explicit acceptance boundary

The declared-route inventory contains218literal HTTP/websocket decorators in
25backend modules; router-relative declarations are not proof of mounting or
authorization. The tested global ASGI guard is a shared choke point. Existing
targeted endpoint tests do not establish every heavy route's response size,
database transfer, cardinality or upstream budget. Current DB tests here include
pool/policy construction and doubles; historical real PostgreSQL proofs retain
their dated scope.

Foreground LCP/CLS, the historical873-second signal, and current25-row audit UI
acceptance remain unmeasured. The working prerequisite packet refuses browser
acceptance: inspected cached browsers are Mach-O, not a qualified Linux browser;
the cached Node24.22.1 version probe alone is insufficient. The historical durable
audit browser fixture also upgrades to current head but checks the olda611 head;
it needs a separately reviewed current fixture and actual owned PostgreSQL/browser
execution. Do not seed production to manufacture25rows or attribute layout shifts
to row animation without measured candidates.

The private handoff supplies exact source-grounded patch requests for the parent
for search-filter shapes, budget-line offset/response budgets and existing
national/civic loan materialization. Those main-module paths were not edited by
this lane. Current external edge/socket identity, intended-host reserve and
production workload acceptance remain separate engineering observations.

The dependency follow-through reconciles the November1 audit with the later
reviewed resolver inventory and locked electron-to-chromium update. The remaining
deepmerge advisory is low severity with no fixed release in the dated primary
readback; the installed-repair proofs are historical/source-bound, not a fresh
full vulnerability scan.

Publishing, uploads, workers, generation, new/reconnect OAuth and automatic/source
admission remain held. The parent owns integration, deployments and ingestion
configuration. No live-operation authority follows from this completion.
