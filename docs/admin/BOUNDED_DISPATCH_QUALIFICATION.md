# One bounded admin Dry Run

This is an operator qualification path for #554. It does not enable nightly
jobs, publishing, media uploads, source discovery or an unattended consumer.
The ordinary dispatch path remains opt-in. A present but invalid qualification
policy disables dispatch rather than falling back to ordinary execution.

## Admission and intent

Set `ADMIN_ETL_QUALIFICATION_POLICY` only for one reviewed attempt. It is an
exact JSON object with `version: 1`, a fresh canonical UUID4 `generation`, and
UTC `issued_at` / `expires_at` strings ending in `Z`. Their interval must be
exactly one hour; this is configuration/deployment admission time, not worker
runtime. A generation with any accepted command, or matching the current worker
row, is refused. No-intent registrations have no durable historical ledger
after another generation replaces that row: the operator must issue a fresh
UUID for every admission rather than reuse an older no-intent policy. At most
one accepted command per generation is independently enforced by durable
command history. Set dispatch sources to exactly `opendata`, OpenData
ingestion on, automatic seeding and release discovery off. The qualification
parser also requires the social/media/worker activation switches off.

Before admission, the existing read-only preflight must pass with the reviewed
source/role/host identity. Do not bypass its refusal. Qualification registration
independently requires no retained readiness, command, claim or nonterminal
job. It does not adopt old queued work or release uncertain execution ownership.

The UI and API allow only **OpenData Dry Run** for the matching generation.
Worker-row locking serializes acceptance across different administrators and
idempotency keys: at most one command is accepted for the generation. Replaying
that exact original intent reads its receipt; it does not create a second run.
The consumer and native adapter independently validate source, dry-run mode,
generation and time. The adapter uses the existing native ownership/job seam
and exact pinned KNBS workbook, with no release discovery or generation hook.
The Dry Run may create operational command/job/audit/claim records; it must not
create or update financial facts or source-document/extraction records.

## Existing-host resource bounds

Run `python -B -m admin_etl_qualification_watchdog` on the existing Linux host.
The fixed child module has no API lifespan, reference bootstrap or migration
entry point. It executes the handler inline on its main thread, preserving the
native signal deadline and avoiding a second heavy handler interpreter.

The watchdog refuses an unknown/unlimited cgroup or any allocation other than
the existing 512 MiB service. It admits at most 320 MiB of initial shared use,
samples every 0.1 seconds and stops its owned process group above 448 MiB.
This leaves **sampled** headroom; it is not a kernel reservation for the API,
and a burst between samples can exceed it. The existing service cgroup remains
the kernel memory limit. The child additionally has a 128 MiB data-segment
limit, 60-second soft / 61-second hard CPU limit, 64 file descriptors, disabled
core dumps and single-thread numerical libraries. These bounds are qualified
with Linux execution; do not infer compatibility from a Mac-only test.

The whole attempt allows 115 seconds before termination, then up to three
seconds for TERM and two seconds for KILL/reaping. Queue wait is at most 50
seconds and native handler time at most 45 seconds, with no HTTP retry. Output
is limited to 4 KiB. Only the owned process group is signaled; closure is an
error unless the child is reaped and the group absent. Database pooling allows
three connections with no overflow: native continuity ownership, handler and
heartbeat. Transactions use statement timeout 2 seconds, lock timeout 500 ms,
idle-in-transaction timeout 5 seconds, work_mem 64 KiB and no parallel query
workers. The native continuity-lock transaction deliberately disables its own
idle timeout while the whole worker remains under the external deadline.
The leader remains unreaped until all group signals have been sent, preventing
PID reuse from redirecting a later signal. An unexpected descendant after a
leader's terminal receipt is stopped but makes the attempt unverified.

## Shutdown and retained readiness

Finalization locks the worker row and clears worker/domain readiness only for
its own generation. It preserves every domain command reference and claim
token, and marks its still-running commands interrupted. An older finalizer
cannot clear a successor's readiness. Forced termination or lost database
acknowledgment is unverified execution, never authority to retry.

For the observed stale readiness-only state, dispatch must first be explicitly
off. Independently read and pin the current generation. The fixed operation
`python -B -m admin_etl_qualification_watchdog --retire-readiness <UUID4>`
refuses a fresh worker, wrong generation, nonterminal/unknown command or job,
unreleased native claim, or any domain command/token. It clears only readiness
and reads it back in a separate transaction. It never clears execution
ownership. Keep the pre-change evidence; do not rewrite historical receipts.

Afterward, rerun the read-only preflight. For the one admitted attempt, record
the actual Chrome acceptance, command/job/audit/claim correlation, source
provenance, unchanged financial/source tables, termination and independent
readiness/ownership readback. Restore dispatch off, remove the admission and
verify disabled UI controls. Do not run a second intent to make a failed or
uncertain attempt green. Publishing, uploads and Actions remain off.

Any maintainer override, deployment or production configuration change still
follows the repository's reviewed release procedure. This document itself
does not certify an installed image, actual host capacity or completed live
Dry Run. No new resource, paid tool or hosting plan is required.
