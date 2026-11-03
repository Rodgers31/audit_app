# Current-release worker preparation

This candidate is based on accepted serving source
`2e206ed9974b254adf75b44867915e326d54487c`. It changes only acquisition
contention refusal and its worker regression fixture. It authorizes no production
deployment, configuration, process, acquisition, release or provider operation.
Issue #699 remains open. Publishing, uploads, workers/supervision and financial
generation remain OFF, as do automatic approval/scheduling/publishing and native
source admission. The ordinary admin ETL consumer and nightly GitHub ingestion
are separate execution paths and are not activated by this profile.

## Defect and recovery boundary

Two concurrent initial acquisitions can choose generation one from their INSERT
statement snapshots. The first commits its owner/history; the second's volatile
BEFORE trigger can then observe that history and raise PostgreSQL P0001,
`Global worker generation mismatch`, before the singleton uniqueness check.
Previously that error escaped the documented `GLOBAL_WORKER_OWNED` refusal.
It did not create a second owner or authorize a send.

`acquire_authority` now recognizes only that exact SQLSTATE/primary diagnostic,
after rollback of the failed transaction. A fresh bounded query must positively
observe the durable singleton before it returns the existing typed refusal.
Absent/hidden ownership and other errors retain the original failure; failed
observation propagates. The function never retries the INSERT or returns an
authority from this path. Ownership, immutable generation history, role grants,
uncertain claims and release rules are unchanged. The only production acquisition
caller remains the native CLI, before provider composition and queue work.

The regression forces the actual PostgreSQL interleaving with a test-only
advisory-lock BEFORE trigger. It proves one retained owner/acquired history row,
then exercises three diagnostic-without-owner refusals. Baseline normal and
optimized runs each failed the race and passed the three refusal controls;
candidate runs pass all four. This is disposable PostgreSQL evidence, not an
observed production contention incident.

## Serving identity and present holds

Read-only Render observations on 2 November 2026 Chicago found the existing
Starter service `srv-d6hr3t5m5p6s73bomqu0` Live at
`dep-dbkilahsrm7s73c2fv7g`, source `2e206ed`. Python 3.12.16/x86_64 and all
81 installed package versions match the accepted local serving image. A complete
23-file worker/launcher/build-profile mapping matches that source. This candidate
has not been deployed; its changed ownership hash must be admitted separately
after parent integration and ordinary release verification.

The existing named worker DSN and `audit_social_worker` role, app/key and private
media references are present. No values were exported. Schema is unset and uses
public; worker shutdown seconds is unset. The existing deployed
`python -B -m social.worker.role_admin --database-url-env SOCIAL_WORKER_DATABASE_URL
--role audit_social_worker --schema public --verify` returned fixed status `ok`.
No install/grant, resident worker, native/empty-queue diagnostic, native client
or acquisition was run.

A following restricted-role REPEATABLE READ/READ ONLY observation found
8 posts, 10 revisions, 0 targets/publications/attempts/assets/current owners/history,
1 historical heartbeat row, two accounts with publishing disabled, and global
publishing/automatic approval/scheduling/publishing false. Effective statement
and lock timeouts were 5s/2s. The heartbeat row is historical metadata, not a
running process. Supervisor/native/material-read and generation ceilings remained
false or unset; uploads stayed false. Secret presence and a role check do not
certify material readiness, provider grants, backup custody or operating reserve.

## Proposed existing-allocation launch profile

This is ready for coordinator review, and remains unexecuted. Do not invoke a
resident native worker from the web shell or create another service. The existing
image command is `python -m social_worker_supervisor`; with its switch off it
execs the current web process. No Dockerfile, command override, plan, instance
count, WEB_CONCURRENCY or deployment automation change is proposed.

