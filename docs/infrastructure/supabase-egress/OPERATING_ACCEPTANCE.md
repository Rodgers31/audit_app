# Offline operating evidence for #481

This prepares the remaining operating-budget review after merged #487, #505 and
#510. It does not repeat their query changes or establish deployed savings.
Issue #481 remains open for actual representative measurements, attribution and
the owner's hosting/availability decision. No collection, database connection,
provider request, environment lookup, billing change or scheduled job is included.

`scripts/verification/evaluate_social_operating_budget.py` uses only the Python
standard library. Its direct interface is
`evaluate(packet, expected_identity=identity, as_of=aware_datetime)`. The expected
identity and evaluation time must be supplied explicitly, independently of the
packet. No credentials, DSNs or environment defaults are accepted.

The report is `BLOCKED`, `OVER_BUDGET` or `CANDIDATE_FOR_OWNER_REVIEW`.
Every result retains `production_authorized:false` and
`evidence_authentication:UNVERIFIED_OPERATOR_ASSERTIONS`. A candidate means the
supplied assertions are internally consistent and within the planning margins.
It does not authenticate receipts, prove provider accounting, authorize a worker,
establish a zero-cost hosting plan, close #481 or approve a downgrade. Unknowns
take precedence over a budget verdict; calculated exceedances remain visible.

## Packet and collection preparation

Use existing retained dashboard/readback/log evidence. Do not scan/export data,
reset statistics, run a load test or enable jobs merely to fill this packet.
An operator must separately obtain and inspect actual evidence under the intended
workload. Quiet days with Actions off or no worker cannot represent future
nightly/worker traffic. The evaluator has no collector or automatic monitoring.

The checked integration checkout has prior R2 acceptance, controlled query/worker
benchmarks, fixed-name cache counters and hosting configuration source. It has
no retained seven-day operating acceptance packet. The dated #510 investigation
records a quiet bounded counter interval and selected-value estimates, not a
current bill. The historical [worker benchmark](batch2-egress/README.md) excludes
protocol/pooler overhead and cannot satisfy this gate.

The version-one packet is strict: all listed fields are required, unknown fields
are rejected, integers reject booleans/floats, and JSON rejects duplicate keys,
NaN and infinity. Files must be regular `.json` files, at most 256 KiB; symlinks,
FIFOs, directories and devices are rejected without blocking. Direct calls have
the same payload bound. There are 7–31 daily records, at most 16 increments and
50 query shapes per snapshot. No raw logs, SQL text, parameters, tokens, URLs or
arbitrary diagnostic text belong in the packet.

| Component | Required declared evidence |
| --- | --- |
| `identity` | Organization, project, deployed 40-character SHA, database fingerprint SHA-256, cycle start/end, IANA timezone, uncached allowance bytes and a positive required reserve. The independently supplied expected identity must match exactly. Cycle dates use an exclusive end. Fingerprint the nonsecret database/project/branch identity; do not include credentials. |
| `synthetic`, `representative` | Exact booleans. Synthetic evidence always blocks. The operator's representative-workload assertion is also checked against the supplied activity records. Explicit `SYNTHETIC-` identity/observer markers remain blocking if a flag is removed. |
| `days` | Consecutive, ordered, complete closed civil days within the cycle, with the exact deployment SHA. Every provider/activity/social payload includes its own `period_start` and `period_end`, matching that civil day's timezone-aware interval. A receipt from one day cannot be copied to another. The window must end within 48 hours of the supplied as-of time. |
| Daily `provider` | `meter_scope:organization_uncached`, total uncached transfer and five service categories: shared pooler, database, auth, storage, other uncached. Include the entire organization's meter, including other projects; do not treat a project-filtered subtotal as the organization allowance. Service intervals must reconcile with the total. |
| Daily `activity` | API requests; cache hits/misses; nightly runs; worker covered/uptime seconds, scans, heartbeats and publications; restarts/deployments; Actions enabled and coverage complete. Worker coverage must span the actual civil day, including 23/25-hour days. Each day needs the intended nightly and worker profile; the window also needs API/cache/publication/deployment activity and at least one observed restart. Preserve explicit zero restarts on quiet days; an all-zero window cannot represent restart traffic. This authorizes no restart or collection. |
| Daily `social` | Database-to-worker direction, transfer and measurement kind. Actual provider bytes or directional protocol measurements qualify as declared measurements; decoded estimates and cumulative counters block. A protocol receipt is still not a provider bill. Include idle/pre-ping/setup, active work, retries/recovery and restart traffic in the observed scope. |
| `cycle_usage`, `cycle_social` | Separate provider total and measured social cycle-to-date records from cycle start through exact as-of. Their capture time equals as-of and their amounts cannot contradict observed daily lower bounds. Existing charges remain counted even when the recent week is quieter. |
| `hosting` | Owner, always-on and cost acceptance, exact build, deployment time before the window, fresh deployment-bound readback, and explicit web/worker/ETL/admin process inventories. Inactive ETL/admin roles use zero replicas/processes/pool/overflow rather than disappearing. |
| Hosting `capacity` | Matching client/direct connection limit kind, positive declared verified limit and positive reserved connections. Count replicas × processes × (pool + overflow), plus reserve. This unchanged build has web pool 5 + overflow 10 per process and worker pool 2 + overflow 0; smaller declarations are rejected. Pooler backend limits cannot substitute for client limits. Actual provider limits/topology still need operator verification. |
| `future_increments` | Unique workload, measured bytes per unit, remaining units in this cycle and explicit inclusion. `already_in_provider_total` means the observed profile/projection already contains that workload; it is not added again and cannot exceed the remaining baseline. `additional_future` adds only new remaining activity. Additional social-worker transfer enters both total and social forecasts. Reject estimates and unresolved inclusion/duplicate workload entries. Inspect the source's unit definition and overlap before review. |
| `query_counters` | Bounded before/after query-hash/count snapshots with exact expected database fingerprints, reset instants and a declared interval covering the observation window. Required `before_dealloc`/`after_dealloc` are bounded nonnegative integers and must match. Each shape has `query_sha256`, `calls`, `rows` and `stats_since`; before/after statistics start instants must match and precede or equal snapshot start. Derive calls/rows only from matching, monotonic shapes with the same global reset and unchanged eviction/history metadata. Missing/unsupported history, extra/evicted/reset shapes or cumulative totals block declared attribution. Even valid declared deltas cover only the supplied shapes and are never billed bytes or caller attribution. |

