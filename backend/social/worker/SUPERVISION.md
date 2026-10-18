# Global ownership and existing-container supervision

This increment is default OFF. It supplies local engineering acceptance, not
production activation or host-capacity acceptance. Parents #545/#476/#488 remain
open. No new service, scheduler, paid reviewer, upload or publishing flag is
introduced.

## Operating contract

The image enters the stdlib-only `social_worker_supervisor` module. With
`SOCIAL_WORKER_SUPERVISOR_ENABLED` absent or exactly `false`, it immediately execs
the same Gunicorn argument vector as the prior image. PORT (including its empty
fallback), WEB_CONCURRENCY and request recycling retain their existing meaning.
No social module, database, SDK, scheduler or resident extra process is created.
Invalid flag values refuse startup.

With the flag exactly `true`, the launcher owns one Gunicorn process group and
one fixed `python -m social.worker` process group. Web concurrency cannot multiply
the social child. The child receives `--database-url-env
SOCIAL_WORKER_DATABASE_URL`, never the DSN itself. It verifies the dedicated
restricted login and existing native/material gates before acquiring authority
or constructing provider resources. No implicit DATABASE_URL fallback exists.
Required server settings are SOCIAL_WORKER_DATABASE_URL, SOCIAL_WORKER_ROLE,
optional SOCIAL_WORKER_DATABASE_SCHEMA (public), existing native/operational
configuration, and explicit SOCIAL_WORKER_SHUTDOWN_SECONDS in [1,300]. This last
value is a declared local drain deadline, **not** an accepted Render stop budget.
Do not enable any setting from this document without separate coordinator
acceptance.

Initial worker profile: one external slot (accepted code ceiling two), two DB
connections/no overflow, two shared DB/native I/O executor threads, active scans5s, idle scans60s,
active heartbeat15s and idle heartbeat60s. Connections use lock timeout2s and
statement timeout5s. These limits and the explicit schema path are reapplied with
snapshot-free `SET LOCAL` statements at every transaction boundary, because a
pooler can discard libpq startup options. An unpinned maintenance engine keeps
its login search path and can still select read-only REPEATABLE READ. Each
transaction adds one batched driver call, without increasing pool size.
A known earlier due time shortens an idle wait. Work newly
queued just after a scan can wait60s. Global/platform pauses still suppress
normal queue claims and wakeups; bounded processing/reconciliation reads retain
all prior read/admission/uncertainty budgets.

## Authority and lock order

The narrow migration `a545b14a0001` follows `a490b15a0001`. Its singleton
`social_worker_runtime_ownership` reserves the entire worker budget. Generation
history is append-only in `social_worker_runtime_history`; acquisitions increase
the historical maximum even after release. There is no TTL, heartbeat expiry or
age-based takeover. A crash, ambiguous commit, failed closure or hard kill retains
the owner, queue and uncertainty evidence. A contender refuses GLOBAL_WORKER_OWNED.

Acquisition validates the actual singleton primary key/check/trigger presence,
then atomically inserts owner and acquisition history and verifies stored values
before commit. Invoker triggers enforce generation/history consistency. Both
tables have RLS and no PUBLIC/anon/authenticated access. The restricted worker
can insert an acquisition and acquired-history record, read history and lock the
owner row. It cannot clear an owner, rewrite history/generation, release, delete,
truncate, or gain definer authority. The reviewed role verifier checks exact
new trigger source/wiring/search path and exact grants/policies. No production
role or grant is installed by the migration or launcher.

A typed authority is also tied to its acquiring process and one bound
SocialWorker. Constructed copies and fork inheritance do not authorize a runtime.
Every queue scan, recovery, claim, load and intent rechecks durable ownership.
Lock order is **global owner → controls → account → publication → target**;
claims lock global then due targets. No database transaction spans external IO.
Operation receipts retain runtime owner/generation. Stale authority can append
late evidence to its exact existing claim/intent, but cannot transition a target
or admit another operation. The process-local guard is an API safety boundary;
compromised Python code or privileged database administrators are outside it.

Late evidence requires the original process-issued reference and the intent's
recorded runtime owner/generation. Missing or copied references cannot settle an
attempt, and a successor cannot settle its predecessor's operation. One runtime
refuses concurrent `run()` calls; direct `process()` callers share its fixed slot
budget and tracked shutdown drain. `close()` waits for those calls before
unbinding the runtime; waiting callers admit no intent after stop.

Non-native CLI is now a separate `--once`, zero-target diagnostic. It constructs
no provider or authority and refuses a nonempty target table. All provider-capable
CLI modes, including native `--once`, use the global permit.
At the CLI boundary cancellation returns sanitized exit 1 after cleanup, while
KeyboardInterrupt returns 130. Neither produces a successful closure receipt.

## Supervision and shutdown evidence

Unexpected worker exit emits `social_worker_unavailable`, retains ownership and
leaves web available. There is no automatic restart. Web/master exit stops the
owned worker group and returns nonzero. Routine Gunicorn ASGI-worker recycling
cannot create another social child. Logs distinguish starting, unavailable,
joined and forced-kill outcomes; signalling is never treated as completion.

SIGTERM/SIGINT coalesce from startup through resource disposal. The CLI stops new
claims/intents and uses a self-pipe to wake a sleeping asyncio selector. Existing
tasks drain, the DB executor joins, native clients close, and durable outstanding
claims/intents are checked. A private inherited pipe carries a bounded typed
closure receipt only after successful closure and engine disposal. The launcher
adds process_joined only after wait/reap and full group disappearance. Malformed,
missing or failed receipts produce no release proof. No receipt automatically
releases ownership.

