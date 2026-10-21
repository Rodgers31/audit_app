# Isolated native worker qualification

For a whole-fixture resource measurement, use the aggregate runner below.
The original multi-container runner described afterward measures the application
container only; its PostgreSQL, endpoints, proxy and controllers have separate
budgets. Those results cannot admit a concurrent full fixture on Render.

## Aggregate fixture

`bounded.py` reuses all eight actual worker cases while placing PostgreSQL17,
the TLS image/Graph/auth endpoint, protocol proxy, real PID1 supervisor,
Gunicorn API, native worker and every probe/controller payload in **one**
512MiB/no-swap,0.5CPU,128-PID cgroup. The host recorder and Docker daemon remain
outside that budget. Docker-exec payloads are inside it. FD limits are512;
`/tmp` and `/dev/shm` are16MiB each. Resolved daemon settings and kernel cgroup
limits are checked before starting PostgreSQL or the application.

Prepare an existing local application image with the locked backend dependencies,
pytest, psutil and ffprobe. Inspect and record its exact local ID. For example,
the coordinator's `b22-ffprobe:verified` image is suitable for local ARM64
functionality, but it is not AMD64 Render performance evidence. Build the opt-in
fixture using only the small harness directory as build context:

```sh
docker image inspect b22-ffprobe:verified
docker build --pull=false --build-arg BASE_IMAGE=b22-ffprobe:verified \
  -f tools/worker_rehearsal/Dockerfile.bounded \
  -t worker-bounded:local tools/worker_rehearsal
docker image inspect worker-bounded:local
python3 tools/worker_rehearsal/bounded.py \
  --image sha256:THE_INSPECTED_FIXTURE_IMAGE_ID \
  --out /absolute/fresh/path/outside/all/checkouts
```

The image ID is mandatory; qualification refuses tags or an implicit pull.
Retain the build log and resolved package/image identities. The opt-in build
installs official Debian PostgreSQL17 packages; it is not part of production's
Dockerfile or startup. No hosted service, resource, plan or workflow is created.
`--optimized --cases idle` adds a real optimized interpreter release/rollback
cohort; a partial case selection never establishes all eight cases.

There is no published port or external interface/route. Fixed loopback aliases
route real SDK calls to the inert fixtures. All Linux capabilities are dropped;
the root filesystem and copied application/harness are read-only. Only a fresh
inert evidence directory, a named PostgreSQL volume and bounded tmpfs mounts are
writable. The named volume has no filesystem quota: the fixed finite database
workload and positive volume cleanup are the declared local disk boundary, not a
claim of a hard disk quota. No production data, host home, Docker socket or
production environment is mounted or forwarded. Credential values and DSNs,
including controller overrides, must match the public inert contract.

Only tracked public backend source/assets are copied, with a32MiB admission
limit and hash checks. The harness is snapshotted before launch. Receipts bind
the complete measured source inventory and refuse source drift or missing
positive container/volume cleanup. Fixture migration identity is read back from
PostgreSQL and compared with Alembic's actual head.

The bootstrap runs PostgreSQL and inert endpoint/proxy helpers, then execs the
real supervisor as PID1. Helpers share its cgroup and die with that container.
After a stop/kill, an auxiliary container restarts only the owned fixture
database for census/release/rollback checks. It never overlaps a running worker
container. This tests recovery from real helper termination as well as custody.

This runner is **local acceptance tooling**, not a command to run inside Render.
Actual host architecture, source/runtime, isolation, maintenance admission,
whole-service stop, real provider/storage and representative operating costs
remain separate gates. A local aggregate peak cannot safely be added to an
already-running production API unless the combined budget independently fits.
Do not enable production operational gates, suspend the live API or add a plan
to make a rehearsal fit. Publishing and uploads remain off in production;
simulated fixture mutations never leave the isolated network.

## Original application-container fixture

This opt-in local tool runs the real `python -m social_worker_supervisor`, its
fixed Gunicorn `main:app` command and fixed native CLI in Linux. It does not call
Render, Supabase, Meta or R2. No production gate is enabled by this tool. The
Docker network is internal; the official-looking Graph/R2 names resolve only to
owned inert TLS endpoints. All credentials are public, inert fixture values.

Prepare a small build context (outside source) containing `Dockerfile` from this
directory and `backend/requirements.txt`. Build it as `b15-worker-runtime:local`.
The base Python image is digest-pinned. Cache `postgres:17` locally. The producer
refuses missing images instead of pulling during qualification. Both resolved
image identities, environment values and cgroup settings are retained.

```sh
python3 tools/worker_rehearsal/run.py \
  --out /private/tmp/b15-worker-qualification-unique
```

