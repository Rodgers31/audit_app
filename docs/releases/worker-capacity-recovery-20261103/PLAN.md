# Worker capacity and recovery: proposed current-host check

This is preparation based on reviewed main `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39`
(tree `429c94692890811fcab68668c5ee1ecd19226c5e`). It grants no activation,
acquisition, release, upload, provider request, deployment or resource change.
The parent owns the release and its production witness. A staged image, an
OFF-state sample and an offline fixture do not establish serving acceptance.

## Evidence and unresolved boundaries

The prior [worker preparation](../worker-readiness-20261102/READINESS.md) and
[operating accounting](../operating-envelope-20261102/CAPACITY_ACCOUNTING.md)
retain their original scopes. Their accepted shutdown, custody, retained-owner
and restore proofs are not reopened here. Current intended-profile reserve still
needs observation. Two media-inspection tests fail in x86_64-on-ARM
emulation while passing on native ARM; native substitution does not accept the
production x86_64 inspector path.

The parent's retained read-only serving witness at **2026-11-03 14:26:32 UTC**
binds source `8f08d85`, Python 3.12.16/x86_64, all **81** resolved distributions
and all **1,496** shipped source files. A local comparison verified the retained
producer/command hashes, the complete normalized package graph against the
staged image, and all 23 worker/launcher/build/profile files as members of the
same source manifest. No additional production operation was needed. The parent
recorded backend acceptance at 14:27:47 UTC and release completion at 14:45:23 UTC,
with the ingestion pin also at `8f08d85`. This V2 draft remains separate from that
deployed release. An earlier borrowed
ARM overlay had amqp 5.4.1/billiard 4.3.1; accepted serving packages were
5.4.2/4.3.2. Test-only dependencies must not replace these runtime versions.
The source manifest is
`24aade5bcd22e0e7995ed7b1ed2360a58bc9e6170ca08fc721ed02301a67d517`.
The completed parent release leaves all four production controls OFF. Its
identity witness does not freshly reverify the restricted database role or
establish active-worker reserve.

## Versioned offline reassessment

The additive entry point is
`tools.worker_rehearsal.capacity_v2.assess`. Historical `run.py`, `bounded.py`
and `qualification.py` retain their original bytes and behavior. Their automatic
verdicts remain V1 and do **not** carry V2's maximum 15-second internal sample
gap guarantee. Future collection needs a separately versioned producer that
calls V2; this change does not alter a historical producer's automatic verdict.

V2 checks the exact frozen profile's keys, numeric types and values, finite
180–900-second measured duration, monotonic sample gaps at most 15 seconds,
distinct per-sample process IDs and distinct target IDs, then the original
workload/API/memory/CPU/SQL/wire/operation-window checks. The public API remains
`capacity_v2.assess`. Its small **externally trusted loader** reads the sibling
`capacity_v2_assessor.py` once and compiles that exact captured byte buffer;
`assessor_sha256` identifies only those executed implementation bytes. The output
also names that implementation entry and the external-loader trust boundary.
Only that public loader constructs the V2 identity, scope and false acceptance
fields. Direct import or execution of the internal implementation can return
unqualified numerical calculations; it cannot stamp those V2 fields. A caller
must use `capacity_v2.assess` through an independently trusted loader. The public
wrapper refuses disk drift before and after assessment. Each archive
is read once, verified and compiled from those exact
bytes; no second file open can substitute unverified code. An archived dependency changed after loading still has its original
executed-code hash; a fresh load refuses changed archive bytes. Successful return still
says `evidence_authenticated=false` and `production_accepted=false`. It cannot
authenticate a runtime or detect a coherently fabricated observation packet.
An arbitrary Python caller can forge a dictionary or replace code in its own
process; no sentinel or source-bytes global is presented as authentication.