Worker drain consumes the declared deadline; web is then stopped within its
remaining time. On deadline, only owned groups receive SIGKILL. Reaping has a
finite additional allowance (up to2s direct wait +2s group observation per child).
Linux enables subreaping and reaps adopted group descendants. Any unresolved
cleanup is logged and cannot certify clean shutdown. Actual host stop interval
must accommodate measured whole-container shutdown, including reap allowance;
this is **not yet accepted**. Host SIGKILL cannot produce a clean receipt.

The existing API status is a heartbeat observation with its existing age window;
it does not consume the launcher's immediate exit event. Use launcher events
and exact process evidence for operator supervision. A future API change must
explicitly integrate deployment-bound supervisor availability; do not interpret
a recently cached heartbeat as proof a process is alive. Shared API files are
outside this lane and unchanged.

## Manual handoff and rollback

An operator with separately authorized privileged credentials may call
`ownership.release_authority(engine, RuntimeAuthority(old_owner, generation),
proof)`. Never pass credentials in argv. Authenticate receipt custody to the
exact old host/build/process and retain its positive joined-process, executor,
SDK/provider-closure evidence. Version1 proof requires exact keys:

```json
{"version":1,"owner_id":"<old UUID>","generation":1,"process_joined":true,"worker_exit_code":0,"providers_closed":true,"executor_closed":true,"claims_drained":true}
```

The privileged release rechecks owner/generation under the same global lock,
locks delivery tables, refuses any lease, processing/reconciling/unknown target,
account hold/admission or unfinished intent, appends release evidence and deletes
exactly one current owner in one transaction. Settled historical ambiguity is
retained and does not by itself block release. Invalid proof, stale generations,
active work, missing rows or uncertain outcomes refuse. The restricted worker
cannot execute this procedure. The database cannot authenticate external host
receipt custody; that positive operator verification remains mandatory. There is
no force/expiry option or automated release after a nominally clean exit.

Any acquisition or release history prevents destructive downgrade, even if the
current slot is empty. Empty-schema downgrade alone is supported. Rollback to
older binaries first disables native/supervisor settings, positively stops and
reaps old processes, preserves owner/history/queue evidence and resolves unknown
work. Old binaries ignore the new permit; elapsed time never makes rollback
safe. Keep the additive schema/history during rollback. Do not run this migration
in production as part of the draft PR.

## Local acceptance and remaining gates

Focused tests use synthetic providers and an independently assigned PostgreSQL17
on loopback55484 (`SOCIAL_GLOBAL_OWNER_TEST_DATABASE_URL`, database
social_domain_test), with unique per-case schemas/roles. Historical port62124
and its guards are unchanged. Compatibility modules replay existing assertions
under this independent fixture. Process tests use actual signals, owned groups,
crash/deadline controls and DSN-free child argv. Migration tests exercise real
upgrade/empty downgrade/history refusal and restricted role denial.

A real60s local idle observation with the transaction-boundary repair measured
12 driver executions per empty steady scan, with no provider calls. The earlier
eight-execution observation predates this repair. At one scan/minute the new
profile extrapolates to17,280 driver executions/day, plus pool pre-ping, startup
and incidental work. A batched timeout/path setup contains multiple SQL
statements: this driver count is **not** a server statement count, billed-query,
egress or provider-cost receipt. Local
macOS Python3.13 idle RSS was about74MiB with no native SDK/provider clients;
Render Python3.12/native-client RSS, CPU, egress and shared DB headroom require
separate measured acceptance. No zero-total-cost claim follows.

Before activation: accept actual Render host shutdown interval and capacity,
production migration and restricted-role certification, API observation limits,
key/privacy/media/provider gates, rollback/receipt custody and real operator
closure. All publishing/native/upload/retained-write flags remain OFF until then.

Coordinator follow-ups are tracked separately in #685 (issued intent completion) and #686 (direct-call bounds and shutdown drain). These concern unmerged candidate defects and local inert reproductions; they are not claims of production provider activity.

## Uploads-off native material reads (Batch15, #700)

`SOCIAL_WORKER_MEDIA_READS_ENABLED` is an independent, strict, default-false
opt-in. With the existing native/material/operational configuration validated,
it permits native material reads while `SOCIAL_MEDIA_ENABLED=false`. The read
configuration validates the same R2 endpoint, bucket, credentials and inspectors;
it does not override the HTTP flag. Native material receives only head, bounded
download and signed preview methods, with no upload/finalization/deletion or SDK
client port. The underlying SDK is still owned and closed by native composition.

The web application keeps its separate disabled upload runtime. When the native
registration needs material reads it owns a separate read client; HTTP upload
capabilities remain unavailable. Legacy upload-enabled composition keeps its
existing enablement requirements. This separation does not establish live
storage permissions, provider readiness, resource capacity or operational gates.

`tools/worker_rehearsal/README.md` documents the opt-in internal-network Linux
rehearsal with the actual supervisor, Gunicorn/API, native CLI, HTTPX/boto3 and
owned PostgreSQL. It includes positive pipe custody, sticky crash ownership,
privileged release rollback and a sustained bounded workload. Only its retained
source-bound results establish what ran; this document is not acceptance proof.
The supervisor now emits measured worker stop and web/reap durations. No local
drain setting is installed automatically and no production configuration changes.
