# Held media, storage and host verification — 3 November 2026

Target: serving commit `f0f4705e9561e2e42edd93fc747e8bff24468fae`, tree
`23f49a0df4ef667f3e253cbf65347bdfe38b1153`. This change adds an observation
tool and documents scoped results. It changes no application code, schema,
dependency, production setting, source admission, plan or ingestion pin.
Publishing, uploads, workers and financial generation remain OFF.

## Review correction — 3 November 2026

The original observation tool omitted analytics, OpenData/KNBS qualification seed
gates and enabled-by-default cache warmup. It also allowed an absent auto-seeder
flag despite the application's production default being enabled. The corrected
tool requires explicit `false` for auto-seeder and warmup, and reconciles its
remaining inventory against the canonical qualification flags in an offline test.
Original receipts remain historical observations of their enumerated flags;
they do not prove that omitted or enabled-by-default controls were held.

Caller-selected source hashes previously checked consistency without independent
execution authority. The tool now requires its embedded reviewed product manifest,
verifies every source before execution and uses a private verified snapshot for
both parent modules and the child. Image checks disable ffprobe entirely. A lone
fixture-packet argument now refuses before observation. Regression fixtures were
executed against the original and corrected probe in normal and optimized Python.
These examiner changes do not change application code or retrospectively upgrade
the scope of the original production results.

## What the new observations establish

The actual serving x86_64 runtime decoded one tiny PNG, one JPEG and one H.264
MP4 through the unchanged bounded product inspector. All nine negative controls
(wrong MIME, wrong length, malformed bytes for each format) refused. The exact
ffprobe configured/resolved path, version and binary hash were retained. No
application upload, asset, retained object, provider operation or worker was
created. Synthetic bytes existed only in private temporary inspection files.

This resolves the **tiny-codec execution boundary on the actual host**. The
eleven historical emulated application-media failures remain historical failures;
they were not rerun as eleven production passes, and their cause is not inferred
from the new result. Larger/concurrent intake, real browser/R2 signed operations,
private library/preview and custody/restore acceptance remain separate.

Current authorized Cloudflare dashboard reads confirmed private access, no custom
or public development domain, exact live-origin GET/HEAD/PUT CORS with the
conditional-write header and exposed ETag, and no lifecycle expiry of completed
objects. The only lifecycle rule aborts incomplete multipart uploads. The two
old diagnostic objects retain their listed identities/sizes/modification times;
they are not application-media acceptance. Dashboard request counters changed
during inspection and are not object-write evidence.

