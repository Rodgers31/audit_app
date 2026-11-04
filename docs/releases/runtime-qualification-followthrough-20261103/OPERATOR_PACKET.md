# Held runtime follow-through — review-hardened preparation

Base: `1542bc5117f09b15b126e03bbd2158a54c348540`, tree
`2fa98d95754e9dde3f1407e315dd0317733c4d3a`. This additive packet changes no
application, build, admission guard or ingestion pin. The parent owns integration,
all production settings and every production command. Publishing, uploads,
social/admin ETL workers, financial generation and automatic approval, scheduling
and publication remain OFF. No manual dispatch, real upload, export/restore,
provider send, OAuth reconnect, canary or added cost is authorized.

## Required configuration and identity

The original supplied preparation witness is **3 November 2026, 4:55:13 p.m. CST**
(`2026-11-03T22:55:13.844054Z`). It records serving application
`f0f4705e9561e2e42edd93fc747e8bff24468fae`, Render deployment
`dep-dbl3il08v5cc73ak6g90`, Linux x86_64 Python 3.12.16, one existing 512 MiB /
0.5 CPU instance, schema `a756b20a0001`; sampled general controls are false.
That witness did not cover the distinct draft-generation master; see the parent
correction below.
This preparation does not refresh that witness. A configuration rollout may
replace the deployment/instance; record its actual identity and confirm unchanged
application bytes instead of requiring the historical deployment identifier.

`backend/main.py:1818` defaults cache warmup to true when
`AUTO_WARMUP_ENABLED` is absent. The corrected probe actually refused the missing
setting at 4:47 p.m. CST, before an observation. This does not prove an active
warmup task or enabled publishing. The parent must arrange explicit lowercase
`false` for **both** `AUTO_SEEDER_ENABLED` and `AUTO_WARMUP_ENABLED` in the real
service environment and verify the new process inherited them. Saving a dashboard
setting alone does not establish process resolution. Do not export an override
in the shell command to force acceptance. Do not roll back by deleting the warmup
setting: absence enables startup warmup.

Read back the startup lines `Auto-seeder disabled via AUTO_SEEDER_ENABLED=false`
and `Cache warmup disabled via AUTO_WARMUP_ENABLED=false` where available
(`backend/main.py:1768,1780`), plus the actual resolved flags. Do not start an app
to obtain those lines. Missing startup logs remain a stated observation gap.
`SOCIAL_MEDIA_FFPROBE_PATH` must resolve to `/usr/bin/ffprobe`. Every canonical
held flag covered by the unchanged reviewed `probe.py` must remain absent or
exactly `false`, except the two enabled defaults, which must be explicitly false.
All global automation booleans must remain false and connected account publishing
paused in the separate protected database witness. Also read the distinct
`social_generation_controls` master and scheduled repository hook variables;
`social_controls.generation_enabled=false` alone is insufficient.

The source pin is the **serving application** SHA above, distinct from the
operator repository SHA and from the ingestion admission pin. This packet never
reads or changes the admission pin. If the serving source, OS, architecture,
Python version, product hashes, codec binary or quota differ, stop and review the
new identity. Do not edit pins to obtain a pass.

## Parent correction — generation and configuration

A separate parent read at 23:23:17Z on 3 November found draft generation enabled,
version 6, for CoB/KRA. The normal admin OFF command produced version 7 with
drafts/shadow false at 23:36:59Z, preserving sources and destination fingerprint.
Both nightly generation hooks were set false. The only observed social changes
were one audit event and one command receipt; no post or financial change was
observed. At 23:38:31Z, remote `main` and ingestion pin matched
`1542bc5117f09b15b126e03bbd2158a54c348540`. These supplement the incomplete
historical general-control witness; no earlier master-OFF claim is accepted.