| Component | Intended bound and evidence requirement |
| --- | --- |
| Web | Existing fixed one Gunicorn ASGI worker and master; current request admission remains authoritative. Preserve root backend, Dockerfile.prod, blank command/health overrides and disabled Auto-Deploy. |
| Social child | Exactly one launcher-owned process group, one external operation slot; the code ceiling of two is not pilot permission. CLI receives `--database-url-env SOCIAL_WORKER_DATABASE_URL`, `--worker-role` from the existing protected role reference, public schema and exact deployed SHA; no DSN in argv. |
| Worker DB/executor | Pool2, overflow0, pool wait10s, connect10s; statement5s/lock2s on every transaction. Two shared DB/native I/O threads plus main; no transaction across provider I/O. Retain current TLS/endpoint and verified least-privilege contract. |
| Other DB demand | Request pool5/overflow0, audit-reader1/overflow0, audit-writer1/overflow0. Legacy bootstrap/background engine5+10 remains a separate potential demand; other clients, operator access and pooler/backend units require complete operating-lane inventory. Nine is only the bounded API/audit/social subtotal, not accepted total demand. |
| Cadence/freshness | Active scans5s, heartbeat15s; idle scans/heartbeat60s; newly queued work can wait60s. Active API freshness45s, idle150s with future-clock/missing-scan refusal. Launcher exit and exact process evidence override a cached heartbeat as operator evidence. |
| Memory/CPU | Existing hard512MiB/0.5CPU; proposed combined peak<=460MiB, reserve>=52MiB, current abort480MiB; steady meanCPU<=0.4 and reserve0.1CPU. Current OFF-state sample is not an additive capacity calculation. Representative combined native/media/API and complete operating evidence remain pending. |
| Drain/host | Proposed explicit drain60s; complete supervisor stop<=75s and measured web/reap<10s inside historically accepted90s host window. Reap can add up to4s per owned group. Never set the maximum300s local drain on this90s host. The current UI does not expose a fresh90s value; historical accepted setting and receipts are preserved. |

The native/material/supervisor flags and operational attestation are independent
owner-controlled boundaries. The worker requires existing validated media reads
even for text work; use the existing uploads-off read path only after applicable
gates are accepted. Do not set an attestation merely to obtain a startup pass.
Keep existing protected app/key/media/worker references in place; do not export,
replace or widen them. No new credential or provider scope is proposed.

## Bounded future observation and abort sequence

1. After parent acceptance, reconcile exact serving source/package/binary hashes,
   role, explicit configuration, host window, complete client demand/reserve and
   provider/media/retention/custody gates. Preserve the four OFF-state baseline
   witnesses. Obtain the separate bounded owner decision naming the account,
   immutable manually reviewed content, time window and only permitted controls.
2. Use one existing-container child, one slot and one selected reviewed target;
   keep financial generation and policy automation OFF. Bind actual instance,
   source, owner/generation, child PID/group, launcher events and inherited-pipe
   custody before relying on a heartbeat. Observe initial idle/active heartbeat
   and last scan by their first expected intervals; freshness alone does not
   establish immediate process availability.
3. During a minimal bounded pilot, continuously observe combined memory/CPU/PIDs,
   actual worker/client/backend demand, API readiness and latency, aligned queue,
   provider confirmation and read/mutation counts, errors and egress. An initial
   180s bounded window is only a pilot, not representative closed-day or seven-day
   acceptance. Preserve protocol bytes separately from provider-billed quantities.
4. Abort on OOM, current memory>=480MiB, peak>460MiB or lost reserve, meanCPU>0.4,
   APIp95>1s/max>3s, readiness failure, extra process/slot/connection, stale/missing
   scan, source/credential/endpoint mismatch, unauthorized operation/egress,
   unresolved mutation, or missing custody. Pause global/affected account
   publishing through authorized controls and stop new worker admission. Do not
   turn a timeout into evidence that a mutation was unsent.
5. Drain/reap only the owned groups; archive full launcher stop/unavailable events,
   exit codes, provider/executor closure and durable claims/intents. Restore holds
   and read back all four OFF. A missing/malformed receipt, forced kill, unfinished
   work or uncertain commit retains ownership and blocks successors. No automatic
   restart, release, new-key resend, age-based takeover or cleanup is permitted.
