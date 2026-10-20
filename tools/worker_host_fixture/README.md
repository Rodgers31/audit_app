# Existing-service worker qualification

This opt-in **maintenance image** is separate from the production Dockerfiles.
It is not selected by any default application flag or startup path. The image
has not passed target-host acceptance merely because its unit tests pass.

The user accepted brief maintenance on 20 October 2026. Do not run this alongside
the live API in one 512 MiB instance. Do not add a service, paid disk, job, plan,
Actions run, bot review, credential or database access grant for qualification.

The build validates the complete exact-version lock before installing anything,
then installs one distribution per pip process with a fresh environment and all
pip configuration disabled. Every installed version is read back and final
`pip check` must succeed. This bounds retained installer state without changing
the locked runtime versions or treating a failed installation as a usable image.

## Boundary and actual workload

The entrypoint requires actual outer PID1, nonroot UID/GID10001, 512 MiB without
swap and exactly half a CPU. It re-execs with an empty production environment,
admitting only a validated public port. It changes user/mount/network namespaces
without changing the actual container PID1. No mount syscall is attempted: all
inherited mounts must already be private. Loopback is the only usable network.
The static copied root contains Python, PostgreSQL17, ffprobe, public application
source and synthetic helper data. Root-owned source is outside the single UID
map. Chroot is followed by complete capability/bounding/ambient removal and
no-new-privileges. A fresh Python exec checks those properties, absence of proc
and sys, real null stdin/ordinary stdout pipes, descriptor inventory and source
write refusal. Missing support refuses; there is no host-network fallback.

The actual application supervisor ultimately execs as **outer PID1**. Its real
Gunicorn and native commands run unchanged, with the actual restricted database
role contract. PostgreSQL, TLS Graph/auth/R2 stand-ins, protocol proxy, image
seeding, capacity driver and kernel observer all share the service cgroup.
RLIMIT_NOFILE512 and RLIMIT_NPROC128 add descriptor/process limits; these are not
a substitute for the aggregate memory/CPU cgroup. The local Docker test also
uses pids.max128. Render's inherited pids.max must be separately recorded.

The observer retains only a fixed public maintenance listener and read-only
kernel observation outside the chroot, in the private network. Native/app code
gets neither that listener nor any outside directory/proc/cgroup descriptor.
Ordinary requests, including `/health/ready`, return503. `/fixture-health` means
only fixture liveness and returns200; it never claims application readiness.
Within the private root, the actual API must pass readiness/upload refusal and
the same actual API/native operations and 180-second qualification thresholds
as the qualified local fixture. All nine human-approved synthetic targets are
prepared before the API/native processes start. A bounded PostgreSQL update sets
their actual next_action_at values to0/0/0/25/50/75/100/125/150seconds after the
measured database clock, before releasing the native gate. The worker's genuine
due-queue logic drives sustained activity; no claimed provider operation is
simulated by the driver. Exact target/time readback is retained. Lightweight
psql snapshots avoid concurrently importing the heavy test seeder.

Fresh private network namespaces prohibit unprivileged TCP443. This image keeps
all capabilities dropped and changes no host sysctl: its explicit fixture-only
socket shim translates only127.0.0.4:443 to127.0.0.4:8443, with a matching inert
server bind. URL/SNI/certificate and actual SDK/HTTP operations remain unchanged.
The translation is recorded in launch identity; production TCP443 parity is not
claimed. No other destination is translated and no external route exists.

Verification advises dropping unused source-file cache pages after hashing.
The frozen helper generates its exact JPEG and TLS certificate in a short-lived
preparation process. The resident synthetic endpoint uses the identical protocol
class with stdlib TLS and those prepared bytes, avoiding resident image-generation
and certificate-generation libraries. The real API/native allocators and the
qualification limits are unchanged; measured cgroup values decide.
The fixed internal `/harness` alias resolves to a deep immutable source path so
the existing rehearsal module can import without changing its qualified bytes.

The driver emits `HOST_FIXTURE_READY_FOR_RENDER_STOP` only after requalifying
the raw current-run dataset, current observer/census/source hashes and exact
seeded image cohort. It then exits. It never sends a shutdown signal on success.
Raw workload observations are retained before assessment even when the capacity
gate refuses them. Render must stop the real outer supervisor when the accepted deployment is
restored. A600-second watchdog or any failed workload sendsTERM only to this
explicit fixture PID1 and emits failure; neither counts as a Render stop pass.