The output must be fresh, canonical, outside every checkout/Git directory and
free of symlink ancestors. No dotenv files are admitted. Database55390 and
API33501 are reserved; Docker internal networks do not expose these ports to the
host. API probes run in owned ephemeral containers on that internal network.
Docker requires a local authenticated daemon configured for the invoking user.
No Docker socket is mounted in a child. Names/labels and exact IDs bind cleanup, including timed-out transient probes. Any probe surviving its command fails qualification even after successful cleanup.

The eight cases cover a deterministically gated startup,65s idle observation,
TERM while an actual HTTP mutation is pending, repeated TERM/INT while actual
native closure is gated, native hard kill, whole-container SIGKILL, the full60s forced deadline, and
180s shared service load. The load queues an image plus text and additional text
every25s through150s; it requires actual SDK image transfer and provider activity
spanning120s. Capacity admission stays gated until the first county API response and CPU baseline. Actual SDK GET start/completion identities must fall inside the measured API window, using the shared Linux kernel monotonic clock. API requests use the real county route. Worker connection count is
observed continuously by the protocol proxy; PostgreSQL pg_stat_statements counts
actual server statements, including SET commands and trigger statements. Capacity records baseline and final per-query counters, rejects resets and reports their delta. Endpoint events carry the actual run/case identity. The image object path and provider account paths come from the seeded target’s database relationships; foreign events cannot satisfy qualification. Publication timestamps must fall inside the aligned wall-clock window. Wire
bytes include protocol traffic, not network/TLS headers or billed usage.

Every non-startup case authenticates against the inert profile endpoint, reads
HTTP media capabilities and attempts a one-byte upload intent: capabilities must
reportfalse, and the request must receive503/MEDIA_UNAVAILABLE. No grant is issued.
The worker uses `SOCIAL_WORKER_MEDIA_READS_ENABLED=true` with
`SOCIAL_MEDIA_ENABLED=false`. Paused cases keep global/account publicationfalse;
busy cases prepare explicitly approved isolated fixtures. Fixture setup reuses
existing domain/media test helpers; the resident worker uses real clients and
real PostgreSQL, without fake adapters or substituted lifecycle methods.

`sitecustomize.py` is mounted only in this rehearsal. It observes the real worker
budgets/client closure and adds explicit phase barriers. It does not execute in
the supervisor or Gunicorn processes. Gates delay real construction/closure;
they do not replace authority, role verification, adapters, clients, queue work,
executor shutdown or receipt code. The stalled closure deliberately requires
SIGKILL and must produce no positive proof. It is a retention test.

Thresholds and abort limits are recorded before launch in `predeclared.json`.
Shared service hard512MiB/no swap/0.5CPU; reserve52MiB; steady meanCPU<=0.40;
APIp95<=1s/max3s; one external slot, pool2/no overflow, one shared two-thread executor for database and native I/O; native process at most three threads including main; no OOM.
Idle server-protocol egress extrapolation must stay<=200MB/30days, separately
from measured requests and statements. Busy response traffic is bounded2MB for
the declared cohort, with client protocol traffic bounded4MB. The image fixture uses deterministic3000×3000 noise and exercises a multi-MiB JPEG. This is a fixture envelope, not a production bill or a
representative closed day. Source is read-only; reference bootstrap's unrelated
local cache writes can refuse, and this limitation is retained in API logs.

The launcher emits measured worker stop time and web/reap time. The selected
local60s drain reserves30s of the separately confirmed90s host window; the tool
requires total stop<=75s and measured web/reap<10s. The forced deadline case
actually consumes60s. These local bounds still require actual-host acceptance.

Clean exit never releases ownership. Each case checks a contender refuses.
The idle case replays a web-only rollback with the owner/history intact, rejects
invalid proof/restricted release, injects a real transactional DELETE failure
and verifies complete rollback, then releases via the captured inherited-pipe
proof. A subsequent real native CLI acquires generation2, closes, and preserves
all three immutable history events. No expiry/force-clear/downgrade exists.

Commands, raw stdout/stderr, snapshots and custody records carry producer and
source-inventory hashes. The final receipt hashes output artifacts, verifies
source stability and reads published JSON back from disk. It reports isolated
scope and `production_accepted:false`. Failed attempts remain diagnostic evidence;
rerun into a fresh directory after a repair. A partial `--cases` run qualifies
only its named cases; it cannot establish all eight or full capacity.

Use `--optimized --cases idle` for a separate real native/control Python-O release/rollback cohort. This option never reads optimization mode from the host environment. The runner records optimization readback in every controller result and the resolved native environment.


Qualification requires an exact completion for every observed provider/storage
request start and explicit upstream-failure counters in both wire snapshots.
The failure count must remain unchanged during busy and idle measurement.
Older receipts without these fields remain historical evidence; they cannot
qualify the current recorder. Run a fresh owned cohort before activation.
