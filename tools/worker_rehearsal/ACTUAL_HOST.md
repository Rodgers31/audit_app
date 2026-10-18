# Coordinator procedure: actual-host acceptance remains separate

This is an unexecuted procedure for #699, not authorization to activate anything.
The Render90s setting was independently saved/read back before this lane. Both
prior temporary credentials are revoked. Do not repeat that setup. This lane
performs no deployment, cloud change, live grant, upload or public publication.

## Preconditions and custody

1. Review the candidate PR and full source-bound local receipt, including failed
   attempts and independent Spec/Standards reports. Read back the exact deployed
   Git/source and image identity after any separately approved release. Compare
   architecture, Python/Gunicorn/SDK versions and resolved environment against
   the tested fixture. The local image is Linuxarm64/Python3.12; it is not proof
   of the actual host's architecture or dependency parity.
2. Keep global/account publishing, HTTP uploads, retained writes and automatic
   generation/approval/scheduling/publishing OFF. Record the actual existing
   operational gates. Never change OPERATIONAL_GATES_VERIFIED merely to run
   qualification. If prerequisites are unaccepted, this live step stays blocked.
3. Compare actual API concurrency, DB mode/TLS, pool sizes, no-overflow settings,
   one shared two-thread DB/native I/O executor (at most three native threads including main), one external slot and5s/2s transaction limits.
   Match existing auto-seeder/scheduler settings and representative read traffic;
   the local fixture disabled auto-seeding and used fresh local county references.
   Its read-only source can refuse unrelated bootstrap cache writes. These are
   explicit parity limits, not successful production checks.
4. Acquire the real shutdown evidence through a coordinator-controlled channel
   bound to exact service instance, deployed source, PID1 launcher, fixed child
   argv/PIDs/groups and database owner/generation. Archive complete raw logs before
   a restart. The anonymous inherited pipe goes only to the native child; the
   launcher appends joined-process proof after wait/reap and group disappearance.
   A copied JSON object, application heartbeat, synthetic child, signalled PID,
   elapsed deadline or client constructor RSS cannot establish custody.

## Actual-host execution boundary

The local Docker producer is not a command to run inside Render. It requires a
local Docker daemon and owned internal-network fixtures. Do not install Docker,
provision a paid service, add workers/schedulers, change DNS on the live host or
point simulated publishing requests at real providers to reproduce it there.

A forced-kill or processing rehearsal on the actual host requires a separately
owned, pre-existing isolated database and inert endpoint route with blocked
public egress. It must use the same native CLI/SDK and fixed supervisor commands,
not dummy children or substituted lifecycle results. Record that route's resolved
inputs and absence of production credentials. If such a fixture is unavailable
under the current permissions/cost constraints, actual-host processing and kill
acceptance remain EXTERNALLY BLOCKED. Do not create an unreleasable sticky owner
in the production database for a forced-kill experiment.

For a separately approved *paused* actual-service stop after all operational
prerequisites are independently accepted, the concrete proposed profile is:

```text
SOCIAL_WORKER_SHUTDOWN_SECONDS=60
SOCIAL_WORKER_MEDIA_READS_ENABLED=true
SOCIAL_MEDIA_ENABLED=false
SOCIAL_MEDIA_RETAINED_WRITES_ENABLED=false
WEB_CONCURRENCY=1
```

The existing native/supervisor gates remain independent approval steps. All
publishing controls stayfalse. Do not activate them through this document.
Use the actual dedicated restricted worker DSN/role/TLS via existing protected
environment references, never command arguments, copied vaults or new grants.
The local60s value is explicitly tested in the owned rehearsal; no host value is
installed by this PR. Require measured worker stop, web/reap, full owned-group
absence and whole-container stop inside90s. Local acceptance reserves30s beyond
drain and refuses total>75s or measured web/reap>=10s. Actual-host uncertainty may
require a smaller deadline or topology rejection; do not increase the host window
or resource plan automatically.

First observe the exact acquired owner/generation, no provider/storage operations,
HTTP upload capabilitiesfalse, authenticated upload issuance refused, bounded
connections and API readiness. Abort on OOM, near480MiB, wrong process/resource
profile, credential/endpoint mismatch, API error/max3s, new publishing permit,
unexpected egress, missing custody or unresolved claim. A stop/timeout never
proves a request unsent. Missing proof means ownership/history stay retained.

## Guarded release and rollback

Only the coordinator, using separately authorized privileged credentials, can
release. First authenticate the launcher receipt's custody, old source/instance,
owner/generation and positive closure of all resources/groups. Require the exact
version1 proof keys; do not fill in absent fields. Restricted worker
credentials cannot release. No timeout, TTL, force option, DELETE/TRUNCATE,
manual proof insertion, history rewrite or sticky-owner clearing is allowed.

The reviewed function is `social.worker.ownership.release_authority`. A concrete
coordinator invocation uses protected DSN and verified proof *files*, not secrets
in argv (this snippet is deliberately not an executable deployment action):

```python
import json, os
from uuid import UUID
from social.worker.config import WorkerConfig, create_worker_engine
from social.worker.ownership import RuntimeAuthority, release_authority
proof = json.load(open('/coordinator/verified-launcher-proof.json'))
old = RuntimeAuthority(UUID(proof['owner_id']), proof['generation'])
engine = create_worker_engine(WorkerConfig(os.environ['COORDINATOR_RELEASE_DATABASE_URL'], database_schema='public'))
try:
    release_authority(engine, old, proof)
finally:
    engine.dispose()
```

This function re-locks the exact owner/generation and delivery tables, refuses
leases, processing/reconciling/unknown work, account holds and unfinished intents,
then appends release history and removes exactly one owner in one transaction.
Read back the owner census and immutable acquired/released rows after commit.
A failed/ambiguous commit is uncertainty requiring inspection, not permission to
retry or clear state. The local tool injects a genuine post-history DELETE failure
and verifies transaction rollback, then tests valid release, stale refusal and
native generation2 acquisition.

Rollback first keeps every native/supervisor/publishing/upload gate OFF and
positively stops/reaps the old process tree. Preserve all owner/history/queue and
remote evidence. The local web-only rollback preserves generation1 and history,
then a separately validated release permits generation2. Keep additive schema
and immutable history; do not downgrade or run old provider-capable binaries
that ignore the global permit. A hard-killed owner without positive proof stays
retained and blocks successors; reconcile through the approved recovery process.

## Scope of acceptance

Local results are CODE IMPLEMENTED/TESTED only. Actual-source deployment, host
whole-container acceptance, sustained production API/worker capacity, TLS/pooler
protocol/billed egress parity, real-provider/media/recovery/retention gates and
representative closed-day/seven-day operating evidence remain separate. No local
protocol extrapolation or combined constructor RSS certifies those gates.