## Evidence and recovery boundary

The fixture-only Python startup shim preserves the B27 observation seams. It
copies raw Python lifecycle lines while keeping Render stdout direct, so final
PID1 output does not depend on a dying observer forwarding a pipe. It does not
invent a launcher proof. After the actual native code closes resources and
prepares its genuine private-pipe receipt, the shim first captures a consistent
bounded dump of **only the inert local fixture database**, then passes the
original receipt bytes unchanged. The authentic supervisor must still reap the
worker group before adding process_joined/exit_code proof.

Backup and capacity artifacts use complete numbered log chunks with run, build,
producer, size and SHA256 binding. `decode.py` rejects missing/duplicate/foreign
chunks, malformed encodings, trailing streams and expansion beyond4MiB. Expected
run/build/producer identities must come from the reviewed build and launch record,
not be trusted merely because they appear in downloaded chunks. The capture is
an off-host backup/restore exercise. **It does not prove persistence of Render's
ephemeral disk.** Restore into an owned local PostgreSQL fixture, compare the
retained owner/history with the actual native and launcher receipts, then execute
the existing guarded release/rollback/contender controls there. Missing stop or
backup evidence remains a failed/incomplete acceptance, never an inferred pass.

Only public synthetic data appears in these exports. Production publishing,
uploads, native activation and configuration stay OFF. Simulated publication
goes only to private loopback fixture endpoints. No production DSN, keys, token,
account, media object or public provider mutation is passed into the root.

## Concrete maintenance configuration and rollback

Before changing Render, record source/build IDs, all existing service settings,
accepted deployment identity, effective OFF flags, health and retained data.
The currently accepted backend is e26d142dd1aa02b817f19957411b16788c356420,
configuration deployment dep-dbbr198ae00c73aj98qg, schema a756b20a0001 on existing
service srv-d6hr3t5m5p6s73bomqu0. No migration is part of this fixture.

The proposed temporary settings are: root directory empty, repository-root Docker
context `.`, Dockerfile `tools/worker_host_fixture/Dockerfile`, blank Docker command,
health path `/fixture-health`, auto-deployOFF and the existing90-second stop
window. Production environment values are not edited; entry discards them before
executing any helper. A bounded target-host qualification trial requires frozen
runtime source, target-architecture build/import checks, exact dependency readback,
independent review, confirmed isolation/resource admission, an available accepted
rollback artifact and the user's maintenance authorization. Current production
defaults remain unchanged in Git.

B27's full local aggregate qualified on ARM. The B28 lean ARM variant completed
the workload but exceeded the460MiB reserve (490012672B peak), so it is not a
capacity pass. A discarded setup-cache experiment hit the480MiB abort. Local
x86_64 emulation refused an extra inherited descriptor; that guard was preserved.
These failures remain distinct from a physical target-host trial. Only measured
target-host data satisfying the unchanged thresholds can establish host capacity;
the trial never authorizes production worker activation.

Keep Chrome open and supervise the window. Abort on namespace/config refusal,
missing post-exec evidence, readiness/role failure, stale observer, 480MiB current
memory, any OOM, API latency above3s, failed capacity qualification, missing
export chunks or unexpected public connectivity. On success restore immediately
after READY, also capturing the Render deployment termination event and raw
launcher stop lines. Reserve75 seconds for measured stop within the90-second
host window. A watchdog timeout is failure, not an automatic rollback.

Rollback restores root directory `backend`, Docker context `.`, Dockerfile
`./Dockerfile.prod`, blank Docker command and the original blank health path.
Restore the exact accepted existing image/configuration deployment through
Render's rollback UI; do not rebuild ranged production dependencies and call it
the same image. Keep auto-deployOFF,90-second delay and every existing production
activation flag unchanged. Verify actual accepted source identity, live/ready200,
two connected accounts with publishingfalse, unchanged owner/history and media
census, and all effective OFF flags before ending maintenance. If browser control
fails, the operator must restore that accepted deployment in Render; do not leave
the maintenance image unattended or claim rollback happened automatically.
