# Storage retention decision and held pilot

Prepared 3 November 2026, America/Chicago. **PROPOSED — NOT APPROVED OR RUN.**
This packet is for the storage portion of issues [490](https://github.com/Rodgers31/audit_app/issues/490)
and [488](https://github.com/Rodgers31/audit_app/issues/488). Both remain open.
It records a concrete decision for later authorization. It installs no policy,
activates no control and supplies no application-media production acceptance.

The engineering baseline is commit `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39`,
tree `429c94692890811fcab68668c5ee1ecd19226c5e`. Its media implementation matches
the prior storage lane's `2e206ed9974b254adf75b44867915e326d54487c` byte for byte.
The prior 2 November packet and producers remain historical evidence; they have
not been edited or relabelled as observations of the newer deployment.

## Decision requested

Choose one retained-only pilot using the existing private social bucket and
existing credential. Authorize only the separately described temporary upload
exception, normal proof-bound pending-slot release and bounded capture to an
already approved custody destination. Retain both object copies and full byte
charges. Authorize no deletion, expiry, quota refund, provider delivery, worker
start or ongoing intake. Until the fields below are completed and the exact
execution is authorized, keep uploads, publishing, workers and financial
generation OFF, with native and automatic source admission held.

| Required decision | Proposed value / owner input still needed |
| --- | --- |
| Retention policy | Adopt or replace every period in the table below; record legal holds and exceptions. Approval and the policy content hash are separate facts. No hash is installed by this packet. |
| Accountable owner and privacy approver | **Unassigned.** Name the owner and independent privacy/legal approver, including approval date and scope. |
| Maintenance operator and backup | **Unassigned.** Name actual people/roles and escalation contact. |
| Backup custodian and key recovery | **Unassigned.** Name custodian, access control and encryption/key-recovery responsibility. |
| Existing approved custody destination | **Unspecified.** Record exact existing destination, authorized DB/object classes, retention, access, byte cap and custody UUID. Approval for credential backup does not authorize application-data export. |
| Restore operator and independent reviewer | **Unassigned.** Name a restore operator and a different reviewer independent of capture/restore implementation; record exact review scope and result. |
| Storage control-plane observer | **Unassigned.** Use existing authorized read-only access; record account/bucket/build/origin and observation time. No new key, scope, login exchange or policy mutation is included. |
| Bounded execution | **Held.** Parent integrates current host/capacity and privacy prerequisites, fixes exact draft/capture identities and authorizes the named exception. This packet is not that authorization. |

The local evidence directory is approved for synthetic checks and sanitized
reports only within this lane. No blanket approval for production social DB or
media export to it, Drive, a source bucket or another destination is inferred.

## Proposed retention and maintenance policy

| Data class | Proposed retention and disposition | Required protection |
| --- | --- | --- |
| Ready originals and inspection identity | Preserve originals with any historical revision reference; no automatic expiry. Review unattached originals after 30 days. Review grants no deletion authority. | Preserve original bytes, checksum, ETag/version, MIME/geometry and every historical reference. |
| Quarantine, pending, failed or ambiguous uploads | Retain both copies and all reserved bytes while write history remains unknown. A 24-hour orphan deadline is eligibility metadata only. | No age-, HEAD- or lease-based force release. Failed/uncertain retained verification keeps pending held. |
| Write owners/attempts, budgets, retained fences, permanent markers and deletion/effect history | Preserve complete admission and effect history through stop, rollback and restore; no automatic expiry. | Unknown/off-system/legacy histories remain quarantined. Do not retrofit a protocol or settlement onto old rows. Lifetime admission is never refunded. |
| Immutable revisions, provenance, approvals and publication/attempt history | Preserve pending a separately approved accountability policy; no period is approved here. | Current-draft deletion does not remove historical references or recipient copies. |
| Sanitized detailed operator reports | Proposed 90 days; retain compact acceptance/incident summaries while their assets/effects remain relevant. | Owner approves periods/exceptions before expiry. |
| Verbose operational logs / failed diagnostics | Proposed 30 / 90 days. | Exclude tokens, DSNs, signed URLs, ciphertext and cookies. Infrastructure and callback copy retention require separate evidence. |
| Backup packet and unresolved external intent | Preserve a consistent complete packet and all later unresolved effect/intent records. Proposed recovery-point objective: 24 hours during operation and before approved maintenance. | Exact approved destination/classes, recoverable custody and independent restore reviewer required. This is an objective, not an achieved recovery guarantee. |
| Existing diagnostic objects | Preserve under their historical diagnostic custody. | Two 77-byte diagnostics are outside the application asset ledger and cannot qualify real app-media backup or restore. |
| Provider, CDN and recipient copies | Separate privacy/account decision. | A media deletion result cannot establish full erasure outside the media boundary. |

The existing implementation's defaults are 200 MiB per actor, 2 GiB globally,
three pending uploads per actor, image size 10 MiB and video size 50 MiB.
New intake reserves twice declared bytes. Upload TTL is 300 seconds, preview TTL
120 seconds, inspection timeout 20 seconds and lease 120 seconds. These are source
defaults; execution must read the actual approved runtime configuration.
[MediaConfig](../../backend/social/media/config.py) is the source contract.

Proposed operator warnings start at 70% actor/global reserved bytes; stop new
admission at 80%, any pending ceiling, discrepancy, unexpected writer/object,
missing original/history or unverified restored marker. These are proposed
procedures, not installed enforcement. Existing hard quotas remain authoritative.
Retained-only mode is bounded to this one-asset proposal and is not an accepted
indefinite operating profile.

## Engineering boundary and safe operator ports

The normal retained mode records `conditional_create_v1` at original admission.
[Completion](../../backend/social/media/service.py) invokes
[retain_ready](../../backend/social/media/retention.py) when configured. Successful
verification downloads and hashes both exact copies outside SQL locks, rechecks
current version/scope/lease under the budget and asset locks, records the fence
and releases only the pending slot in the same transaction. Full two-copy byte
reservation and unknown browser-write epochs remain. Failure or uncertainty
holds capacity; a saved marker is not generic write-drain evidence.

The proposed pilot must explicitly authorize that normal pending-slot release.
It must not force release after failure. Retained histories are excluded from
ordinary cleanup. Fenced retirement and owned-quiescence modes stay OFF. A later
retirement/deletion policy is a separate reviewed decision.

[report_once / prepare_reconciliation](../../backend/social/media/maintenance.py)
provides a bounded database-only observation. It validates limit 1–20 and an
optional UUID cursor before opening the report connection. On PostgreSQL each
page uses repeatable-read/read-only mode and a five-second statement timeout;
pages are separate observations. Observe counts, quotas, unknown epochs, retained
fences, discrepancies and all historical-reference protection. No object I/O,
quota release, write drainage, deletion authority or repair follows from a report.
Use the existing in-process credential/DSN source, never a literal secret in argv.

`run_once` defaults to report-only. `--allow-cleanup`,
`--recover-retained-upload`, `--reconcile-owned-command` and `--retire-command`
are mutation surfaces with separate authority. They are outside this held pilot.
No timer, service or recurring worker is installed. Proposed cadence after an
approved pilot: baseline, after each completed phase, after stop, then daily
only during separately accepted operation; triage backlog next business day.

## Current configuration evidence required

The 2 November evidence records a successful LIST and conditional HEAD of the
two diagnostics, an empty application-media ledger and a CORS-read AccessDenied
with the app credential. The dashboard was signed out. These are historical,
scoped observations, not a current storage-policy or new-release acceptance.
AccessDenied is appropriate least privilege; do not broaden the app credential.

Before any pilot, an existing authorized control-plane reader must bind these
facts to the exact social account, private bucket, deployed build, credential
metadata and live origin:

- Private access and exact `https://www.auditgava.com` CORS methods/headers for
  the intended signed PUT, GET and HEAD behavior.
- No lifecycle expiry of completed originals, retained source copies or permanent
  markers; identify versioning/replication behavior and every possible writer.
- Existing credential scope, expiry/rotation responsibility and secure recovery
  metadata, with no credential values exported.

Absent access or source-visible metadata is a blocker, not a policy failure and
not authority to create access. Retain the exact refusal; use an authorized owner
observation later. Do not infer provider configuration from a code comment,
quiet inventory, empty ledger or synthetic test.

## One storage-only pilot, for later authorization

**Limit:** one administrator; one synthetic 1080×1080 JPEG of at most 262,144
bytes; one fresh application-allocated upload/asset; one new test post with one
initial immutable revision and one asset reference; zero targets, publications,
attempts, provider sends and workers. Maximum retained payload and reservation:
524,288 bytes across two copies. Do not generate the image or allocate any asset
as preparation for this decision.

1. Parent binds the actual backend/frontend/origin, existing allocation and
   inspector to the reviewed source, with independent host/capacity and privacy
   prerequisites. Capture a fresh read-only DB/object/control baseline. Do not
   use an old inert test build as deployment evidence. Refuse unexpected writer,
   target, publication, attempt, object or source drift.
2. Owner fixes exact actor, new test-draft name, approved custody destination,
   authorized dependent tables/object classes, byte cap and independent reviewer.
   Generate and independently inspect the synthetic JPEG only after authorization;
   record exact bytes/hash/MIME/dimensions and nonpublishing caption/alt text.
3. Parent temporarily enables only upload issuance and retained-write recording
   on the existing service, with the explicit pending-release exception. Keep
   fenced retirement, owned quiescence, publishing, workers/supervision, financial
   generation, automation and native/automatic source admission held. Verify
   actual flags and unchanged allocation/source before intake.
4. Through the real browser on the exact live origin and normal application
   path, initiate one upload with its original idempotency key and expected
   version. Observe signed conditional PUT, bounded inspection, ready private
   library/preview and exact hash. Never log bearer URLs/tokens. Attach it to the
   one new test post/revision using the normal API/UI after verifying exact
   create semantics. Do not alter an existing draft. Account validation is
   separate; unavailable native/account readiness remains a blocker and is not
   hidden by activating it.
5. Parent restores upload/protocol flags OFF promptly and reads back all held
   controls and zero worker/target/publication/attempt census. Success requires
   pending_count=0, exact retained fence, unknown browser epochs and declared
   bytes ×2 still charged. Failure/uncertainty means pending_count=1, retained
   bytes and incomplete pilot. No second upload or forced repair is permitted.
6. Under the separately approved bounded copy scope, capture a consistent
   read-only DB snapshot and exact object versions to named existing custody.
   Include schema/source/runtime, assets/uploads/budgets, owners/attempts,
   commands/audit events and required parents, immutable revisions/references,
   retained fence, pending/grant/finalization state, deletion/effect history,
   exact keys/sizes/ETags/versions/hashes/metadata and permanent markers, plus
   applicable independently retained signed intent. Unknown writes prevent a
   consistency claim without an independently reviewed fencing/capture procedure.
   Do not export unrelated secrets/account ciphertext/financial/source records or
   omit dependency closure merely to meet the cap. Stop and rescope if the
   approved packet cannot fit. Hash at capture and independently read back bytes.
7. The named restore operator reconstructs the actual captured packet in the
   approved isolated target with no production credentials/public listeners. A
   different reviewer, independent of capture and restore implementation, checks
   the retained input bytes and reconstruction results. Reinspect reconstructed
   originals; verify private preview/library, all historical
   references, exact full byte charges, pending release and unknown epochs,
   retained fence and effect/intent agreement. Exercise missing/corrupt original
   refusals. Missing history or later unresolved effects mean quarantine, never
   permission to overwrite objects or refund quota. No remote R2 restore write
   or production overwrite is included; qualify those separately if required.
8. Record exact source/runtime, inputs/outputs/hashes, row/object deltas, custody
   UUID, independent review and residual gaps. Preserve original objects and all
   history. Verify removal only of owned disposable synthetic resources. Accept
   only the observed scope; issues 490/488 retain all unmet criteria.

Expected authorized deltas: +1 asset, +1 upload, lazy actor/global budget rows,
two object copies, +1 post/+1 initial revision/+1 reference and bounded normal
command/audit records. Fix and verify exact API create semantics before submitting;
unexpected extra revisions are an incomplete pilot, not a reason to rewrite
history. The two diagnostics stay separate and unchanged. The backup byte cap
must account for the approved dependency closure as well as the ≤512 KiB media.

Abort on any missing prerequisite, unknown outcome, version/scope/account drift,
unexpected activity, corrupt/missing original/history, inconsistent packet or
budget breach. Stop admission through the approved parent action; preserve the
original command, uncertainty, both copies, markers, reservations and histories.
Do not delete the test draft to conceal effects, retry with a fresh idempotency
key, force pending release, refund bytes, downgrade schema or restore an old
snapshot over current objects. No automatic cleanup or rollback deletion is
part of this proposal.

## Acceptance limits

Offline tests can prove bounded report behavior, transaction fences, retained
accounting and synthetic reconstruction against the measured source/runtime.
They cannot approve a policy, identify a custodian, supply current bucket
metadata, establish real production custody/restore, representative egress/cost
or authorize operation. No synthetic restore, 77-byte diagnostic, empty ledger,
source merge or successful test suite substitutes for the actual one-asset
application path and independent approved-custody restore.