The parent then used Render **Save and deploy** with the existing build, adding
only `AUTO_WARMUP_ENABLED=false`. Deployment `dep-dbl74rs9v7es73b0aa50` became
live at approximately 23:47:22Z on instance `q5j7f`, unchanged application source
`f0f4705e9561e2e42edd93fc747e8bff24468fae`. Startup logged both seeder and warmup
disabled. The 23:48:15Z readback passed health/private-admin contracts, unchanged
financial/social fingerprints and zero background workers. The separate
23:48:40Z generation observation still showed version 7 drafts/shadow false.
The parent subsequently reconciled new bootstrap receipts 3629–3630 as
COMPLETED, zero created/updated/error counts (20/0 processed). These are startup
no-ops against their configured inputs, not a full nightly success.
At 23:49:08Z all 1,506 application files and 81 installed package versions
matched the retained serving inventory. This inventory does not itself accept codecs,
worker capacity, uploads or publishing. The later bounded codec result is recorded
in [parent result](PARENT_RESULT.md). Parent observations are retained privately
under `ingestion-pin-repair-20261103`, not produced by this preparation lane.

## Concrete parent execution

The durable source is `scripts/verification/launch_runtime/`. Run its
`build_held_command.py` locally with the existing supported interpreter and retain
the exact resulting shell command, byte count and SHA-256 in a fresh private
external evidence directory. [Qualification](QUALIFICATION.md) identifies the
current candidate command and runner; the earlier actual host receipt remains
bound to its old bytes in [parent result](PARENT_RESULT.md). The current candidate
has not been rerun on that host. The builder **prints only** and never runs the
host command. Review the expanded command before parent execution.

The builder has a fixed `REVIEWED_SHA256` manifest for all four transported
inputs, including the runner; it refuses modified input instead of generating a
new approval digest from it. The generated transport contains the same fixed
review pins independently of its data rows, checks exact names/order/cardinality
and matches captured bytes before compilation. Neither side may auto-repin a
dirty file. Any source/pin update requires independent review and a newly approved
complete command hash. The self-contained verifier is not an authentication or
signature system against changes to the entire command and its pins together.

The command uses `python -B -I -` in the existing host session. It transports
only the reviewed probe, new runner and three fixed synthetic codec fixtures
(two images in one JSON, one MP4). It verifies captured bytes before compiling
them, creates a private owned temporary directory, executes no application
startup and opens no network, database or provider connection. It reads only
the held flags, Linux cgroup/process metadata, pinned product files and pinned
ffprobe binary. It projects no DSN, account, role, token, signed URL, process
command line or provider body. Its decoded and output sizes are bounded.

The unchanged probe is pinned to
`7ad09a3d164cdbd963236c4c463ef2b4825ceb53af31b46be56ba57f6b1f7a2c`.
Product pins are `inspection.py`
`0238a1acca5c110d322a0918f64b0d51c17e5d38a4703197b7c8b634182ac4cf`,
`inspection_child.py`
`986237eacee78643a02890c63ea79f135aa501132d382b9f720a9310f0837c16`,
and `config.py`
`d739759a2a10d6b1e6ef3b5478122f5eccf1dc1840b7cd28653da4e70a4c64ed`.
The binary must match the previously observed ffprobe SHA
`cefc5f81c0b18429cdbf8fa5a89e1e9c759235e10f93f9b329ff1b2fdff26f46`.
Video uses a private copy of the verified binary and verified product parent/child;
images disable ffprobe entirely. Product limits are unchanged. Binary identity
does not attest all dynamic libraries or the complete host image.

Before execution, the parent records a fresh version of the existing protected
readback (producer SHA
`6528c8ba95a97658041f17c0ae6f59f76edf0dbbde743e13b0a54342bca1fccb`)
in its existing separately reviewed scope, plus the separate generation-master
observer and repository-hook readback. Compare serving source/schema, all
runtime/supplemental flags, controls version/booleans, account pauses, zero
background workers, social/media/financial fingerprints, zero asset/upload/
target/publication/attempt counts and HTTP readiness/private-admin contracts.
Retain that raw private observation locally. No credential or raw account/role
metadata belongs in this PR.

