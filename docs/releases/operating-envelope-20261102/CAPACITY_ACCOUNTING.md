# Operating-envelope preparation, 2 November 2026

This is a local evaluator correction and scoped qualification. It grants no
production, worker, upload, publication, financial-generation or hosting authority.
The accepted deployment remains `2e206ed9974b254adf75b44867915e326d54487c`.
Issues #481, #778, #809 and #774 retain their operational acceptance gaps.

## Corrected connection arithmetic

The offline [budget evaluator](../../../scripts/verification/evaluate_social_operating_budget.py)
previously counted only `database.engine`'s legacy five pooled connections plus
ten overflow connections for each web process. The same process also constructs
the five-connection request pool and one-connection audit-write pool, and can
open a separate one-connection restricted audit-reader pool. The latter remains
reserved even when dormant or routed elsewhere. This is a conservative ceiling
against the declared common connection limit, not measured occupancy or proof
of the current credential/destination topology.

The existing packet's web `pool_size:5, overflow:10` fields continue to describe
the legacy pool. The evaluator now adds **seven auxiliary clients per web
process**, exposes `web_auxiliary_connection_demand`, and multiplies both portions
by the declared replicas and processes. It changes no application pool or limit.

| Per-process pool | Pool | Overflow | Client ceiling |
| --- | ---: | ---: | ---: |
| Legacy/bootstrap | 5 | 10 | 15 |
| HTTP request | 5 | 0 | 5 |
| HTTP audit writer | 1 | 0 | 1 |
| Restricted audit reader, conservatively reserved | 1 | 0 | 1 |
| Web total | 12 | 10 | 22 |
| Separate social worker, when eventually qualified | 2 | 0 | 2 |

Thus a declared one-web/one-worker profile with explicitly inactive ETL/admin
roles has a 24-client planning ceiling **before other clients and reserve**.
It is not the current OFF-state process inventory. A pooler's per-user/database
backend limit is a different kind of limit; it cannot replace a pooler client
limit. Direct connections, other hosts, provider/platform clients, operator
clients and the accepted reserve require separate reconciliation. Replicas and
processes accepted arithmetically by this offline tool do not qualify a serving
topology beyond the currently admitted one process.

This addendum supersedes only the current-capacity arithmetic in
[OPERATING_ACCEPTANCE.md](../../infrastructure/supabase-egress/OPERATING_ACCEPTANCE.md)
and its earlier hosting examples, which predate the request/audit pools. Their
other strict evidence, representativeness, egress, authentication and authority
requirements remain in force. Shared launch/infrastructure documents and the
historical synthetic fixture were deliberately not edited by this lane.

## Reproduction and verification

A new behavioral regression was executed against the original evaluator at
`2e206ed`: the declared test profile had web15 + worker2 + ETL1 + admin1 +
reserve5, fitting a limit24. It incorrectly returned
`CANDIDATE_FOR_OWNER_REVIEW`. With the seven auxiliary slots, demand is26;
the same packet returns `OVER_BUDGET` with `CONNECTION_CAPACITY_EXCEEDED`.
The four-web-process fixture changes from demand64 to92, including28 auxiliary
clients. The default synthetic fixture remains blocked.

This is a **measurement-tool correction**, not a measured change in production
connections. Existing reports retain their original bytes and generator hashes.
Old evaluator reports are historical and unsuitable for current-capacity
acceptance; rerun the corrected tool against original evidence and attribute
each changed field to this arithmetic correction. No historical bill or runtime
receipt is rewritten. A declaration can still be fabricated and rehashed:
`UNVERIFIED_OPERATOR_ASSERTIONS` and `production_authorized:false` remain on
every result.

Local executions used existing production-package Python 3.12.16 plus the
separate test overlay, read-only source/toolchain, an empty inert environment,
nonroot containers, no external networking, private scratch and bounded
CPU/memory/process/file/time budgets. The database fixtures used private
container loopback namespaces and no published host ports. They were removed.

| Selection | Normal | Optimized | Scope |
| --- | ---: | ---: | --- |
| Budget/collection/independent declarations | 359 pass | 359 pass | Offline input, arithmetic, output and collection contracts |
| TCP/ASGI startup, proxy, ingress, response/cache and request database policy | 109 pass | 109 pass | Existing deterministic request/security controls plus actual engine capacity inventory |
| Request database/PostgreSQL revisions | 19 pass | 19 pass | Actual statement/lock/checkout, rollback and independent audit capacity |
| Owned PostgreSQL collector | 22 pass | 22 pass | Actual least-privilege collection and text-free function/refusal paths |

These selections have no skips and are not summed across interpreter modes.
Initial import-path setup failure and the initial stale expected replica total
remain retained as failures; they are not passing controls. The final source
was replayed after the comment correction and document publication; exact logs,
JUnit identities, source hashes, commands and final replay are retained in the
coordinator's external `operating-envelope-20261102` evidence directory.

