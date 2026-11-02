# Existing-service worker qualification

This opt-in maintenance image is separate from production Dockerfiles and startup
flags. Publishing, uploads and production worker activation remainOFF. The user
accepted brief maintenance on20October2026. Use only the existing512MiB/0.5CPU
service; do not add plans, resources, credentials, hostedActions or bot reviews.

## Mountless public runtime boundary

Render rejected both build-time creation/extraction of a copied null device and a
private-child runtime bind. The B29 image therefore uses the container engine's
real `/dev/null`, a public image root, private USER/MOUNT/NET namespaces and
unprivileged Landlock filesystem confinement plus an inherited seccomp filter.
It performs no mount or chroot syscall. Path metadata remains visible; content
outside an explicit allowlist is denied. This is a changed qualification boundary,
not a claim that the failed copied-root image passed.

Actual outerPID1/nonroot10001 is required. Entry re-execs with only a validated
public port and fixed clean markers, closes all descriptors above2, and never
passes production credentials into the workload. The private NET namespace has
loopback only and must refuse an outside connection with ENETUNREACH. UID0 is
unmapped by the single10001→10001 map, so immutable image paths appear as65534.
All capabilities and bounding/ambient sets are removed; no-new-privileges is set.
RLIMIT_NOFILE512/NPROC128/core0 and the actual512MiB/no-swap/half-CPU cgroup remain
required. The resource assessor and thresholds remain unchanged.

The synthetic PostgreSQL cluster uses1MiB WAL segments instead of the default16MiB.
PostgreSQL consequently initializes min/max WAL sizes to5/64MiB rather than80/1024MiB;
this fixture checkpoint/retention profile is recorded and is not production database
parity. fsync, synchronous_commit and full_page_writes remainON; no no-sync option
is used. The synthetic cluster also uses2MiB shared_buffers. PostgreSQL17.11
readback changes automatic wal_buffers from256 to64KiB and total configured shared
memory from15 to8MiB, with smaller buffer descriptors and related structures.
This changes fixture cache/I/O behavior; it does not prove a net cgroup saving.
The full workload, actual kernel peak, SQL, latency, CPU and closure checks remain
required at their existing limits. API probes make the same bounded real HTTP requests from the resident
driver, avoiding an extra Python process per request. Native/API processes, nine
targets, SDK/TLS calls, resource observation and all acceptance thresholds remain.
Failed capacity assessments export their raw UNASSESSED observations under
capacity_failed before re-raising. They never emit qualified capacity or READY.
The inert endpoint also drains ignored multipart uploads in64KiB reads and streams
the prepared JPEG in16KiB blocks instead of buffering/caching another whole copy.
It hashes the same opened file, preserves exact headers and checks delivered
length/digest before a completed request event; short writes or changed bytes fail.
The JPEG dimensions/content, wire lengths, hashes, TLS and real native inspection
stay unchanged. These helper reductions require fresh full-workload qualification;
they are not subtracted from observed memory or treated as proved headroom.

Before any workload exec or thread, Landlock ABI3+ handles all filesystem rights
through REFER/TRUNCATE. Only public `/usr`, source/helper trees and fixed public
configuration leaves are readable. `/state`, `/evidence`, `/tmp` and `/dev/shm`
permit bounded fixture writes but not executable files, device nodes, symlinks or
filesystem sockets. The real null device permits reads/writes. Kernel proc/sys
content, secrets and other paths are not admitted to the workload. Fresh execs
must refuse opens of known-existing outside/proc/sys controls, pathname UNIX
socket creation, source writes and unexpected descriptors. Missing policy support
or any failed syscall refuses startup; there is no unconfined fallback.
The vendor resolver may retain one read-only public hosts-file descriptor. The
fresh-exec census admits only that exact immutable inode, owner, mode and access
mode; foreign, writable, duplicate or outside descriptors still refuse.

The seccomp filter checks native architecture and x32, refuses new namespace,
mount/chroot, ptrace/process-memory/FD-acquisition, perf/BPF and io_uring paths.
It permits IPv4/IPv6 sockets in the independently isolated network and only
AF_UNIX/protocol0 connected STREAM socketpairs for asyncio wakeups. Datagram pairs
and pathname UNIX client sockets are denied. PostgreSQL uses TCP only. Ordinary
process/thread creation inherits both policies; clone3 returns ENOSYS for libc's
ordinary clone fallback, while namespace clone flags are denied.