The listed storage-token scope/expiry was read without displaying credentials or
changing access. A digest comparison also binds the deployed access-key ID,
bucket and endpoint to that exact token record. Cloudflare's
[credential mapping](https://developers.cloudflare.com/data-localization/how-to/r2/)
identifies the token ID as the S3 access-key ID. This establishes configured
identifier binding, not a successful signature, live PUT or exclusive writers.
Renewal/custody responsibility, account administrators and any other possible
writer still require reconciliation.
No bucket lock, replication or independent backup was installed. Cloudflare's
[S3 compatibility reference](https://developers.cloudflare.com/r2/api/s3/api/)
lists bucket-versioning and replication operations as unsupported; they cannot
serve as assumed backup/restore controls.

## Current-host inventory and its limits

The existing allocation and single web-process topology were observed, along
with cgroup memory/CPU/PID limits, process RSS/threads, CPU throttling counters
and OOM counters. Samples include observer overhead. Current and retained peak
are different observations; neither is a representative busy-worker peak.
Missing history, unknown reset/lifetime and no worker execution prevent a
sustained-capacity acceptance claim.

Sanitized configured references and separate catalog-only read-only connections
established that the main app uses a transaction-pooler endpoint while the audit
reader and future social worker use a session-pooler endpoint with distinct
logins. Database-name hashes agree across the three observations. Separate
metadata comparisons bind the configured project/login suffix, host, database
name and ports to AuditGava. This is configured routing evidence; physical
backend identity was not attested. Existing
verify-full TLS/CA was used; no grant or credential was created. Role connection
limits, observer-session memory settings and grouped backend counts were retained
without reading query text or application rows. Restricted-role views are masked;
the observations are sequential and include the observer. Background processes
in `pg_stat_activity` are not all pooler clients or connection slots.

The source ceilings remain:

| Population | Configured client ceiling |
| --- | ---: |
| Web legacy/bootstrap pool | 5 + 10 overflow |
| Web request pool | 5, no overflow |
| Web audit writer | 1, no overflow |
| Restricted audit reader, conservatively reserved | 1, no overflow |
| One web subtotal | 22 |
| Future separate social worker | 2, no overflow |
| Web plus future worker, before other clients/reserve | 24 |

These are planning ceilings, not measured occupancy. Reconcile the independently
scheduled GitHub seeding/migration/validation writer, source-cache reader,
ordinary admin ETL consumer, platform services and operator/observer clients
before selecting reserve. The source-cache CLI constructs its own default
QueuePool. Its job steps are separate from
the web process; the 24-client worksheet does not account for it. No seed run
or admin consumer was started to fill this gap.

Provider client limits, per-user/database backend limits and database-wide
connection limits are different units. Current metadata alone cannot establish
peak populations or positive accepted reserve. The provider still reports a
memory-commitment warning and unavailable connection-history charts. A cause
such as a leak or OOM is not established. The current effective host shutdown
window was not exposed by the inspected UI; the historical 90-second proof is
not a fresh control-plane readback. Render's [documented default](https://render.com/docs/deploys)
cannot establish this service's actual setting.

## Evidence and review

Nonpublic dashboard transcriptions, runtime observations, role metadata,
commands and source-bound receipts stay in the coordinator's local
`media-storage-host-verification-20261103` packet. They are not authenticated
portable provider exports. `REPORT-v3.md`, `RECEIPT-v2.json` and its preserved producer
bind exact input/output hashes, versions, target, before/after witnesses and
independent reviews. Earlier report/index versions remain historical; the current
formatter also validates OFF semantics before emitting an OFF summary. No raw DSN, key, token, signed URL or query text is included
in this repository change.

The original revision of the [probe](../../../scripts/verification/launch_runtime/README.md)
was executed on the serving host. Its eight offline verifier tests passed in normal and
optimized Python. The corrected revision has twelve offline verifier tests; its
review results and any fresh host execution are recorded separately rather than
attributed to the original receipts. Independent adversarial, Standards and Spec controls execute
the guards and actual product child. Failed pre-fix cases and transport/setup
failures remain preserved. Corrections reject explicit port zero, previously
unguarded enabled controls, blank counter maps and literal-unset flags; missing process
RSS is unavailable rather than invented zero. Catalog-tool refusals retain their
original outputs; the corrected examiner accepts bounded provider extension
worker labels without treating them as an accepted workload.

The final production comparison retains identical financial/social witnesses,
controls, account pause state, schema, ingestion summary and background-process
census. Media assets/uploads, targets, publications and attempts remain empty.
No paid review, hosted rerun, resource/plan, policy or automation was added.

## Remaining decision and execution gates

Issues [490](https://github.com/Rodgers31/audit_app/issues/490),
[488](https://github.com/Rodgers31/audit_app/issues/488),
[778](https://github.com/Rodgers31/audit_app/issues/778) and
[481](https://github.com/Rodgers31/audit_app/issues/481) remain open.

1. Reconcile writer authority, renewal, recovery custody, approved retention/legal holds, exact
   existing backup destination and independent restore reviewer. The existing
   private-DB export decision does not authorize media/data export.
2. Obtain current host stop timing and missing provider metric/history semantics;
   reconcile other clients and accept positive memory/connection/byte reserves
   for the bounded intended profile. Add no resource or speculative tuning.
3. After those prerequisites and separate explicit authorization, execute the
   existing [one-asset storage/restore pilot](../../operations/storage-retention-20261103.md)
   and [zero-send worker canary](../controlled-launch-20261103/PILOT_PROPOSAL.md).
   Busy worker/media, representative operating/egress observations and any later
   real sends retain their own gates. Keep every control held until then.
