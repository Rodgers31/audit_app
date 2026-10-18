# Worker qualification — 17 October 2026

The candidate is implemented and tested in an isolated Linux fixture. Deployment
and live-host acceptance remain pending. Production publishing, uploads, native
activation, supervision, retained writes, credentials and settings are unchanged.

## Fresh durable proof

The persistent B15 packet is `lane/worker-evidence-resume-20261017` under
`FULL_PLAN_COMPLETION_B15`. Its `full/receipt.json` covers all eight lifecycle
cases; `optimized-idle/receipt.json` covers real native/control Python-O release
and rollback. Both report PASS, unchanged runtime source, zero cleanup errors and
owned containers absent. Their PostgreSQL volumes and networks were removed.
Final independent review and delivery source/blob hashes are catalogued there.
No hosted CI or paid review ran; unavailable checks are not labelled passed.

| Shared API/native measurement | Observed | Predeclared bound |
|---|---:|---:|
| Duration | 180.80 s | >=180 s |
| API requests / cgroup samples | 132 / 27 | >=100 / >=20 |
| API p95 / max | 11.99 / 48.36 ms | <=1000 / <=3000 ms |
| Service peak memory | 282.82 MiB | <=460 MiB; hard 512 MiB |
| Steady CPU | 0.01611 CPU | <=0.40; allocation 0.5 |
| Native maximum threads including main | 3 | <=3 |
| Published targets / inert POST completions | 8 / 10 | >=3 / >=6; span >=120 s |
| PostgreSQL server / client protocol bytes | 612521 / 402761 | <=2 MB / <=4 MB |
| Restricted-role SQL calls in measured snapshot delta | 1798 | >0; nonempty, nonreset snapshots |

The actual SDK image transfer sizes were [5414226] bytes.
GET start/completion offsets inside the measured API window were [(3.396, 3.408)] s.
The first county response and CPU baseline precede gated native admission. Events
must match the declared run/case; object paths and provider account paths derive
from the seeded target's database relationships. The bound image target must
publish, and all publication timestamps must lie inside the aligned wall-clock
window. GET/POST completions require unique matching IDs, paths and time order.
SQL measurements subtract baseline counters grouped by query; empty baselines,
resets and cumulative-only activity refuse qualification (#709).

Idle observation measured 32 SQL calls and 1552 server-protocol
bytes in 65 s. These are fixture measurements, not TLS/network/billed egress,
production traffic or a representative closed day. Pool2/no overflow, one external
slot and one shared two-thread DB/native executor were observed. Runtime/image
identity is recorded; the fixture is Linux arm64/Python3.12, with host parity pending.

Startup interruption, idle, pending mutation TERM, repeated parent/native TERM/INT,
native hard kill, whole-container SIGKILL, the full 60 s deadline, and sustained
capacity all completed. Clean cases emitted joined-process/resource custody.
Kill/deadline cases retained authority and emitted no positive release proof;
contenders refused. The longest measured container stop was
60.20 s, inside the 75 s local
bound and previously confirmed 90 s host window. No host deadline was installed.

The idle case tested web-only rollback without owner/history changes, malformed
and restricted release refusal, a real post-history DELETE failure with complete
transaction rollback, valid privileged release, stale refusal, and generation2
acquisition preserving three immutable history events. The separate optimized
cohort executes these paths with native/control PYTHONOPTIMIZE=1. Authenticated
upload capabilities were false and upload issuance returned503 in every
non-startup case. No real provider post or HTTP upload grant occurred.

## Tests, reviews and history

The final focused normal and optimized cached-image runs each passed 72 tests
plus 52 subtests, with raw/JUnit reconciliation, no skips/failures/XPASS and
physical child cleanup. Independent executable Spec and Standards reviews cover
product failure/SDK paths and hostile evidence. Spec ran 245 direct controls and
14 guard tests per mode; Standards ran 104 hostile controls and 14 guard tests
per mode. An accepted-base overlay restored three exact expected failures for
uploads-off reads and the extra executor; current green tests cover those cases.
Fresh observed-red #709 controls and the empty-SQL-baseline regression are retained.
See the packet's spec-review and standards-review reports for exact scope.

The interruption made all original `/private/tmp/b15-worker-*` raw receipts and
review files unavailable. Their earlier narrative is preserved byte-for-byte as
`prior-results-original.md`, explicitly historical and not current acceptance.
Earlier thread-budget, phase/window and request-pairing findings informed the
repairs, but no lost receipt was reconstructed or recatalogued. The fresh proof
uses new run IDs and is written directly into this durable packet.

## Remaining acceptance

#699 and #709 remain separate operational/review gates until the coordinator
accepts the bound delivery. Actual deployed source/architecture/dependencies,
API/data and auto-seeder parity, host custody/whole-container capacity, TLS/pooler
and billed egress, real media/provider/recovery gates, and representative closed-
day/seven-day evidence remain outstanding. Processing/kill host acceptance needs
separately authorized pre-existing isolated DB/inert routes; unavailable fixtures
remain externally blocked. ACTUAL_HOST.md provides the unexecuted procedure.
No merge, deploy, grant, forced owner clearing or new paid resource follows from
these local results.
