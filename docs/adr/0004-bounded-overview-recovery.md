# 0004: Bounded recovery from explicit temporary read refusals

Date: 2026-10-31. Status: accepted for the reviewed candidate; deployment is separate.

The admin Overview starts seven concurrent authenticated reads. A cold JWKS
cache admits one provider fetch and immediately refuses followers. Those
followers previously received a bare 503; the shared browser client excluded
503 from its retry policy, and CORS did not expose Retry-After. A healthy later
cache therefore required a manual page refresh to recover those panels.

Keep the authentication admission policy. Cold in-flight followers receive
Retry-After: 1 and Cache-Control: no-store. Failed-provider leaders and cooldown
followers advertise the ceiling-rounded remaining attempt-based cooldown,
including time consumed by the failed fetch. Signature validation, roles,
single-fetch concurrency and the existing 30-second attempt cooldown remain.

Expose only Retry-After through the existing CORS policy. The shared Axios
client may retry GET/HEAD on a 503 only with unambiguous numeric delta-seconds
within its existing three-second backoff ceiling. Keep two retries maximum,
the existing exponential minimum delays, cancellation and token reacquisition.
Bare, malformed, date-based or longer advice remains a visible failure.
Mutations are not replayed. Normal Axios transports normalize header values;
the direct raw-object fallback separately refuses duplicate case aliases.
This is bounded recovery, not a promise that every 503 becomes successful.

Homepage reachability is observation, not ingestion or financial authority.
Use CoB's canonical https://cob.go.ke endpoint to avoid the unnecessary www
redirect. Keep five HEAD calls, two-second HTTP phase timeout, three-second
batch deadline, two redirects, five connections and 300-second refresh period.
The deadline starts cancellation; resource ownership continues through cleanup.

Publisher certificate failures remain failed observations. Add fixed diagnostic
codes/messages for expired certificates, unverified chains and hostname errors;
do not disclose raw library error text, install publisher-specific trust
exceptions, disable verification, manufacture availability or widen budgets.
Stale/unknown evidence does not become a fresh failure or a healthy result.
Legacy health messages and v2 alerts consume the same safe diagnostics.

The October 31 probes identify a missing served intermediate at KNBS and an
expired Treasury leaf. Publisher repairs are required before those warnings
can clear. A successful homepage probe also does not establish document
availability, correctness, or source acceptance under #802.

Validation, executed review dispositions, live read-only observations and
limitations: [release record](../releases/overview-source-health-20261031.md).
