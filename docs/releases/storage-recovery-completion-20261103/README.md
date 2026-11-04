# Storage recovery completion packet

Prepared 3 November 2026, America/Chicago. **Live Stage A remains HELD.**
This adds a bounded row/object capture and isolated row reconstruction library;
it installs no policy, connects to no provider on import and adds no API, worker,
scheduler, flag or startup hook. Parent owns integration and every live command.
The earlier [decision packet](../storage-retention-packet-20261103/README.md)
and its immutable evidence indices retain their dated scopes.

Base: `e94eb980190f6074dcfc0f8ec6f9317fc74cfba0`, tree
`2d62058b07f8a23dbc2f0bdf3c15f46121b90e1e`. The old worktree branch/history is
preserved. Serving identity is the parent's dated `f0f4705` observation, not this
candidate. No current production row fingerprint is inferred from the pre-run
observations: scheduled run 41759203897 legitimately ran and failed after them.
Nightly diagnosis belongs to its lane; no rerun or repair is included here.

Current control-plane evidence is the [authenticated 4 November readback](AUTHENTICATED_READBACK.md).
It supersedes the earlier signed-out access conclusion. Live Stage A stays held;
the subsequent general account-token JSON preview fills the expiry timestamp.
Access restoration does not supply appointments or policy.

## Discoverable facts and precise remaining choices

| Subject | Filled fact / provenance | Remaining input |
| --- | --- | --- |
| Bucket | Authenticated 4 November 03:58–03:59Z refresh confirms private Standard bucket, exact origin/method/header CORS, 300-second max-age, only seven-day incomplete-multipart abort and no completed-original expiry or lock. Two old diagnostic PNGs; 304 B displayed. Original E05–E08 remain historical. | No exclusive writer or independent backup is inferred. See the dated readback for current usage and limits. |
| Access | Initial 03:31Z attempt was signed out; user restored login. This lane read authenticated visible metadata during 03:56–04:10:30Z without changing credentials/settings or reading secret values. | General account-token JSON preview later reveals exact expiry; off-system copy attestations remain unresolved. Initial access refusal is preserved as historical. |
| App token | Current account-token editor confirms Object Read & Write limited to the social bucket, start 15 October and end **14 November 2026**, empty include/exclude IP filters. The R2 editor exposes date only; the unedited general account-token JSON preview at04:18:31Z exposes **`expires_on: 2026-11-14T21:05:55Z` /15:05:55 CST**. E09/E10 deployed-identifier binding remains dated; no new key/signature test. | Named renewal operator and secure recovery custodian acceptance, secure-store reference, strictly earlier completion deadline and escalation. No person or grace time is invented; no credential change was made. |
| DB export rule | Roger has **already accepted seven-day rolling PRIVATE LOCAL DATABASE EXPORT retention**; original #488 comment 6330295479. Do not reopen this decision. | Reconcile actual copies/enforcement and any exception, without opening/deleting them. This gives no media/key/provider/WAL-copy or new-destination authority. |
| Existing local destination metadata | At **4 November 03:06:28Z / 3 November 21:06:28 CST**, metadata-only inventory found the historical private recovery root, owner UID501, mode0700; FileVault is On. A B42-named database.dump exists at 8,898,698 B, mode0600, matching historical size and locator. No content/hash identity was tested. Original B42 restore acceptance is preserved. | This root is a discoverable existing candidate, approved only within the old DB-export scope. Owner must explicitly choose the exact existing destination and scope for media custody; do not treat discovery as approval or independent/off-host custody. Private locator stays out of Git. |
| Overdue B42 follow-through | Historical not-after cutoff **29 October 02:45:54Z** has passed. Inventory found 276 regular files in the recovery root, including one .dump and 27 .sql candidates totaling 9,136,286 B; oldest candidate mtime 22 October 02:47:54Z. SQL files are classified by suffix only. A separate private backup root has four .dump candidates totaling2,746,814 B, oldest mtime27 September18:35:31Z. Four candidate roots were inspected to depth four; this is not a whole-machine/cloud census. | Roger confirms present/disposed-with-evidence/unresolved categories, oldest actual DB export, enforcement and the disposition/exception for the still-present archive locator. Presence is observed; disposal and continued-retention permission are not. No cleanup was run. |
| Policy | Existing implementation preserves referenced originals, unknown epochs, full reserved bytes and durable fences/history. Proposed periods/warnings remain unapproved. | Choose retention triggers/horizons, legal/evidence holds, exceptions and disposition authority by class; name the accountable owner and independent approver. |
| Custody and independence | No accepted media custodian, key-recovery owner, restore operator or independent reviewer was found in the supplied records. | Actual people must accept appointments. Restore operator and reviewer must differ; reviewer must be independent of capture/restore implementation. Role labels and Roger's narrower DB role do not fill these appointments. |

The smallest policy choice is to authorize only the one retained pair and its
bounded custody packet while holding deletion/expiry/retirement indefinitely
OFF pending a separately specified policy. This is a proposed operation scope,
not an approved retention horizon. An alternative is to refuse intake until the
broader class policy is settled. Neither option invents a legal determination.