Two independent executable reviews passed: adversarial/spec ran 100 direct and
eight CLI controls per mode; standards ran 26 controls per mode and independently
instantiated all four engine factories without opening database sockets.
Both checked reserve boundaries, replica multiplication, malformed declarations
and false production authorization. Review establishes this local boundary,
not deployed capacity, complete route coverage or security clearance.

## Remaining acceptance and minimal next actions

| Gate | Useful work completed | Exact boundary still requiring evidence |
| --- | --- | --- |
| #481 cost/egress | Current existing-plan usage and spending-control readbacks retained locally; evaluator underestimate repaired | Billing timezone/cutoff/rounding and complete service totals; current-source caller attribution and seven complete representative days; explicit owner reserve/cost acceptance |
| #778 reserve/memory | Current resource limits, a bounded cgroup sample, provider memory headlines and connection limits retained locally | Trusted commitment-limit/aggregation history, missing connection-history charts, full role/client populations and sustained intended-profile headroom; no OOM/leak cause is established |
| #809 security/admission | Actual owned TCP forged-forwarding refusal; required registration failure; aggregate/body/scanner cancellation; response/query/cache and real PG refusal controls replayed | External edge/origin identity and pre-ASGI handling; actual deployed route/topology/DB reserve qualification; process-local limits remain local and reset on restart |
| #774 performance | Current field metric populations, event counts and selector attribution retained locally | Exact-release foreground cold/warm page timelines, visible changing elements, SPA/BFCache/background distinctions and causal reproduction before a UI change |

The production observations and exact provider/account/billing values stay in
the external local report. They are transcribed readings, not authenticated
portable exports, release-specific peaks, a representative operating packet or
a declaration that all gates passed. Missing/unsupported charts, differing
dashboard populations and mixed releases remain explicit unknowns.

## Future observation plan, requiring a separate bounded launch decision

Preparation possible with all four controls OFF: bind the exact frontend/backend
release and process/role/endpoint inventory; choose positive connection and
byte reserves; obtain existing billing metadata/provider answers; retain
available nonsecret history; replay the local controls; reproduce ordinary
foreground read-only admin loading/shift paths. Use the already provisioned
collector only if an existing approved least-privilege reader and exact query
allowlist are available. Do not create a grant/token or scan query text to fill
an evidence gap.

A later manual Facebook/Instagram pilot needs named accounts/revisions and an
owner-defined hard bound on assets, formats/bytes, sends, concurrency, duration,
retries/recovery and stop observations. That profile must fit the current
allocation with measured memory and connection reserve, accepted storage/native
and worker prerequisites, and all provider/retention gates. Keep financial
generation and automatic approval/scheduling/publishing OFF. No upgrade or new
service is implied. If the proposed profile cannot fit with the chosen reserve,
keep admission held and revise the concrete profile; do not silently widen limits.

A concrete proposal for that later decision is one 1080×1080 PNG/JPEG original
up to 5 MiB, attached to one saved and human-reviewed revision for the existing
Facebook Page and Instagram identity: at most one asset and two destination
targets, one existing worker process and one external slot, a 30-minute attended
window including idle observation before and after. Use the actual unchanged
5/60-second active/idle scan and 15/60-second heartbeat defaults; count their
setup/pre-ping/renewal/recovery traffic. Stop new admission on an uncertain
outcome, lost heartbeat, failed reserve or failed custody observation, retaining
the original command and unresolved ownership. This proposal authorizes no
execution or automatic resend. Video remains a separate measured profile.

If that image-only pilot is accepted, a candidate seven-day profile is at most
one such manually reviewed revision per day, no more than seven originals and
14 destination targets, with the same one-slot worker. That limited profile
cannot qualify video or a larger publication rate. It also cannot fill the
current evaluator's required nightly activity if source refresh remains held:
missing nightly observations stay blocked. An intentionally different ongoing
manual-only contract requires its own reviewed specification; do not invent
runs or weaken the present contract to obtain a candidate verdict.

For operating acceptance, retain 7–31 consecutive complete civil days on one
accepted deployment, with the intended API/cache/nightly/manual worker profile,
ordinary restart/deployment/recovery observations, measured directional social
traffic and organization uncached service totals. Preserve cycle-to-date charges,
capture lag, timezone/DST, counter reset/eviction history, other-client demand and
future-increment overlap. Use either consistent measured protocol bytes or
provider bytes for social accounting; they are different bases. R2 object bytes
remain a separate meter. Evaluate against the independently supplied identity
and as-of time. A passing local declaration is only a candidate for owner review.

An OFF-state week cannot supply active-worker, upload or delivery acceptance.
No worker, media upload, provider send, policy exception, new grant, support
message, monitoring service or paid run was performed to fill those gaps.