The pre-policy forked observer has its own Landlock/seccomp policy: public code,
read-only proc/cgroup content and writes only under `/evidence`. It retains only
the fixed maintenance listener opened before NET isolation. App code inherits
neither this listener nor outside descriptors. `/fixture-health` returns200 for
fixture liveness only; all ordinary paths, including application readiness,
return503. Observer aborts at480MiB current memory, any OOM or600seconds. These
failures do not count as a Render shutdown pass or automatic service restoration.

Docker/Render replace outer `/etc/hosts`. The image uses Debian's public
`libnss-wrapper` with an immutable, fixed synthetic hosts file and an explicit
B29-only environment discriminator. Preload path and hosts file must match the
architecture; partial/extra resolver configuration refuses. The library hash is
bound in the build manifest. Fresh Python execs verify every synthetic name/IP;
the real local PostgreSQL/libpq connection must also succeed before workload.
TLS verification and original Graph/R2 names/SANs are retained. The existing
fixture-only443→8443 translation remains explicit; production DNS/TCP443 parity
is not claimed.

## Workload and evidence

The actual application supervisor execs as outerPID1, with genuine Gunicorn and
native worker commands. Synthetic PostgreSQL17, the actual restricted worker-role
contract, private TLS/auth/Graph/R2 endpoints, wire proxy, capacity driver and
kernel observer share the service cgroup. Nine approved synthetic targets are
prepared before resident API/native work, then scheduled at0/0/0/25/50/75/100/
125/150seconds using the actual database clock and genuine due-queue logic.

The existing180-second workload must meet its unchanged460MiB peak reserve,
480MiB current abort,0.4CPU,3s maximum/1s p95 API limits, minimum API/sample counts
and sustained provider/wire activity. Raw observations are retained before the
assessor runs. READY is emitted only after actual source/run/cohort qualification;
the driver never sends a shutdown signal on success. Render must terminate the
real outer supervisor when the accepted image is restored.

The native closure shim captures a bounded consistent dump of only the inert
local database after resources close, then passes genuine receipt bytes unchanged
to the authentic launcher. The launcher must reap the process group and produce
its real closure proof. Numbered exports bind run/build/producer/size/hash;
`decode.py` refuses missing/duplicate/foreign chunks, malformed data and expansion
beyond4MiB. Downloaded chunks alone are not external identity proof. An off-host
dump/restore exercise does not prove persistence of Render's ephemeral disk.
Missing host stop, capacity or recovery evidence remains incomplete, never inferred.

The complete exact-version profile is validated before installation. Each of 93 pins
is installed in a fresh isolated pip process, read back, and followed by mandatory
pip check. The accepted production Python package versions must match before host
qualification. The OS
package inventory and vendor resolver hash are recorded rather than assumed.

## Maintenance configuration and restoration

Record the actual accepted source, configuration deployment, schema, flags and
retained data before any host trial. The following values are historical
20 October 2026 restoration evidence, not a current release or rollback target:
e26d142dd1aa02b817f19957411b16788c356420/configuration deployment
 dep-dbbr198ae00c73aj98qg/schemaa756b20a0001 on existing service
srv-d6hr3t5m5p6s73bomqu0. Establish a fresh accepted production baseline and exact
rollback artifact before any newly authorized host trial. This dependency update
includes no host-trial authorization; publishing, uploads, workers and financial
generation remain off. No migration or production environment edit is included.

Temporary build settings: rootempty, context `.`, Dockerfile
`tools/worker_host_fixture/Dockerfile`, blank command and unchanged blank health,
main/autoDeployOFF, existing90-second shutdown delay. Use only a frozen reviewed
commit with target-architecture build/import/version checks, demonstrated kernel
admission and a known accepted rollback artifact. Current host qualification is
pending; B27's local eight-case pass is historical local evidence, and B28's ARM
reserve/emulation-FD failures are not host passes.