## Possible writers: positive reconciliation, not a quiet LIST

| Writer/copy class | What engineering established | Required current witness |
| --- | --- | --- |
| Web process | `backend/social/media/runtime.py` constructs the R2 client from existing config; allocation/signing, finalization and deletion/fencing ports are in `service.py`, `storage.py`, `fencing.py`. Original conditional protocol is recorded at admission. | Exact deployed identifier/scope and web instance/config readback. OFF flags do not revoke a credential or prove its copies absent. |
| Worker/maintenance/operator code | `backend/social/worker/media_reads.py` consumes the same configured storage credential for its read port. Media maintenance/CLI and privacy retirement can reach mutation ports only within their explicit guards. | Current process, deployment/env-group and operator-client census, including stopped clients that retain credentials. No worker or command is started for this discovery. |
| Local checkout | No .env/.env.local/.env.production/backend .env file exists in this assigned fresh worktree. Only known candidate recovery roots were inventoried; no secret contents were read. | Owner inventories authorized credential stores/copies, holders, CI secrets and off-system clients. Absence in this checkout does not establish machine-wide absence. |
| Cloud administrators / account tokens | Authenticated listing: one active entire-account Super Administrator; four Account API tokens, including social-bucket ObjectRW, source-bucket ObjectRW×2 and all-bucket Admin Read Only×1; zero user API tokens. | Named holder/copy attestations and accepted restrictions; the administrator can alter authority. No appointment is inferred. Secret values and raw account/role bodies were not read/exported. |
| Workers / replication / external tools | Authenticated Show all/empty-search inventory contains zero Workers/Pages projects, hence no project R2 bindings in this account. Optional catalog/migration disabled; no connected Cloudflare OAuth applications. Current R2 S3 documentation lists versioning/replication APIs unimplemented. | Off-system S3 clients, legacy/global keys, credential copies and external backup/replication remain unattested. Provider API absence does not prove no external copies. |

The general account-token JSON preview now fills the exact social token expiry
with timezone. No owner API command or new token is requested. Secure-holder/copy
attestations remain required for deployment/operator/external clients. The dated
readback records the distinct date-only, minute and final seconds-precision
observations. No object creation, PUT signing/test, renewal or paid service occurred.

Renewal handoff must contain the private existing secret-store reference,
exact expiry evidence/hash, named operator/custodian acceptance, explicit
pre-expiry completion deadline and escalation route. A possible planning target
is **10 November 18:00Z / noon CST**, but it remains unapproved and must be
checked to precede the verified **14 November21:05:55Z** expiry. Unknown/missed deadline
holds intake. This packet performs no renewal or secret recovery.

## Executable capture/reconstruction boundary

[`backend/social/media/recovery.py`](../../../backend/social/media/recovery.py)
exports four explicit operations:

1. `capture_stage_a_rows(db, actor_uuid, asset_uuid, post_uuid)` reads only the
   first retained upload and one manual initial draft. Caller must already hold
   a PostgreSQL REPEATABLE READ READ ONLY transaction with `row_security=off`;
   RLS-filtered reads refuse. It bounds 64 total rows and 131,072 encoded bytes.
   Actual incoming FKs across schemas, including histories attached to captured
   audit/receipt rows and posts depending on this post, must be included or
   empty. Any broader closure refuses rather than being truncated/exported.
2. `capture_stage_a_payloads(rows, read_storage)` HEADs/downloads both exact
   copies with the concrete storage identity checks, binds both recorded ETags
   and the original's version/hash metadata, hashes the downloaded bytes and
   rechecks snapshots. It performs no object write/delete. Version absence is
   recorded honestly. Transient bounded capture files are used; the approved
   custody plan must cover their processing lifecycle too.
3. `verify_stage_a_payloads(rows, independently_read_payloads)` requires exactly
   both keys, positive exact lengths and the recorded SHA256 for each copy.
   Missing/corrupt quarantine is a failure even when original preview works.
4. `restore_stage_a_rows(connection, rows_bytes)` inserts into an empty isolated
   target inside a savepoint, runs deferred checks, verifies complete semantic
   closure and exact stored rows before returning. A caught error cannot commit
   a partial usable asset. It never creates a connection/schema, truncates data,
   overwrites a nonempty target or issues remote storage writes. It is not an
   HTTP restore port or authorization mechanism. Merely encoding JSON is not
   semantic validation or recovery acceptance.

[`recovery_packet.py`](../../../backend/social/media/recovery_packet.py) supplies
the callable publication/readback wrapper: `publish_stage_a_packet(...)` writes
only a fresh custody-UUID child of an existing owner-only destination, with
exclusive0600 files, file/directory fsync and complete byte readback. It refuses
invalid/existing destinations before capture I/O and preserves partial files on
failure. `read_stage_a_packet(...)` requires the independently retained outer
manifest hash and rejects missing/corrupt/extra/symlinked/hardlinked inputs.
Context hashes are references, not approvals. The manifest explicitly labels its
generator hash as observed file bytes and execution authentication false; the
parent recorder must independently bind the executed frozen producer/runtime.