**2026-11-03 source-identity correction:** the earlier draft read its own file
after Python had already compiled it. A forced compile-to-execute file swap
reproduced a mismatched reported/executed hash in normal and optimized Python.
That earlier self-identity claim is superseded. The replacement loader binds
execution to one captured implementation buffer, including when a stale bytecode
cache exists. This does not attest the loader's own execution: a future caller or
recorder must establish its identity independently. No recursive self-hash claim,
historical producer rewrite or production qualification follows from this repair.

For an explicit reassessment, verify the original packet's source and artifact
hashes first and select exactly one capacity result from its original receipt.
Assemble these eight arguments from that same measured case; never substitute
a later census, thresholds, source checkout or reconstructed event stream:

| Argument | Original retained input |
| --- | --- |
| `samples` | Capacity result's `samples` |
| `latencies` | Capacity result's `api_latencies` |
| `census` | Original `capacity-steady.json`, including cohort and `statements_before` |
| `wire_before`, `wire_after` | Capacity result's corresponding wire snapshots |
| `requests` | Capacity result's original request start/completion records |
| `duration` | Capacity result's measured `seconds`, subject to V2's stated bound |
| `thresholds` | Original predeclared packet's complete `thresholds` |

Missing raw inputs leave reassessment unavailable. A future recorder must bind
its own hash, the independently verified `capacity_v2.py` loader hash, both
archived helper hashes, the executed `capacity_v2_assessor.py` hash, exact target/source,
original input hashes, complete output and readback in a fresh append-only
receipt. Preserve the old verdict and attribute any changed interpretation to
the new examiner; do not relabel a fixture as production acceptance. This
active-workload assessor cannot accept the zero-send idle canary below.

## Existing allocation and pool budget

The existing allocation is 512 MiB and 0.5 CPU. The retained **432.7 MiB OFF-state
peak** leaves only 79.3 MiB against that historical peak and cannot qualify an
active worker. Do not add constructor RSS to that sample or infer steady headroom.
The prior 90-second host stop setting needs current control-plane confirmation;
an unset worker drain value is not a confirmed 60-second configuration.

The conservative client worksheet, from the actual engine factories, is:

| Population | Maximum clients |
| --- | ---: |
| One web process: legacy 5+10, requests 5, audit writer 1, restricted reader 1 | 22 |
| One separately owned social process: pool 2, overflow 0 | 2 |
| Proposed web plus social subtotal, before other clients and reserve | 24 |

Source: `backend/database.py:56`, the request/reader/writer factories in
`backend/request_database.py:129`, `backend/social/worker/config.py:78`, and the
linked accounting addendum. Inventory every destination, role and endpoint before applying a
common pooler limit. The earlier observed 200 pooler clients, 15 backend
connections per user/database and 13/60 direct occupancy have different units
and populations. The worksheet is **24 + other clients + accepted reserve <=
the applicable client limit**; it is not a backend reservation or current usage.
No positive reserve or complete other-client inventory has been accepted here.

## Future worker-only canary, requiring a separate owner decision

The proposed limit is one existing-container supervisor, one native worker,
one external slot, **180 attended seconds**, followed by bounded stop and OFF
restoration. There are **zero selected delivery targets, zero uploads and zero
provider sends**. It tests paused startup, idle scan/heartbeat, actual capacity
and stop on the intended host. It cannot accept active queue processing,
media inspection, provider recovery, daily egress or a seven-day operating rate.
Queue/recovery execution remains an offline fixture until a separately approved
real workload and its prerequisite media/provider/retention gates are accepted.

Before authorization, name the operator, receipt custodian and independent
closure reviewer; confirm exact deployment/package/role/endpoint identity,
current host shutdown window, memory/CPU/client reserves and storage-read gates.
Require a fresh census with no retained owner, actionable/processing/reconciling
targets, live or expired leases, or unfinished intents, and prevent admission of
any such work during the window. Otherwise keep this idle-only canary held;
do not clear or merely classify retained work to make it eligible. Global pause
alone does not suppress all recovery reads (`backend/social/worker/repository.py:30`;
`backend/social/worker/runner.py:71`). A positive empty census cannot authorize
clearing an existing owner. Keep the separate admin ETL
consumer and GitHub nightly writer in the client inventory. Do not create a
service, credential, grant, resource, plan or monitoring product.

