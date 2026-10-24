# Status observations, version 2 — issue #774

Base: `ff2790ee3646f1629be5f8ee979633da922da8d0`. Scope: prompt status reads,
truthful source observations and execution labels. No ingestion, source trust,
publishing, uploads, configuration, migration or service activation is implied.

## Compatibility and authority

The admin page uses `GET /api/v1/system/pipeline-health/v2`, schema_version 2.
It requires the existing admin dependency, with private/no-store HTTP headers.
The synchronous database snapshot retains the existing one-thread physical slot,
session ownership/closure and database timeout boundary. Only that local snapshot
is cached for 30 seconds; source freshness is assembled on every response.
The retired web `etl.kenya_pipeline` import is not checked in this version.
Missing database counts display Unavailable rather than zero.

Cold source state is unknown, reachable=null, outcome=not_observed,
observed_at=null. A request starts one independent background batch; the status
response never awaits it. Fresh/stale labels use a monotonic clock, independent
of the database timestamp. Source observation timestamps are UTC. At five minutes
the old observation is explicitly stale while another batch runs. A reversed
monotonic observation is unknown. Stale success never appears as fresh success.

The legacy endpoint remains present with its boolean reachable DTO. It shares
the same source cache/batch; if necessary it awaits a real observation. A cancelled
legacy waiter cannot cancel shared work. If a boolean cannot be supported by an
observation, it returns503 rather than inventing false. Legacy module/job fields
remain available to existing consumers; the new UI makes no inference from them.

## Resource and failure limits

Per web process: one on-demand batch, at most once per300 seconds. Five fixed
government homepage HEAD requests, at most five connections, no keepalive pool,
no retries, two redirects maximum per request,2-second HTTP timeouts and a
3-second async batch deadline including context-managed client closure. The slot
is not released until batch cancellation/client cleanup completes. These are
cooperative async limits, not an OS process-kill guarantee for arbitrary injected
noncooperative implementations. No scheduler runs while nobody reads status.
TLS verification stays enabled. No body download or database connection is used
by the reachability monitor. There are no user-supplied probe URLs or flags.

HTTP responses below500 mean an HTTP response was observed; they do not verify
publisher content, financial freshness, credentials or ingestion. The UI shows
the actual HTTP code, not an invented successful job. Timeout, certificate and
other request failures have distinct fixed outcomes. Library exception text and
internal paths are not exposed by the monitor. Stale/unknown source observations
make the overall observed-check state unknown unless another recorded warning
or error already makes it degraded/unhealthy. An empty observation set or absent
database cannot make the state healthy.

## UI polling and interpretation

The existing layout is retained. The page polls every60 seconds, briefly every
2 seconds while its bounded source batch is pending. Local DB cache prevents
those pending polls from repeating counts. React Query does not poll background
windows by default. Refresh does not bypass the300-second source budget.

The web auto-seeder is labelled as web state; stopped is not a dedicated-worker
failure. Execution is explicitly not observed on this page. The link to
`/admin/etl` provides worker readiness and durable command/native receipts.
Calendar plans, homepage responses and a status badge never authorize a job.

## Qualification

Red controls execute the predecessor's stalled HTTP path and its actual UI
certificate/unknown/stale labels. Green controls execute source coalescing,
deadlines/closure, cancellation, stale/clock reversal, admin denial, private wire
shape, retired-import exclusion and preserved existing worker/SQL behaviour.
Actual Chrome uses an inert local fixture or the accepted production release;
fixture render proof does not certify production authentication, field FCP/LCP
or billed savings. Original #774 field-performance and #699 operating gates stay
open until their separate evidence exists.