The non-FK signed-intent/effect ledger and possible-writer inventory remain
independent required inputs. SQL metadata cannot prove their absence. This
deliberately minimal protocol refuses owner/deletion history, source/account
parents, extra revisions or other media. If any are discovered, stop and review
a larger exact packet; never drop them to fit the cap.

## Proposed complete byte and operation envelope

| Component | Proposed hard cap / expected operation |
| --- | --- |
| Remote intake | One synthetic 1080×1080 JPEG ≤262,144 B; quarantine+original ≤524,288 B; reserve exactly 2× declared bytes. No other app objects or permanent-marker conversion. |
| New custody data | Rows/history ≤131,072 B, copied payloads ≤524,288 B, object/source/decision/custody manifest ≤65,536 B: **≤720,896 B total**. Parent must approve this total, not only media bytes. In-memory and transient scratch peaks are separately bounded. |
| Recovery executables | Existing cached serving image 1,567,501,754 B, existing PG image 661,055,639 B, tracked backend+ETL source 18,500,031 B at base (candidate source adds a small measured delta). These are dependency identities, not media. Proposed inclusive dependency closure **≤2.5 GiB**, with source/schema/tools ≤64 MiB and no pulls/builds/new copies unless exact existing destination/copy authority includes them. Actual archive byte sizes/hashes must be measured if copied; image Size is not a docker-save archive size. |
| Existing dependencies option | If those exact source/runtime/schema/tool inputs already have separately accepted durable custody and recovery access, record their private references, hashes, byte inventory and availability test. No transfer bytes may be hidden by calling them “references.” If not, the ≤720,896 B data packet alone is incomplete; rescope the total, destination and time window first. |
| Whole local operation | Proposed **4 GiB inclusive**: ≤2.5 GiB dependency custody, five isolated PG data variants ≤160 MiB each (800 MiB), browser/cache workspace ≤64 MiB, transient processing ≤16 MiB and preserved fixture/custody/logical-restore packets ≤8 MiB. Each item needs enforced/observed bounds; opaque cache, physical index/WAL or archive overhead is not zero. Existing source-provider physical/WAL/backups remain separately unqualified. This is a local operation cap, not measured billed bytes. |
| DB closure | Expected +1 asset/+1 upload/+2 initially absent budgets/+1 post/+1 initial revision/+1 reference/+6 media/post audit events/+1 post command receipt. The measured inert flow has 14 total rows across 11 tables, three explicitly empty history tables. Grant retries or preexisting budgets alter the envelope: abort/reconcile, never edit history. |
| Object operations | Browser one signed conditional PUT; service normal completion/inspection and both-copy verification; one private preview/GET; custody two bounded GETs with conditional identities and before/after HEADs. No deletion, provider send, restore PUT or canary. Actual wire counters are recorded; SDK metadata calls are not zero-cost proofs. |

Local inert measurement: JPEG 19,125 B, two payloads 38,250 B, row JSON 7,817 B
(46,067 B before the outer manifest). The first native Linux ARM64/3.12.16
seven-case run completed in 3.94s; the image differs from 22 of 81 shipping
versions. A later 141-case focused run on its frozen source passed. These are
feasibility measurements, not serving/operating acceptance. Exact shipping
Linux x86_64/3.12.16/all81 replay initially failed seven actual-child-inspection
cases with `MEDIA_INSPECTION_FAILED`; failures are preserved. Inert-inspector
row/transport tests and native decoder results must stay separately labeled.
Final native ARM64 replay passed 164 distinct cases in each normal/optimized mode,
with those same 22 version differences. Independent shipping-package x86_64
reviews passed 28 Standards and 43 Spec cases per mode using an inert inspector;
selections overlap and are not additive. Actual PostgreSQL snapshot/closure/restore
and packet readback passed with local PG17.11 ARM64. The private handoff binds
source, producer, commands and results. Filesystem acceptance used native Linux
tmpfs: a Docker Desktop host bind mount refused directory stability checks. The
chosen real custody filesystem still needs qualification; no guard was weakened.

The proposed ten-minute intake/60-minute attended total is **not approved**.
Small fixture timing supports data-path feasibility only. It does not measure
browser delays, provider throughput, operator attendance, independent review,
dependency-custody preparation or live resource reserves. Pre-stage existing
dependencies must already be qualified before starting that clock; if a complete
closure cannot fit, HOLD and rescope rather than extending time or omitting it.

Copy classes include the source fixture file, browser/OS cache and decoded
buffers, inspector/transient files, remote quarantine/original, custody packet,
positive restore and four preserved damaged variants. The two-copy/2N app quota
describes remote source payloads only; it is not a total-copy census. The browser
API response is private/no-store, but direct R2 signed GET currently sets only
Content-Type/Disposition in `storage.py:_signed_get`; no ResponseCacheControl
override is requested there. Direct response/cache behavior and copy lifecycle
must be observed/accepted in the future bounded path. The privacy/admin contract
handoff is to review a signed GET cache-control override and browser copy budget;
no provider header guarantee, cache purge or shared-scope change is asserted here.

Continue with the exact [future operation sequence](STAGE_A.md). No stage,
policy or appointment is accepted by this document.