The proposed explicit profile is the current fixed one-worker Gunicorn command,
`SOCIAL_WORKER_SHUTDOWN_SECONDS=60`, one slot, pool 2/no overflow, two shared
executor threads, statement/lock timeouts 5s/2s, active scan/heartbeat 5s/15s and
idle scan/heartbeat 60s/60s. These values follow
`backend/social_worker_supervisor.py`, `backend/social/worker/config.py` and
`backend/social/worker/runner.py`. Use existing protected worker DSN/role/media
references; never copy credentials into argv or evidence. Native, material-read,
operational-attestation and supervisor switches require their own accepted
prerequisites. A startup pass is not permission to set an attestation.

Publishing, account publishing, HTTP uploads, retained writes, financial
generation, automatic approval/scheduling/publishing and native/automatic source
admission remain OFF throughout. Any temporary native/supervisor/material-read
switch values must be explicitly listed in the later authorization, observed
after resolution, and restored to the recorded OFF baseline. No automatic restart.

Record the actual instance, launcher PID/group, fixed child argv, worker
PID/group, exact owner/generation and original inherited-pipe custody. Observe
the initial scan and heartbeat by 15 seconds, then idle observations by 75 and
135 seconds. The API's 150-second idle freshness window does not prove process
availability; launcher/process evidence is required. Use bounded 5-second
resource observations with no gap above 15 seconds. Retain full raw logs and
counters, including observer overhead, and compare the complete before/after
queue, intent, owner/history and flag witnesses.

Abort on any OOM/kill, peak above 460 MiB, current memory at least 480 MiB,
reserve below 52 MiB, mean CPU above 0.4 core, applicable client/backend reserve
loss, API p95 above 1s or any request above 3s, readiness failure, missing/stale
scan, extra process/slot/connection, changed source/endpoint, unexpected provider
or object operation, any newly actionable work/lease/unfinished intent, or lost
custody. Missing telemetry aborts qualification.
Stop admission, signal only the owned groups, allow drain at most 60 seconds,
require measured whole stop at most 75 seconds and web/reap below 10 seconds
inside the separately confirmed host window. Preserve existing larger-scope
shutdown receipts; this narrow observation does not replace them.

## Recovery, OFF restoration and owner input

A clean signal, zero child exit, elapsed deadline or fresh heartbeat never
releases ownership. The independently authenticated original launcher receipt
must positively prove joined groups, provider/executor closure and drained
claims for the exact owner/generation. Only a separately authorized privileged
operator can use the existing fenced release path after inspecting all retained
work. Restricted worker credentials cannot release. Failed or ambiguous closure
or commit retains ownership/history and stops the canary; no TTL, force clear,
DELETE, schema rollback or automatic retry is proposed.

Restore the recorded flag baseline through the later authorized control plane,
read back the resolved OFF values, positively prove worker/supervisor absence,
and compare queue/intent/asset/upload/publication/attempt witnesses. Preserve
new legitimate owner/history/heartbeat metadata explicitly; do not claim an
identical database fingerprint after an acquisition. OFF restoration is
incomplete if process absence or protected state is uncertain. Keep additive
schema/history and do not roll back to a provider-capable binary that ignores
the permit.

The specific missing owner inputs are a positive memory/CPU/client reserve and
complete other-client/role topology, current host stop-window confirmation,
named operator/custodian/reviewer, accepted native/material/retention gates,
and an explicit decision approving this exact 180-second zero-send profile and
its acquisition/release/restore actions. No request for that authorization is
made by publishing this proposal. A later real media/delivery pilot needs its
own reconciled asset/target/rate/recovery bounds and explicit authorization.