6. Only a separately authorized coordinator can authenticate custody and use the
   existing privileged guarded release procedure. This lane performs no release.
   Before any binary rollback, positively stop/reap provider-capable code and
   preserve additive owner/history/queue state. A configuration rollback does not
   prove external effects were undone. Reuse the exact currently accepted web
   artifact if restoration is needed; older releases require their own ownership
   compatibility check. Do not downgrade schema/history.

## Evidence scope and remaining decisions

The source-bound lane packet is under the parent admin-redesign evidence root at
`worker-readiness-20261102`. It retains initial real failures, red/green fixtures,
raw/JUnit outcomes, exact commands, complete source hashes, independent executable
reviews and physical owned-container/volume cleanup. Local Linux amd64 execution
uses emulation on an ARM host; four image cases reproduce the already documented
inspection limitation and are explicitly excluded from the later worker-only
cohort. No image acceptance is claimed from that cohort.

| Current candidate validation | Actual result per normal/optimized mode |
| --- | --- |
| Deterministic author regression | 4 passed each; baseline had exactly1 failed/3 passed each. |
| Worker queue/role/CLI/heartbeat/stop cohort | 282 passed each, zero skips/failures/errors; four known emulated-image cases explicitly deselected. |
| Correctly assigned PostgreSQL supplements | 6 policy-scope cases and6 command/reconciliation cases passed each, zero skips/failures/errors. |
| Independent adversarial/spec review | 34 distinct controls passed each, including independent real-PG forced race and RLS/refusal controls. |
| Independent standards review | 51 passed each, including20 independently authored controls and existing ownership/CLI/release tests. |

These are overlapping selections and interpreter replays, not additive test
totals. The initial broad attempt retained5 failures/277 passes: the contention
failure and four known emulated-image failures. Its tmpfs JUnit disappeared when
the container stopped; its raw log remains diagnostic only. A later ordinary
supplement refused acceptance with6 prerequisite skips because the policy fixture
was assigned to the other isolated port. The final supplements execute all six
formerly skipped identities under their unchanged correct fixture in both modes;
the original skipped receipt is preserved. Independent reviewer harness and
publication mistakes are likewise retained and explicitly superseded. None is
represented as a product or production acceptance pass.

Preserve #699's accepted B29 actual-host synthetic capacity/platform-stop/custody
and guarded SQL recovery, and the later scoped logical restore receipts. Those
are not production Supabase/provider/storage sustained operation or a current
representative cost day. A current-release test failure is not grounds to erase
their original scope. The maintenance-host fixture graph has separate package
and pinned-base qualification limits; it is not the intended serving launch
artifact and is not started here.

The operating-envelope lane supplies complete client/backend inventory/reserve
and representative combined memory/CPU/egress/cycle evidence. Provider, media,
retention and independent production app-media restore remain their owners'
gates. The coordinator/owner supplies the final bounded pilot/stop/custody
decision after those inputs. No fixture, empty queue, paused account or OFF-state
sample closes #699 or waives any of those gates. Existing resources, costs,
Vercel Git disconnection, Render Auto-Deploy and ingestion pin remain untouched.

## Combined-validation fixture correction

The supervisor subprocess fixture previously treated a PID file as proof that
signal handlers were installed. A deterministic delayed worker startup reproduced
the resulting missing-closure assertion in normal and optimized Python. The
observed supervisor still stopped and reaped the child and retained ownership;
this was a test initialization race, not evidence of an unsafe release.

The inert children now publish readiness after installing handlers, and the web
failure scenario waits for that readiness within a fixed bound. Zero-delay and
400ms-delay cases preserve the nonzero exit, closure and process-absence checks,
and explicitly require null release proof with retained ownership. Product
supervisor code and its deadlines are unchanged. The full 23-case file passes in
both modes on the serving image. Source-bound author and independent receipts
are retained in the coordinator's `pr897-review-and-open-merges-20261102` packet;
earlier invalid private harness and timed-out attempts remain uncredited.