Supervise Chrome. On READY, restore the exact accepted existing deployment image
through Render's rollback UI and capture actual stop/lifecycle events. Reserve75s
inside the90s host window. Also restore root `backend`, Dockerfile
`./Dockerfile.prod`, context `.`, blank command/health, main/autoDeployOFF. Do not
rebuild ranged production dependencies and call it the same accepted artifact.
Check accepted source, live/ready200, all12 effectiveOFF flags, unchanged retained
data, private media tables and both connected accounts with publishingfalse before
ending. If the candidate refuses or a guard fails, restore these settings without
relaxing policy or leaving a maintenance image unattended.

## Dependency maintenance — 31 October 2026

`requirements.txt` is the authoritative complete exact package profile. It replaces
the historical `requirements.lock` filename so native Dependabot can discover it;
the image still copies it to the installer's fixed `/input/requirements.lock` path.
The profile is refreshed from a fresh backend runtime plus the existing fixture
test tools. Obsolete python-jose/ecdsa/rsa/pyasn1 are absent; current application
JWT verification uses PyJWT. The installer validates the complete file before any child, then upgrades its
declared pip pin first and retains the other pins' order. The exact install and
pip check must pass before any
image rebuild is accepted. A package audit is not restricted-host qualification.

Every update PR must retain exact pins, pass `install_locked.py` in a fresh owned
environment, compare its complete installed distribution census, and repeat the
normal/optimized host boundary tests. Changes to Python, native libraries, framework
or resource behavior additionally need the unchanged native x86 host workload and
capacity/confinement acceptance before use. That workload was not run or activated
by this dependency refresh. The pinned 3.12.15 fixture base remains historical and
needs a separately verified 3.12.16+ base/image refresh before renewed qualification.
No historical fixture acceptance carries forward to the new package graph.

## Dependency maintenance — 2 November 2026, original proposals

The 93-pin profile advances pytest-asyncio 1.4.0→1.4.1 and Starlette 1.9.0→1.10.0.
This is a default-off maintenance-image dependency change, not production worker
or maintenance-image launch authorization. The earlier 90-pin/84-production-package
counts describe an older corpus; they are not a current parity receipt.

The retained 31 October production inventory contains 81 distributions (SHA256
`ea09035c5e8246cfc9a044ff9c71fbdc06ec8d16b55dcb1d5fa3057c05f10c17`).
Compared with this candidate, its shared versions differ in AnyIO 4.16.0 versus
fixture 4.15.1 (pre-existing) and Starlette 1.9.0 versus fixture 1.10.0. This archived
inventory is not a fresh live production readback. Production package parity is
therefore **UNMET**; the version-match requirement above remains in force.

Fresh exact installation, complete census, pip check, package advisory queries
and normal/optimized local boundary tests do not qualify the native restricted
host. The available local Docker host is ARM64; actual nonroot namespace admission
under its unchanged confinement refused `unshare` with EPERM. Neither emulation
nor relaxed container privileges substitutes for native x86 Linux acceptance.
Before any host use, establish a newly reviewed accepted production-version
baseline and matching fixture graph, refresh the separately pinned Python base,
then repeat the complete unchanged native confinement/cgroup workload, resource,
closure, recovery and actual host-stop qualification. All thresholds and activation
holds above remain unchanged.

## Captured native group addon — 2 November 2026

Native Dependabot #890 at `e69b993cdefa6b11459f239671015e658fa8304d`
additionally proposes FastAPI 0.156.8→0.162.0, pytest 9.1.1→9.2.0 and
SQLAlchemy 2.0.55→2.1.6 for this profile. The profile still has exactly 93 pins;
these are the only additional version changes. Earlier same-day package/test
receipts apply to the original-proposal graph, not this addon.

Against the same retained 31 October 81-package inventory, the addon differs
in four shared runtime packages: AnyIO 4.16.0 versus fixture 4.15.1,
FastAPI 0.156.8 versus fixture 0.162.0, SQLAlchemy 2.0.55 versus fixture 2.1.6,
and Starlette 1.9.0 versus fixture 1.10.0. The inventory is historical, not a
fresh production observation. Production package parity remains **UNMET**.

Fresh exact installation and local framework/database boundary checks must
qualify this specific graph. They do not qualify native x86 confinement,
resource capacity, recovery, host stop or production use. The pinned Python
base refresh, matching accepted production graph, unchanged host workload and
all activation/qualification requirements above remain mandatory. No worker or
maintenance image launch is authorized by these dependency changes.