Each section's `receipt` contains `kind`, `identity_sha256`, `source_sha256`,
`payload_sha256`, `captured_at`, `observer` and `synthetic`. The identity hash
binds all expected identity fields. The payload hash is canonical UTF-8 JSON
(sorted keys, compact separators, no NaN), excluding the receipt itself. This
binds the amounts, period and relevant scope. `source_sha256` is an operator's
declared hash of retained source evidence; the evaluator does not read that
source or verify its authenticity. A person can rehash a false assertion. Hashes
are provenance/integrity checks, not signatures or independent verification.

Construct each `query_sha256` from the scoped database, user, query identity and
top-level flag rather than raw SQL. The declared database fingerprint must also
match the independently supplied expected identity. PostgreSQL 18 exposes
`pg_stat_statements_info.dealloc` for evictions and each entry's `stats_since` for
its statistics start; matching endpoint counts alone cannot establish continuous
history. See the [official pg_stat_statements documentation](https://www.postgresql.org/docs/18/pgstatstatements.html),
read on 2026-10-08. Unsupported source metadata stays blocked; no query collector,
statistics reset or fallback estimate is supplied.

Allowed receipt kinds are `provider_dashboard`, `runtime_logs`,
`social_provider_meter`, `social_protocol_measurement`, `hosting_readback`,
`future_measurement` and `query_stats_snapshots`, matched to their sections.
Capture times cannot precede the evidenced interval or exceed as-of. Hosting
readback is also fresh within 48 hours. Report provenance includes the tool's
actual content SHA-256, generation time, canonical input/expected-identity hashes
and the explicit evaluation time. Optional saved reports are created exclusively,
never overwrite inputs/results, and are reopened to verify their contents.
CLI argument/read/write failures retain the same unverified-authentication flag,
tool identity/hash and generation time. Unvalidated packet/identity hashes remain
null in those failure reports; no caller values or raw file errors are returned.

## Budget arithmetic and limitations

Quantities require `value`, `unit`, `rounding` and `resolution`. Values are
nonnegative integers or bounded decimal strings; units are B, MB or GB with
decimal scales. `exact` requires zero resolution. `nearest`, `up` and `down`
require positive resolution and produce conservative byte intervals. Decisions
use upper bounds, including service-rounding uncertainty. The provider total
and its breakdown are alternative descriptions of one charge, never summed as
two charges. Cached transfer and external R2 object bytes are separate scopes.

Exact zero protocol transfer conflicts with declared worker scans, heartbeats or
publications, including their setup/header/reply traffic, and blocks both daily
and cycle records. A charged provider meter may legitimately read zero. A rounded
protocol reading of zero with positive upper uncertainty is also distinct from
exact zero; the evaluator preserves that uncertainty without inventing a bill.

Daily social records, accumulated social usage and measured `social_worker`
increments must use the same measurement basis. Charged provider bytes and
protocol wire bytes cannot be combined into one social rate. Only provider-byte
social records must fit the corresponding charged provider total; protocol
traffic can be positive when that charged meter is zero. The 200 MB social
planning target still applies to the consistently declared social basis.

The existing planning margins remain 120,000,000 bytes/day averaged across the
observed calendar days and 200,000,000 social bytes over the exact billing cycle.
Keep peak days visible. Forecast each scope as accrued upper bytes plus measured
window bytes per elapsed second × remaining cycle seconds, then add explicitly
additional future activity. This preserves historical charges and handles the
actual cycle length and timezone/DST boundaries. Check total allowance minus the
explicit reserve and the matching connection capacity with its reserve. Future
demand and representativeness remain operator assertions, not guarantees.
`projection_basis` identifies the provider baseline, social basis and protocol
future policy. `additional_future_protocol_proxy_upper_bytes` separately exposes
protocol contributions to the total forecast; included protocol workloads appear
as `included_future_protocol_proxy_upper_bytes_not_added`. Additional protocol
bytes remain conservative planning proxies rather than claimed provider-metered
charges. They remain subject to explicit overlap handling and reserve checks.

## Run and verification

Use an existing configured Python interpreter; no package installation is needed.
Extract or prepare the expected identity separately rather than trusting a
packet to identify its own intended deployment. Invoke from the repository root:

```sh
python scripts/verification/evaluate_social_operating_budget.py \
  --packet /absolute/path/operating-packet.json \
  --expected-identity /absolute/path/expected-identity.json \
  --as-of 2026-10-15T12:00:00Z \
  --out /absolute/path/new-operating-report.json
```

Exit 0 means candidate for owner review; exit 1 means blocked/over budget; exit 2
means invalid CLI/input/output. `--help` is safe without a configured app.
Errors contain fixed codes without caller values, filenames or chained source
exceptions. The checked `fixtures/social-operating-synthetic.json` is a
**hypothetical future test packet**, not a 15 October reading. It is visibly
synthetic and evaluates `BLOCKED`; it establishes no deployed measurement.

```sh
PYTHONPATH=backend PYTHON_DOTENV_DISABLED=1 python -m pytest \
  backend/tests/egress/test_operating_acceptance.py \
  --confcutdir=backend/tests/egress -q --tb=short
```

Five first-draft regressions were executed before fixes: copied receipts,
understated web pools, the 31-day social boundary, omitted additional social
growth and missing accrued charges all wrongly returned candidate. Root replayed
the same failures against a **reconstructed first draft with later hunks reversed**;
this was not a saved original snapshot. Root also observed a named-pipe read
timeout before the regular-file guard. Independent review then reproduced an
all-zero restart window incorrectly becoming candidate; the retained test failed
before the aggregate restart guard and passed after it. A single observed restart
qualifies that coverage without inventing restarts on the other days.
Root also reproduced absent counter history still reporting an available delta;
that fixture was observed red before the eviction/statistics-start guard. Changed
or missing metadata is tested offline; no real eviction/reset was replayed.
Exact-zero protocol declarations with active worker traffic were also observed
red in both daily and cycle scopes; charged-provider zero and rounded protocol
zero with positive upper uncertainty remain passing controls.
The retained tests cover these findings,
accrued over-quota/social spikes, rounding, exact cycle/DST seconds, overlap,
snapshot identity/deltas, incomplete activity, strict direct/JSON/CLI inputs,
secret redaction, bounded regular-file reads and report provenance/readback.
No test supplies live acceptance evidence.

## PR #519 review receipt

The remote review exposed one inline finding and three body-only categories,
without further inline details. At `53dba78`, nine retained cases were observed
red before fixes; all passed afterward with the complete authored suite.

- **Provenance: valid.** CLI argument, file-read and report-write failures omitted
  `evidence_authentication`. A common report constructor now preserves provenance
  and false production authorization for all three paths.
- **Measurement scope: valid.** Mixed daily/cycle/social-worker bases could form
  one forecast. Protocol bytes were also compared against a charged provider
  meter. Mixed bases now block; consistent protocol measurements with a zero
  charged meter remain reviewable. Consistent provider/protocol controls pass.
- **Provider-byte forecasting: reporting ambiguity, with intentional arithmetic.**
  Measured protocol future traffic remains an explicit conservative planning
  proxy under the batch contract. A 10 MB extra protocol workload increases the
  total planning forecast by 10 MB; its contribution and basis are now exposed.
  It never becomes an authenticated or actual provider charge.
  Independent follow-up [#521](https://github.com/Rodgers31/audit_app/issues/521)
  found that positive future social-worker units could claim protocol upper-bound
  zero in either inclusion mode. All four exact/upward-rounded combinations were
  observed red against committed `53dba78`; they now block with
  `FUTURE_PROTOCOL_TRANSFER_CONTRADICTS_UNITS`. Zero remaining
  units, legitimately zero charged-provider bytes and rounded protocol zero with
  positive upper uncertainty remain passing controls in both modes.
- **Receipt interval: valid for query snapshots.** A receipt captured at the daily
  window end could precede its own later snapshot `end_at` and still qualify.
  Capture must now reach that actual end. A matching later receipt passes.
  The hosting-before-deployment suspicion was refuted by execution: it already
  blocks, because deployment precedes window start and capture follows window end.

Actual provider/project attribution, complete representative measurements and
owner hosting/headroom acceptance remain tracked by #481. The review establishes
internal declaration consistency only and supplies no operational authorization.