Run the exact hashed command once, attended. The inner observation must finish
in less than 75 seconds; the generated transport explicitly arms that observation
timer even when calling `observe()` directly. The original absolute 80-second
transport deadline is restored afterward (including refusal), leaving only its
remaining time for source rereads and cleanup. Both initial source capture and
private rereads are bounded to 32 KiB plus one refusal byte. The runner rechecks
held flags/source after image resource sampling and before H264 inspection; final
state/source guards remain required. No inner timeout refreshes the outer budget.
Children retain the product's 20-second inspection limit, CPU/file/descriptor
limits and file-only ffprobe protocol restrictions. The command emits exactly
one `HELD_RUNTIME_PACKET` line only after source readback and owned temporary
directory removal. Require exit zero, complete parseable finite JSON, exact
source/input/product/binary identities, three codec results and **nine** named
negative refusals, cleanup true and unchanged flags. Require all capacity,
upload/delivery and launch acceptance fields false. A partial line, generic
refusal, timeout, missing evidence or nonzero exit is **not accepted**.

Afterward repeat the same protected readback and compare with before. Bind the
command, executed runner, input/product bytes, full raw output, actual child exit,
before/after witnesses and producer hashes in a fresh append-only external receipt;
reopen it and check hashes and exact JSON primitive types. The command's stdout
is an observation, not an authenticated receipt. A local test with injected
Linux/cgroup readings cannot substitute for this real host run.

## Abort, cleanup and rollback

Abort qualification on any source/flag/schema/control/account pause change,
unexpected worker/object/provider activity or protected ledger change, any
OOM/kill evidence, memory telemetry missing, half-core/512 MiB quota mismatch,
less than 96 MiB current headroom before/between/after tiny codecs, codec failure,
source drift, missing process inventory, deadline or incomplete cleanup. The
96 MiB check is a tiny-probe execution guard, **not an accepted worker reserve**;
no sustained workload or safe capacity verdict is produced. Preserve every refusal
and rerun only after a separately identified cause is corrected by the parent.

On an ordinary exception the owned Python temporary-directory contexts remove
only their own synthetic files; product subprocess timeouts kill/wait the exact
inspection child, whose video mode replaces itself with ffprobe. On SIGKILL,
lost shell or ambiguous closure no completion is possible: retain the exact
owned path/PID, prove its process/descendant absence read-only, and hand any
remaining temporary files to the parent. This assignment authorizes no manual
cleanup/deletion or signal against the live service. Never use a broad `pkill`,
restart a worker or clear retained ownership to tidy an observation.

Tool rollback is to stop invoking this additive command and retain the unchanged
merged probe as historical source. The earlier probe version does **not** provide
current acceptance for the warmup mismatch. No application/schema/data rollback
is needed. Keep explicit false flags and all holds; the parent owns any separate
configuration rollback or recovery. Read back OFF state, worker absence and
protected fingerprints after any abort. Do not restore an unsafe absent warmup
value or delete/restore data. A source revert requires a separately reviewed PR.

## Remaining gates

This packet can establish only current tiny-codec functionality and instantaneous
OFF-state observations. Historical tiny PNG/JPEG/H264 and nine-negative receipts
remain historical. The eleven older emulated application-media failures remain
failures; neither local native success nor this narrower host observation upgrades
them to production passes.

Storage custody, retention/legal holds, renewal before the recorded 14 November
expiry, writer authority, retained copies, exact existing backup destination and
independent nonempty restore remain with the separate storage work. A real
browser upload, app asset/preview/retention, provider send and active worker are
unexercised. Stop timing, client inventories and accepted positive reserves below
remain required before the separately authorized 180-second zero-send worker
canary. That idle canary itself cannot accept sustained active media/delivery,
representative egress, recovery or a guaranteed no-cost operating profile.
